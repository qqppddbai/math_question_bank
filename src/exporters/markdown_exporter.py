# -*- coding: utf-8 -*-
"""Markdown 导出：公式保留 LaTeX 原文，图片以 base64 内嵌。"""
from __future__ import annotations

from src.exporters.common import PaperView, image_to_data_uri


def _ml(text: str) -> str:
    """多行文本 → markdown 硬换行。"""
    return (text or "").replace("\r\n", "\n").replace("\n", "  \n")


def _section_meta(sec) -> str:
    if not sec.items:
        return ""
    scores = {it.score for it in sec.items}
    if len(scores) == 1:
        s = next(iter(scores))
        return f"（共 {sec.count} 题，每题 {s} 分，共 {sec.total_score} 分）"
    return f"（共 {sec.count} 题，共 {sec.total_score} 分）"


def _emit_images(lines, image_list):
    """把图片 base64 内嵌到 markdown。"""
    for rel in image_list or []:
        uri = image_to_data_uri(rel)
        if uri:
            lines.append(f"![]({uri})")
            lines.append("")
        else:
            lines.append("_［图片丢失］_")
            lines.append("")


def export_markdown(view: PaperView, *, include_answer: bool = True,
                    include_analysis: bool = True, answers_at_end: bool = False,
                    include_images: bool = True) -> str:
    lines = []
    lines.append(f"# {view.title}")
    lines.append("")
    if view.subtitle:
        lines.append(f"*{view.subtitle}*")
        lines.append("")

    meta = []
    if view.exam_minutes:
        meta.append(f"考试时间：{view.exam_minutes} 分钟")
    meta.append(f"满分：{view.total_score} 分")
    lines.append("　".join(meta))
    lines.append("")
    lines.append("姓名：__________　学校：__________　得分：__________")
    lines.append("")
    lines.append("---")
    lines.append("")

    for sec in view.sections:
        lines.append(f"## {sec.title}")
        lines.append("")
        if meta_line := _section_meta(sec):
            lines.append(meta_line)
            lines.append("")

        for it in sec.items:
            lines.append(f"**{it.number}.**（{it.score} 分） {_ml(it.stem)}")
            lines.append("")

            if include_images and it.image_list:
                _emit_images(lines, it.image_list)

            for o in it.options:
                text = (o.get("text") or "").strip()
                if not text:
                    continue
                lines.append(f"{o.get('key', '')}. {_ml(text)}")
                lines.append("")

            if not answers_at_end and (include_answer or include_analysis):
                if include_answer and it.answer:
                    lines.append(f"> **答案：** {_ml(it.answer)}")
                if include_analysis and it.analysis:
                    lines.append(f"> **解析：** {_ml(it.analysis)}")
                if it.answer or it.analysis:
                    lines.append("")

    if answers_at_end and (include_answer or include_analysis):
        lines.append("---")
        lines.append("")
        lines.append("# 参考答案与解析")
        lines.append("")
        for sec in view.sections:
            lines.append(f"## {sec.title}")
            lines.append("")
            for it in sec.items:
                lines.append(f"**{it.number}.**")
                if include_answer and it.answer:
                    lines.append(f"答案：{_ml(it.answer)}")
                if include_analysis and it.analysis:
                    lines.append(f"解析：{_ml(it.analysis)}")
                lines.append("")

    return "\n".join(lines)