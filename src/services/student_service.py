# -*- coding: utf-8 -*-
"""学生档案服务：学生、错题、学习图片。

规则：
- 学生软删除；错题/图片跟随学生一起保留，学生被彻底删除时一并清理。
- 错题必须关联题库题目（按你的要求），同时保存题干/答案快照，
  避免题库题目后续被修改导致历史记录变样。
- 删除错题或彻底删除学生时，一并删除磁盘上的图片文件。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func, or_, select

from src.database import session_scope
from src.models import Question, Student, StudentFile, StudentMistake
from src.utils.file_utils import (STUDENT_FILES_DIR, delete_file_silently,
                                  save_uploaded_image)


# ============================================================
# 学生
# ============================================================
def create_student(name: str, class_name: str = "",
                   grade: str = "", notes: str = "") -> int:
    with session_scope() as s:
        stu = Student(
            name=(name or "").strip(),
            class_name=(class_name or "").strip(),
            grade=(grade or "").strip(),
            notes=(notes or "").strip(),
        )
        s.add(stu)
        s.flush()
        return stu.id


def update_student(sid: int, *, name: Optional[str] = None,
                   class_name: Optional[str] = None,
                   grade: Optional[str] = None,
                   notes: Optional[str] = None) -> bool:
    with session_scope() as s:
        stu = s.get(Student, sid)
        if stu is None or stu.is_deleted:
            return False
        if name is not None:
            stu.name = name.strip()
        if class_name is not None:
            stu.class_name = class_name.strip()
        if grade is not None:
            stu.grade = grade.strip()
        if notes is not None:
            stu.notes = notes.strip()
        stu.updated_at = datetime.now()
        return True


def get_student(sid: int, include_deleted: bool = False) -> Optional[Student]:
    with session_scope() as s:
        stu = s.get(Student, sid)
        if stu is None:
            return None
        if stu.is_deleted and not include_deleted:
            return None
        s.expunge(stu)
        return stu


def list_students(keyword: str = "", class_name: str = "", grade: str = "",
                  include_deleted: bool = False) -> List[Dict]:
    """返回学生摘要列表。include_deleted=True 时只返回已删除的学生。"""
    with session_scope() as s:
        stmt = select(Student)
        if include_deleted:
            stmt = stmt.where(Student.is_deleted.is_(True))
        else:
            stmt = stmt.where(Student.is_deleted.is_(False))
        if class_name:
            stmt = stmt.where(Student.class_name == class_name)
        if grade:
            stmt = stmt.where(Student.grade == grade)
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(
                Student.name.like(kw),
                Student.class_name.like(kw),
                Student.notes.like(kw),
            ))
        stmt = stmt.order_by(Student.name.asc(), Student.id.asc())
        rows = s.scalars(stmt).all()

        result = []
        for stu in rows:
            result.append({
                "id": stu.id,
                "name": stu.name,
                "class_name": stu.class_name,
                "grade": stu.grade,
                "notes": stu.notes,
                "mistake_count": len(stu.mistakes),
                "file_count": len(stu.files),
                "updated_at": stu.updated_at,
                "is_deleted": stu.is_deleted,
            })
        return result


def soft_delete_student(sid: int) -> bool:
    with session_scope() as s:
        stu = s.get(Student, sid)
        if stu is None or stu.is_deleted:
            return False
        stu.is_deleted = True
        stu.deleted_at = datetime.now()
        return True


def restore_student(sid: int) -> bool:
    with session_scope() as s:
        stu = s.get(Student, sid)
        if stu is None or not stu.is_deleted:
            return False
        stu.is_deleted = False
        stu.deleted_at = None
        return True


def hard_delete_student(sid: int) -> bool:
    """彻底删除学生（连同错题、图片记录）。磁盘图片一并清理。"""
    with session_scope() as s:
        stu = s.get(Student, sid)
        if stu is None:
            return False
        paths: List[str] = []
        for f in stu.files:
            paths.append(f.file_path)
        for m in stu.mistakes:
            for f in m.files:
                paths.append(f.file_path)
        s.delete(stu)

    for p in paths:
        delete_file_silently(p)
    return True


def get_all_classes() -> List[str]:
    with session_scope() as s:
        rows = s.scalars(
            select(Student.class_name).where(Student.is_deleted.is_(False)).distinct()
        ).all()
        return sorted({r for r in rows if r})


# ============================================================
# 错题
# ============================================================
def add_mistake(student_id: int, question_id: int, wrong_answer: str = "",
                error_reason: str = "", mastery: int = 0) -> int:
    """添加一条错题。同一学生对同一题目只允许一条记录。"""
    with session_scope() as s:
        q = s.get(Question, question_id)
        if q is None:
            raise ValueError(f"题目 #{question_id} 不存在")
        exists = s.scalar(
            select(func.count()).select_from(StudentMistake).where(
                StudentMistake.student_id == student_id,
                StudentMistake.question_id == question_id,
            )
        ) or 0
        if exists:
            raise ValueError(f"该学生已有题目 #{question_id} 的错题记录")

        m = StudentMistake(
            student_id=student_id,
            question_id=question_id,
            snapshot_stem=q.stem or "",
            snapshot_answer=q.answer or "",
            wrong_answer=(wrong_answer or "").strip(),
            error_reason=(error_reason or "").strip(),
            mastery=min(3, max(0, int(mastery or 0))),
        )
        s.add(m)
        s.flush()
        return m.id


def update_mistake(mid: int, *, wrong_answer: Optional[str] = None,
                   error_reason: Optional[str] = None,
                   mastery: Optional[int] = None) -> bool:
    with session_scope() as s:
        m = s.get(StudentMistake, mid)
        if m is None:
            return False
        if wrong_answer is not None:
            m.wrong_answer = wrong_answer.strip()
        if error_reason is not None:
            m.error_reason = error_reason.strip()
        if mastery is not None:
            m.mastery = min(3, max(0, int(mastery)))
        m.updated_at = datetime.now()
        return True


def delete_mistake(mid: int) -> bool:
    with session_scope() as s:
        m = s.get(StudentMistake, mid)
        if m is None:
            return False
        paths = [f.file_path for f in m.files]
        s.delete(m)
    for p in paths:
        delete_file_silently(p)
    return True


def list_mistakes(student_id: int) -> List[Dict]:
    """返回该学生的错题列表（含关联图片信息）。"""
    with session_scope() as s:
        rows = s.scalars(
            select(StudentMistake)
            .where(StudentMistake.student_id == student_id)
            .order_by(StudentMistake.created_at.desc(), StudentMistake.id.desc())
        ).all()
        result = []
        for m in rows:
            result.append({
                "id": m.id,
                "question_id": m.question_id,
                "snapshot_stem": m.snapshot_stem,
                "snapshot_answer": m.snapshot_answer,
                "wrong_answer": m.wrong_answer,
                "error_reason": m.error_reason,
                "mastery": m.mastery,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
                "files": [
                    {"id": f.id, "path": f.file_path, "caption": f.caption}
                    for f in m.files
                ],
            })
        return result


# ============================================================
# 学习图片
# ============================================================
def add_student_file(student_id: int, uploaded_file, caption: str = "",
                     mistake_id: Optional[int] = None) -> int:
    """保存上传的图片并入库。返回新记录 id。"""
    rel = save_uploaded_image(uploaded_file, target_dir=STUDENT_FILES_DIR)
    with session_scope() as s:
        f = StudentFile(
            student_id=student_id,
            mistake_id=mistake_id,
            file_path=rel,
            file_type="image",
            caption=(caption or "").strip(),
        )
        s.add(f)
        s.flush()
        return f.id


def delete_student_file(file_id: int) -> bool:
    with session_scope() as s:
        f = s.get(StudentFile, file_id)
        if f is None:
            return False
        rel = f.file_path
        s.delete(f)
    delete_file_silently(rel)
    return True


def list_student_files(student_id: int,
                       mistake_id: Optional[int] = None) -> List[Dict]:
    """学生级图片列表。mistake_id=None 时返回所有图片。"""
    with session_scope() as s:
        stmt = select(StudentFile).where(StudentFile.student_id == student_id)
        if mistake_id is not None:
            stmt = stmt.where(StudentFile.mistake_id == mistake_id)
        stmt = stmt.order_by(StudentFile.created_at.desc())
        rows = s.scalars(stmt).all()
        return [{
            "id": f.id,
            "path": f.file_path,
            "caption": f.caption,
            "mistake_id": f.mistake_id,
            "created_at": f.created_at,
        } for f in rows]