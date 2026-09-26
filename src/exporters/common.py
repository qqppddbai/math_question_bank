# -*- coding: utf-8 -*-
"""导出器共享的数据结构。

流程：
    DB (papers + paper_items + questions)
        ↓ paper_service.get_paper_detail / get_questions_by_ids
        ↓ build_paper_view()
    PaperView → 各格式 exporter → str / 文件
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import base64
import mimetypes
from pathlib import Path

@dataclass
class ItemView:
    number: int             # 全卷连续编号，从 1 开始
    score: int
    question_id: int
    qtype: str
    stem: str
    options: List[dict]     # [{'key':'A','text':'...'}, ...]
    answer: str
    analysis: str
    image_list: List[str] = field(default_factory=list)
    missing: bool = False   # 题目已从题库移除，或从未取到


@dataclass
class SectionView:
    title: str
    items: List[ItemView] = field(default_factory=list)

    @property
    def total_score(self) -> int:
        return sum(it.score for it in self.items)

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass
class PaperView:
    title: str
    subtitle: str
    exam_minutes: int
    total_score: int
    sections: List[SectionView]
    paper_id: Optional[int] = None


def build_paper_view(paper_detail: Dict, questions_map: Dict[int, object]) -> PaperView:
    """把 DB 结构转成导出视图。"""
    number = 0
    sections: List[SectionView] = []
    for si, sec in enumerate(paper_detail.get("sections", [])):
        sec_title = (sec.get("title") or "").strip() or f"大题{si + 1}"
        view = SectionView(title=sec_title)
        for it in sec.get("items", []):
            number += 1
            qid = int(it["question_id"])
            q = questions_map.get(qid)
            if q is None:
                view.items.append(ItemView(
                    number=number,
                    score=int(it.get("score", 0) or 0),
                    question_id=qid,
                    qtype="",
                    stem=f"（题目 #{qid} 已从题库中移除）",
                    options=[],
                    answer="",
                    analysis="",
                    image_list=[],
                    missing=True,
                ))
                continue
            view.items.append(ItemView(
                number=number,
                score=int(it.get("score", 0) or 0),
                question_id=qid,
                qtype=q.qtype or "",
                stem=q.stem or "",
                options=list(q.options_list or []),
                answer=q.answer or "",
                analysis=q.analysis or "",
                image_list=list(q.image_list or []),
            ))
        sections.append(view)

    return PaperView(
        title=paper_detail.get("title") or "未命名试卷",
        subtitle=paper_detail.get("subtitle") or "",
        exam_minutes=int(paper_detail.get("exam_minutes") or 0),
        total_score=int(paper_detail.get("total_score") or 0),
        sections=sections,
        paper_id=paper_detail.get("id"),
    )

# ============================================================
# 图片辅助
# ============================================================
def resolve_image_path(rel: str) -> Path | None:
    """相对 data/ 的路径 → 绝对 Path；文件不存在返回 None。"""
    if not rel:
        return None
    from src.config import DATA_DIR
    p = DATA_DIR / rel
    return p if p.is_file() else None


def image_to_data_uri(rel: str) -> str | None:
    """读取图片并转成 data:image/...;base64,...，供 HTML / Markdown 内嵌。
    文件缺失或读取失败时返回 None。
    """
    p = resolve_image_path(rel)
    if p is None:
        return None
    mime, _ = mimetypes.guess_type(p.name)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"