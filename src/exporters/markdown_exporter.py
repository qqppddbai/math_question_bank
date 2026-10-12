# -*- coding: utf-8 -*-
"""Markdown 导出：公式保留 LaTeX 原文，图片以 base64 内嵌。"""
from __future__ import annotations

from src.exporters.common import (PaperView, image_to_data_uri,
                                  text_image_blocks)


def _ml(text: str) -> str:
    """多行文本 → markdown 硬换行。"""
    return (text or "").replace("\r\n", "\n").replace("\n", "  \n")


def _section_meta(sec) -> str:
    if not sec.items:
        return ""
    return f"（共 {sec.count} 题）"


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


def _emit_mixed(lines, text, images):
    """正文（题干 / 解析）：按 ![[img:N]] 把文字和图片交替排出来。

    Markdown 天生支持图文混排，所以顺序输出即可，图片就出现在标记位置。
    没有标记时等价于「文字 + 末尾图片」，与改动前一致。
    """
    for block in text_image_blocks(text, images):
        if block["type"] == "text":
            lines.append(_ml(block["text"]))
            lines.append("")
        elif block.get("path"):
            _emit_images(lines, [block["path"]])
        else:
            lines.append(f"_［配图 {block['number']} 不存在：请检查 "
                         f"![[img:{block['number']}]] 的序号］_")
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

    # 说明：按需求不显示考试时间 / 满分 / 姓名班级得分，也不显示每题分值。
    lines.append("---")
    lines.append("")

    for sec in view.sections:
        lines.append(f"## {sec.title}")
        lines.append("")
        if meta_line := _section_meta(sec):
            lines.append(meta_line)
            lines.append("")

        for it in sec.items:
            if include_images and (it.image_list or it.analysis_images):
                lines.append(f"**{it.number}.**")
                lines.append("")
                _emit_mixed(lines, it.stem, it.image_list)
            else:
                lines.append(f"**{it.number}.** {_ml(it.stem)}")
                lines.append("")

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
                    if include_images and it.analysis_images:
                        lines.append("")
                        _emit_mixed(lines, it.analysis, it.analysis_images)
                    else:
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
                    if include_images and it.analysis_images:
                        lines.append("")
                        _emit_mixed(lines, it.analysis, it.analysis_images)
                    else:
                        lines.append(f"解析：{_ml(it.analysis)}")
                lines.append("")

    return "\n".join(lines)