# -*- coding: utf-8 -*-
"""试卷服务：试卷与题目的增删改查。

试卷草稿在前端以如下结构存在（不落库）：
    {
      "id": None 或 int,
      "title": str, "subtitle": str, "exam_minutes": int,
      "sections": [
        {"sec_id": "...", "title": "一、单选题",
         "items": [{"item_id": "...", "question_id": 12, "score": 5}, ...]},
        ...
      ]
    }
本模块负责把这种结构序列化进 papers + paper_items 两张表。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from src.database import session_scope
from src.models import Paper, PaperItem, Question

from sqlalchemy import delete, func, select

# ------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------
def _compute_total(sections: List[dict]) -> int:
    total = 0
    for sec in sections or []:
        for it in sec.get("items", []):
            try:
                total += int(it.get("score", 0) or 0)
            except (TypeError, ValueError):
                pass
    return total


def _flatten_items(sections: List[dict]) -> List[dict]:
    """把 sections 打平成 PaperItem 需要的字段，附带全卷唯一 order_index。"""
    flat, order = [], 0
    for sec in sections or []:
        title = (sec.get("title") or "").strip()
        for it in sec.get("items", []):
            flat.append({
                "question_id": int(it["question_id"]),
                "section_title": title,
                "order_index": order,
                "score": int(it.get("score", 0) or 0),
            })
            order += 1
    return flat


# ------------------------------------------------------------
# 创建 / 更新
# ------------------------------------------------------------
def create_paper(title: str, subtitle: str, exam_minutes: int,
                 sections: List[dict], config: Optional[dict] = None) -> int:
    with session_scope() as s:
        p = Paper(
            title=(title or "").strip() or "未命名试卷",
            subtitle=(subtitle or "").strip(),
            exam_minutes=int(exam_minutes or 0),
            total_score=_compute_total(sections),
        )
        p.config_dict = config or {}
        s.add(p)
        s.flush()
        for row in _flatten_items(sections):
            s.add(PaperItem(paper_id=p.id, **row))
        return p.id


def update_paper(paper_id: int, title: str, subtitle: str, exam_minutes: int,
                 sections: List[dict], config: Optional[dict] = None) -> bool:
    """整卷覆盖更新：先清空关联，再重建。简单可靠。"""
    with session_scope() as s:
        p = s.get(Paper, paper_id)
        if p is None or p.is_deleted:
            return False
        p.title = (title or "").strip() or "未命名试卷"
        p.subtitle = (subtitle or "").strip()
        p.exam_minutes = int(exam_minutes or 0)
        p.total_score = _compute_total(sections)
        p.updated_at = datetime.now()
        if config is not None:
            p.config_dict = config

        # 清空旧关联，直接走 SQL 避免 ORM 的孤儿判定
        s.execute(delete(PaperItem).where(PaperItem.paper_id == paper_id))
        s.flush()
        for row in _flatten_items(sections):
            s.add(PaperItem(paper_id=paper_id, **row))
        return True


# ------------------------------------------------------------
# 查询
# ------------------------------------------------------------
def list_papers(only_not_deleted: bool = True) -> List[Dict]:
    """返回试卷摘要列表（不加载题目详情）。"""
    with session_scope() as s:
        stmt = select(Paper)
        if only_not_deleted:
            stmt = stmt.where(Paper.is_deleted.is_(False))
        stmt = stmt.order_by(Paper.updated_at.desc(), Paper.id.desc())
        rows = s.scalars(stmt).all()

        result = []
        for p in rows:
            result.append({
                "id": p.id,
                "title": p.title,
                "subtitle": p.subtitle,
                "exam_minutes": p.exam_minutes,
                "total_score": p.total_score,
                "item_count": len(p.items),
                "updated_at": p.updated_at or datetime.now(),
            })
        return result


def get_paper_detail(paper_id: int) -> Optional[Dict]:
    """返回完整结构，供编辑器加载。题目顺序按 order_index 恢复，section 按首次出现顺序。"""
    with session_scope() as s:
        p = s.get(Paper, paper_id)
        if p is None or p.is_deleted:
            return None

        items = sorted(p.items, key=lambda x: x.order_index)
        sections: List[Dict] = []
        current_title = object()  # 用哨兵值，避免跟空字符串混淆
        for it in items:
            if it.section_title != current_title:
                sections.append({"title": it.section_title or "", "items": []})
                current_title = it.section_title
            sections[-1]["items"].append({
                "question_id": it.question_id,
                "score": it.score,
            })

        return {
            "id": p.id,
            "title": p.title,
            "subtitle": p.subtitle,
            "exam_minutes": p.exam_minutes,
            "total_score": p.total_score,
            "config": p.config_dict,
            "sections": sections,
        }


def get_questions_by_ids(ids: List[int]) -> Dict[int, Question]:
    """一次性批量取题目，返回 {id: Question}。供编辑器渲染预览用。"""
    ids = [int(i) for i in (ids or []) if i is not None]
    if not ids:
        return {}
    with session_scope() as s:
        rows = s.scalars(select(Question).where(Question.id.in_(ids))).all()
        result = {}
        for q in rows:
            s.expunge(q)
            result[q.id] = q
        return result


# ------------------------------------------------------------
# 删除 / 还原（第 7 步回收站会用）
# ------------------------------------------------------------
def soft_delete_paper(paper_id: int) -> bool:
    with session_scope() as s:
        p = s.get(Paper, paper_id)
        if p is None or p.is_deleted:
            return False
        p.is_deleted = True
        p.deleted_at = datetime.now()
        return True


def restore_paper(paper_id: int) -> bool:
    with session_scope() as s:
        p = s.get(Paper, paper_id)
        if p is None or not p.is_deleted:
            return False
        p.is_deleted = False
        p.deleted_at = None
        return True


def hard_delete_paper(paper_id: int) -> bool:
    """彻底删除（级联删掉 paper_items）。"""
    with session_scope() as s:
        p = s.get(Paper, paper_id)
        if p is None:
            return False
        s.delete(p)
        return True


def list_deleted_papers() -> List[Dict]:
    with session_scope() as s:
        rows = s.scalars(
            select(Paper).where(Paper.is_deleted.is_(True)).order_by(Paper.deleted_at.desc())
        ).all()
        return [{
            "id": p.id,
            "title": p.title,
            "item_count": len(p.items),
            "deleted_at": p.deleted_at,
        } for p in rows]

# ============================================================
# 回收站（第 7 步）
# ============================================================
def count_deleted_papers() -> int:
    with session_scope() as s:
        return int(s.scalar(
            select(func.count()).select_from(Paper).where(Paper.is_deleted.is_(True))
        ) or 0)


def batch_restore_papers(ids: List[int]) -> int:
    if not ids:
        return 0
    with session_scope() as s:
        rows = s.scalars(
            select(Paper).where(Paper.id.in_(ids), Paper.is_deleted.is_(True))
        ).all()
        for p in rows:
            p.is_deleted = False
            p.deleted_at = None
        return len(rows)


def batch_hard_delete_papers(ids: List[int]) -> int:
    """批量彻底删除试卷（级联删 paper_items）。"""
    if not ids:
        return 0
    with session_scope() as s:
        rows = s.scalars(select(Paper).where(Paper.id.in_(ids))).all()
        for p in rows:
            s.delete(p)
        return len(rows)


def empty_paper_trash() -> int:
    return batch_hard_delete_papers([p["id"] for p in list_deleted_papers()])