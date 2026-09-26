# -*- coding: utf-8 -*-
"""题目服务：所有对 questions 表的读写都走这里。

注意：返回的 Question 对象在 session 关闭后仍然可以访问标量属性和
@property 计算属性（因 expire_on_commit=False），但**不要再访问关系属性**。
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from typing import Dict, List, Optional
from sqlalchemy import func, or_, select

from src.database import session_scope
from src.models import PaperItem, Question
from src.utils.options_parser import normalize_options

from datetime import date, datetime, time

# ------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------
def _normalize_stem_for_hash(stem: str) -> str:
    """去除所有空白后做 MD5，避免因空格/换行差异导致重复。"""
    s = "".join((stem or "").split())
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _apply_fields(q: Question, data: dict) -> None:
    """把 data dict 写入 Question 对象。"""
    for field in ("grade", "chapter", "knowledge", "qtype",
                  "source", "tags", "stem", "answer", "analysis"):
        if field in data:
            setattr(q, field, (data[field] or "").strip() if isinstance(data[field], str) else "")

    if "difficulty" in data:
        try:
            d = int(data["difficulty"])
        except (TypeError, ValueError):
            d = 3
        q.difficulty = min(5, max(1, d))

    if "options_list" in data:
        q.options_list = normalize_options(data["options_list"])

    if "image_list" in data:
        q.image_list = list(data["image_list"] or [])

    q.stem_hash = _normalize_stem_for_hash(q.stem)


# ------------------------------------------------------------
# 增删改查
# ------------------------------------------------------------
def create_question(data: dict) -> int:
    """新增题目，返回新题目 id。"""
    with session_scope() as s:
        q = Question()
        _apply_fields(q, data)
        s.add(q)
        s.flush()
        return q.id


def update_question(qid: int, data: dict) -> bool:
    """更新题目；题目不存在或被软删时返回 False。"""
    with session_scope() as s:
        q = s.get(Question, qid)
        if q is None or q.is_deleted:
            return False
        _apply_fields(q, data)
        q.updated_at = datetime.now()
        return True


def get_question(qid: int, include_deleted: bool = False) -> Optional[Question]:
    """按 id 取单题。"""
    with session_scope() as s:
        q = s.get(Question, qid)
        if q is None:
            return None
        if q.is_deleted and not include_deleted:
            return None
        # 主动 expunge，脱离 session 后仍可安全读取标量属性
        s.expunge(q)
        return q


def list_questions(
    keyword: str = "",
    qtype: str = "",
    grade: str = "",
    chapter: str = "",
    difficulty: Optional[int] = None,
    only_not_deleted: bool = True,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Question]:
    """按条件列出题目（按更新时间倒序）。"""
    with session_scope() as s:
        stmt = select(Question)
        if only_not_deleted:
            stmt = stmt.where(Question.is_deleted.is_(False))
        if qtype:
            stmt = stmt.where(Question.qtype == qtype)
        if grade:
            stmt = stmt.where(Question.grade == grade)
        if chapter:
            stmt = stmt.where(Question.chapter.like(f"%{chapter}%"))
        if difficulty:
            stmt = stmt.where(Question.difficulty == difficulty)
        if keyword:
            kw = f"%{keyword}%"
            stmt = stmt.where(or_(
                Question.stem.like(kw),
                Question.answer.like(kw),
                Question.analysis.like(kw),
                Question.source.like(kw),
                Question.tags.like(kw),
                Question.knowledge.like(kw),
            ))
        stmt = stmt.order_by(Question.updated_at.desc(), Question.id.desc())
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)

        rows = s.scalars(stmt).all()
        for q in rows:
            s.expunge(q)
        return list(rows)


def count_questions(
    keyword: str = "",
    qtype: str = "",
    grade: str = "",
    chapter: str = "",
    difficulty: Optional[int] = None,
    only_not_deleted: bool = True,
) -> int:
    """统计符合条件的题目数量（配合分页）。"""
    with session_scope() as s:
        stmt = select(func.count()).select_from(Question)
        if only_not_deleted:
            stmt = stmt.where(Question.is_deleted.is_(False))
        if qtype:
            stmt = stmt.where(Question.qtype == qtype)
        if grade:
            stmt = stmt.where(Question.grade == grade)
        if chapter:
            stmt = stmt.where(Question.chapter.like(f"%{chapter}%"))
        if difficulty:
            stmt = stmt.where(Question.difficulty == difficulty)
        if keyword:
            kw = f"%{keyword}%"
            stmt = stmt.where(or_(
                Question.stem.like(kw),
                Question.answer.like(kw),
                Question.analysis.like(kw),
                Question.source.like(kw),
                Question.tags.like(kw),
                Question.knowledge.like(kw),
            ))
        return int(s.scalar(stmt) or 0)


def soft_delete_question(qid: int) -> bool:
    """软删除：进回收站。"""
    with session_scope() as s:
        q = s.get(Question, qid)
        if q is None or q.is_deleted:
            return False
        q.is_deleted = True
        q.deleted_at = datetime.now()
        return True


def restore_question(qid: int) -> bool:
    """从回收站还原。"""
    with session_scope() as s:
        q = s.get(Question, qid)
        if q is None or not q.is_deleted:
            return False
        q.is_deleted = False
        q.deleted_at = None
        return True


def hard_delete_question(qid: int) -> bool:
    """彻底删除（回收站里使用）。若已被试卷引用则拒绝。"""
    with session_scope() as s:
        q = s.get(Question, qid)
        if q is None:
            return False
        used = s.scalar(
            select(func.count()).select_from(PaperItem).where(PaperItem.question_id == qid)
        ) or 0
        if used:
            # 试卷引用了这道题，直接抛出让 UI 层提示老师
            raise RuntimeError(f"该题目已被 {used} 份试卷引用，请先从试卷中移除后再彻底删除")
        s.delete(q)
        return True


def find_duplicates_by_stem(stem: str) -> List[int]:
    """按题干内容查找重复题目的 id 列表（供导入查重用）。"""
    h = _normalize_stem_for_hash(stem)
    if not h:
        return []
    with session_scope() as s:
        rows = s.scalars(
            select(Question.id).where(
                Question.stem_hash == h, Question.is_deleted.is_(False)
            )
        ).all()
        return list(rows)


def get_all_chapters() -> List[str]:
    """返回题库中已用过的章节名，去重且排序。"""
    with session_scope() as s:
        rows = s.scalars(
            select(Question.chapter).where(Question.is_deleted.is_(False)).distinct()
        ).all()
        return sorted({r for r in rows if r})


def get_all_sources() -> List[str]:
    """返回题库中已用过的来源，供筛选下拉框使用。"""
    with session_scope() as s:
        rows = s.scalars(
            select(Question.source).where(Question.is_deleted.is_(False)).distinct()
        ).all()
        return sorted({r for r in rows if r})

# ============================================================
# 高级搜索（第 3 步）
# ============================================================
def _apply_search_filters(
    stmt,
    keyword: str = "",
    qtypes: Optional[List[str]] = None,
    grades: Optional[List[str]] = None,
    chapters: Optional[List[str]] = None,
    difficulties: Optional[List[int]] = None,
    sources: Optional[List[str]] = None,
    knowledge_list: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    only_not_deleted: bool = True,
):
    """把搜索条件应用到 select 语句。搜索/计数共用，避免条件重复写两遍。"""
    if only_not_deleted:
        stmt = stmt.where(Question.is_deleted.is_(False))

    if qtypes:
        stmt = stmt.where(Question.qtype.in_(qtypes))
    if grades:
        stmt = stmt.where(Question.grade.in_(grades))
    if chapters:
        stmt = stmt.where(Question.chapter.in_(chapters))
    if difficulties:
        stmt = stmt.where(Question.difficulty.in_(difficulties))
    if sources:
        stmt = stmt.where(Question.source.in_(sources))

    # 知识点 / 标签：逗号分隔字符串，多选用 OR + LIKE
    if knowledge_list:
        conds = [Question.knowledge.like(f"%{k}%") for k in knowledge_list if k.strip()]
        if conds:
            stmt = stmt.where(or_(*conds))
    if tags:
        conds = [Question.tags.like(f"%{t}%") for t in tags if t.strip()]
        if conds:
            stmt = stmt.where(or_(*conds))

    # 时间范围
    if created_from is not None:
        stmt = stmt.where(Question.created_at >= datetime.combine(created_from, time.min))
    if created_to is not None:
        stmt = stmt.where(Question.created_at <= datetime.combine(created_to, time.max))

    # 关键词：跨多个字段模糊匹配
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(
            Question.stem.like(kw),
            Question.answer.like(kw),
            Question.analysis.like(kw),
            Question.source.like(kw),
            Question.tags.like(kw),
            Question.knowledge.like(kw),
            Question.chapter.like(kw),
        ))
    return stmt


_ORDER_MAP = {
    "updated_desc":    (Question.updated_at.desc(), Question.id.desc()),
    "updated_asc":     (Question.updated_at.asc(),  Question.id.asc()),
    "created_desc":    (Question.created_at.desc(), Question.id.desc()),
    "created_asc":     (Question.created_at.asc(),  Question.id.asc()),
    "difficulty_desc": (Question.difficulty.desc(), Question.id.desc()),
    "difficulty_asc":  (Question.difficulty.asc(),  Question.id.asc()),
}


def search_questions(
    keyword: str = "",
    qtypes: Optional[List[str]] = None,
    grades: Optional[List[str]] = None,
    chapters: Optional[List[str]] = None,
    difficulties: Optional[List[int]] = None,
    sources: Optional[List[str]] = None,
    knowledge_list: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    order_by: str = "updated_desc",
    only_not_deleted: bool = True,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Question]:
    """多条件搜索，返回题目列表。"""
    with session_scope() as s:
        stmt = select(Question)
        stmt = _apply_search_filters(
            stmt, keyword=keyword, qtypes=qtypes, grades=grades,
            chapters=chapters, difficulties=difficulties, sources=sources,
            knowledge_list=knowledge_list, tags=tags,
            created_from=created_from, created_to=created_to,
            only_not_deleted=only_not_deleted,
        )
        stmt = stmt.order_by(*_ORDER_MAP.get(order_by, _ORDER_MAP["updated_desc"]))
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)

        rows = s.scalars(stmt).all()
        for q in rows:
            s.expunge(q)
        return list(rows)


def count_search_questions(
    keyword: str = "",
    qtypes: Optional[List[str]] = None,
    grades: Optional[List[str]] = None,
    chapters: Optional[List[str]] = None,
    difficulties: Optional[List[int]] = None,
    sources: Optional[List[str]] = None,
    knowledge_list: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    created_from: Optional[date] = None,
    created_to: Optional[date] = None,
    only_not_deleted: bool = True,
) -> int:
    """与 search_questions 条件一致的总数。"""
    with session_scope() as s:
        stmt = select(func.count()).select_from(Question)
        stmt = _apply_search_filters(
            stmt, keyword=keyword, qtypes=qtypes, grades=grades,
            chapters=chapters, difficulties=difficulties, sources=sources,
            knowledge_list=knowledge_list, tags=tags,
            created_from=created_from, created_to=created_to,
            only_not_deleted=only_not_deleted,
        )
        return int(s.scalar(stmt) or 0)


# ============================================================
# 字典汇总（供筛选下拉框使用）
# ============================================================
def get_all_knowledge() -> List[str]:
    """题库里出现过的所有知识点（去重排序）。"""
    with session_scope() as s:
        rows = s.scalars(
            select(Question.knowledge).where(Question.is_deleted.is_(False))
        ).all()
    bag = set()
    for r in rows:
        for item in (r or "").split(","):
            item = item.strip()
            if item:
                bag.add(item)
    return sorted(bag)


def get_all_tags() -> List[str]:
    """题库里出现过的所有标签（去重排序）。"""
    with session_scope() as s:
        rows = s.scalars(
            select(Question.tags).where(Question.is_deleted.is_(False))
        ).all()
    bag = set()
    for r in rows:
        for item in (r or "").split(","):
            item = item.strip()
            if item:
                bag.add(item)
    return sorted(bag)


# ============================================================
# 批量操作（第 3 步）
# ============================================================
def batch_soft_delete(ids: List[int]) -> int:
    """批量软删除，返回实际删除条数。"""
    if not ids:
        return 0
    now = datetime.now()
    with session_scope() as s:
        rows = s.scalars(
            select(Question).where(
                Question.id.in_(ids), Question.is_deleted.is_(False)
            )
        ).all()
        for q in rows:
            q.is_deleted = True
            q.deleted_at = now
        return len(rows)


def batch_add_tags(ids: List[int], new_tags: List[str]) -> int:
    """批量追加标签（已存在的自动忽略）。返回受影响条数。"""
    new_tags = [t.strip() for t in new_tags if t and t.strip()]
    if not ids or not new_tags:
        return 0
    affected = 0
    with session_scope() as s:
        rows = s.scalars(select(Question).where(Question.id.in_(ids))).all()
        for q in rows:
            existing = set(q.tag_list)
            merged = list(existing | set(new_tags))
            q.tags = ",".join(merged)
            affected += 1
    return affected


def batch_remove_tags(ids: List[int], remove_tags: List[str]) -> int:
    """批量移除指定标签。返回受影响条数。"""
    remove_set = {t.strip() for t in remove_tags if t and t.strip()}
    if not ids or not remove_set:
        return 0
    affected = 0
    with session_scope() as s:
        rows = s.scalars(select(Question).where(Question.id.in_(ids))).all()
        for q in rows:
            remain = [t for t in q.tag_list if t not in remove_set]
            q.tags = ",".join(remain)
            affected += 1
    return affected


def batch_update_category(ids: List[int], *, grade: str = None,
                          chapter: str = None) -> int:
    """批量修改年级/章节。只改传入的字段（空字符串视为清空）。"""
    if not ids:
        return 0
    with session_scope() as s:
        rows = s.scalars(select(Question).where(Question.id.in_(ids))).all()
        for q in rows:
            if grade is not None:
                q.grade = grade
            if chapter is not None:
                q.chapter = chapter
        return len(rows)

# ============================================================
# 回收站（第 7 步）
# ============================================================
def list_deleted_questions() -> List[Question]:
    """列出回收站里的题目，最近删除的排前。"""
    with session_scope() as s:
        rows = s.scalars(
            select(Question)
            .where(Question.is_deleted.is_(True))
            .order_by(Question.deleted_at.desc(), Question.id.desc())
        ).all()
        for q in rows:
            s.expunge(q)
        return list(rows)


def count_deleted_questions() -> int:
    with session_scope() as s:
        return int(s.scalar(
            select(func.count()).select_from(Question).where(Question.is_deleted.is_(True))
        ) or 0)


def batch_restore_questions(ids: List[int]) -> int:
    """批量还原。返回实际还原数。"""
    if not ids:
        return 0
    with session_scope() as s:
        rows = s.scalars(
            select(Question).where(
                Question.id.in_(ids), Question.is_deleted.is_(True)
            )
        ).all()
        for q in rows:
            q.is_deleted = False
            q.deleted_at = None
        return len(rows)


def batch_hard_delete_questions(ids: List[int]) -> Dict[str, int]:
    """批量彻底删除。被试卷引用的题目跳过，返回统计数据。

    返回：{"deleted": n, "blocked": m, "blocked_ids": [...]}
    """
    if not ids:
        return {"deleted": 0, "blocked": 0, "blocked_ids": []}

    deleted = 0
    blocked_ids: List[int] = []
    with session_scope() as s:
        rows = s.scalars(select(Question).where(Question.id.in_(ids))).all()
        for q in rows:
            used = s.scalar(
                select(func.count()).select_from(PaperItem)
                .where(PaperItem.question_id == q.id)
            ) or 0
            if used:
                blocked_ids.append(q.id)
                continue
            s.delete(q)
            deleted += 1

    return {"deleted": deleted, "blocked": len(blocked_ids), "blocked_ids": blocked_ids}


def empty_question_trash() -> Dict[str, int]:
    """清空题目回收站：能删的都删，被引用的跳过。"""
    ids = [q.id for q in list_deleted_questions()]
    return batch_hard_delete_questions(ids)