# -*- coding: utf-8 -*-
"""SQLAlchemy ORM 模型：6 张表。
- questions          题目
- papers             试卷
- paper_items        试卷-题目 关联（含分值、大题、顺序）
- students           学生
- student_mistakes   学生错题（必须关联题库题目，同时存快照）
- student_files      学生图片/附件
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(text: str, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


# ============================================================
# 1. 题目
# ============================================================
class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 分类维度
    grade: Mapped[str] = mapped_column(String(20), default="", index=True)       # 年级
    chapter: Mapped[str] = mapped_column(String(80), default="", index=True)     # 章节
    knowledge: Mapped[str] = mapped_column(Text, default="")                     # 知识点，逗号分隔
    qtype: Mapped[str] = mapped_column(String(20), default="解答题", index=True)  # 题型
    difficulty: Mapped[int] = mapped_column(Integer, default=3, index=True)      # 1~5

    # 内容
    stem: Mapped[str] = mapped_column(Text, default="")        # 题干（含 LaTeX）
    options: Mapped[str] = mapped_column(Text, default="[]")   # 选项 JSON 字符串
    answer: Mapped[str] = mapped_column(Text, default="")      # 答案
    analysis: Mapped[str] = mapped_column(Text, default="")    # 解析
    source: Mapped[str] = mapped_column(String(200), default="", index=True)  # 来源
    tags: Mapped[str] = mapped_column(Text, default="")        # 标签，逗号分隔
    image_paths: Mapped[str] = mapped_column(Text, default="[]")  # 图片相对路径 JSON 数组

    # 去重与审计
    stem_hash: Mapped[str] = mapped_column(String(32), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    # 软删除
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关系
    paper_items: Mapped[List["PaperItem"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    mistakes: Mapped[List["StudentMistake"]] = relationship(back_populates="question")

    # ---------- 便捷属性：JSON / 逗号串 与 Python 对象互转 ----------
    @property
    def options_list(self) -> List[dict]:
        """返回 [{'key':'A','text':'...'}, ...]"""
        return _json_loads(self.options, [])

    @options_list.setter
    def options_list(self, value: List[dict]):
        self.options = _json_dumps(value or [])

    @property
    def image_list(self) -> List[str]:
        return _json_loads(self.image_paths, [])

    @image_list.setter
    def image_list(self, value: List[str]):
        self.image_paths = _json_dumps(value or [])

    @property
    def knowledge_list(self) -> List[str]:
        return [x.strip() for x in (self.knowledge or "").split(",") if x.strip()]

    @property
    def tag_list(self) -> List[str]:
        return [x.strip() for x in (self.tags or "").split(",") if x.strip()]

    def __repr__(self) -> str:
        return f"<Question id={self.id} {self.qtype} {self.grade}/{self.chapter}>"


# ============================================================
# 2. 试卷
# ============================================================
class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名试卷")
    subtitle: Mapped[str] = mapped_column(String(200), default="")     # 副标题/说明
    exam_minutes: Mapped[int] = mapped_column(Integer, default=120)    # 考试时长
    total_score: Mapped[int] = mapped_column(Integer, default=0)       # 总分（自动汇总）
    config: Mapped[str] = mapped_column(Text, default="{}")            # 导出排版配置 JSON

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    items: Mapped[List["PaperItem"]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperItem.order_index",
    )

    @property
    def config_dict(self) -> dict:
        return _json_loads(self.config, {})

    @config_dict.setter
    def config_dict(self, value: dict):
        self.config = _json_dumps(value or {})

    def __repr__(self) -> str:
        return f"<Paper id={self.id} {self.title}>"


# ============================================================
# 3. 试卷-题目 关联
# ============================================================
class PaperItem(Base):
    __tablename__ = "paper_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    section_title: Mapped[str] = mapped_column(String(100), default="")  # 大题标题
    order_index: Mapped[int] = mapped_column(Integer, default=0)         # 顺序（全卷唯一）
    score: Mapped[int] = mapped_column(Integer, default=5)               # 本题分值

    paper: Mapped["Paper"] = relationship(back_populates="items")
    question: Mapped["Question"] = relationship(back_populates="paper_items")


# ============================================================
# 4. 学生
# ============================================================
class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), default="", index=True)
    class_name: Mapped[str] = mapped_column(String(50), default="")   # 学校
    grade: Mapped[str] = mapped_column(String(20), default="")        # 年级
    notes: Mapped[str] = mapped_column(Text, default="")              # 备注

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    mistakes: Mapped[List["StudentMistake"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    files: Mapped[List["StudentFile"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Student id={self.id} {self.name}>"


# ============================================================
# 5. 学生错题（必须关联题库题目）
# ============================================================
class StudentMistake(Base):
    __tablename__ = "student_mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    # 按你的要求：必须关联题库题目，所以不可为空
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )

    # 快照，防止题库题目被修改后，历史错题记录变样
    snapshot_stem: Mapped[str] = mapped_column(Text, default="")
    snapshot_answer: Mapped[str] = mapped_column(Text, default="")

    wrong_answer: Mapped[str] = mapped_column(Text, default="")   # 学生当时的错误答案
    error_reason: Mapped[str] = mapped_column(Text, default="")   # 错因分析
    mastery: Mapped[int] = mapped_column(Integer, default=0)      # 0未掌握 ~ 3已掌握

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    student: Mapped["Student"] = relationship(back_populates="mistakes")
    question: Mapped["Question"] = relationship(back_populates="mistakes")
    files: Mapped[List["StudentFile"]] = relationship(
        back_populates="mistake", cascade="all, delete-orphan"
    )


# ============================================================
# 6. 学生图片 / 附件
# ============================================================
class StudentFile(Base):
    __tablename__ = "student_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    # 可挂到某条错题下；为空表示只挂在学生档案下
    mistake_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("student_mistakes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    file_path: Mapped[str] = mapped_column(String(300), default="")   # 相对 data/ 的路径
    file_type: Mapped[str] = mapped_column(String(20), default="image")
    caption: Mapped[str] = mapped_column(String(200), default="")     # 说明文字
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    student: Mapped["Student"] = relationship(back_populates="files")
    mistake: Mapped[Optional["StudentMistake"]] = relationship(back_populates="files")