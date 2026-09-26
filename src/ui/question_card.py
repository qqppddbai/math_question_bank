# -*- coding: utf-8 -*-
"""题目卡片公共渲染层。

「题目管理」「搜索筛选」「手动组卷」三个页面都通过这里渲染题目，
保证三处的题目展示完全一致（版式 + 宋体六号字号）。

字号来源：src/config.py 的 UI_QUESTION_FONT_SIZE；
全局 CSS 在 app.py 里，用 st.container(key="qdisp_...") 生成的选择器定位。
各页面的按钮不放在 qdisp 容器内，因此不受题目字号影响。
"""
from __future__ import annotations

import streamlit as st

from src.config import (CHOICE_TYPES, QUESTION_FONT_STACK,
                        UI_QUESTION_FONT_SIZE)
from src.utils import file_utils
from src.utils.latex import md

THUMB_WIDTH = 140   # 卡片内缩略图宽度（像素）。想更大就改成 180、220

# 卡片内使用的紧凑分割线（上下 margin 各 4px，比 st.divider() 紧凑很多）
TIGHT_HR = (
    '<hr style="margin:4px 0 8px 0;border:none;'
    'border-top:1px solid #e0e0e0;">'
)

# 卡片元信息样式（字号与题目正文统一）
META_FONT_SIZE = UI_QUESTION_FONT_SIZE
META_LABEL_COLOR = "#333"        # 标签颜色（深色）
META_VALUE_COLOR = "#09AB3B"     # 内容颜色（浅绿色）
META_LINE_HEIGHT = "1.9"         # 行高，越小越紧凑
META_ITEM_GAP = "16px"           # 两个条目之间的水平间距


def meta_block(items) -> str:
    """把 [(标签, 内容), ...] 渲染成紧凑的一整块。

    - 标签深色，内容浅绿，字号与题目正文一致
    - 条目用 inline-block，容器不够宽时自动换行
    """
    parts = []
    for label, value in items:
        safe = (value or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(
            f"<span style='display:inline-block;"
            f"margin-right:{META_ITEM_GAP};white-space:nowrap;'>"
            f"<span style='font-weight:600;color:{META_LABEL_COLOR};'>{label}</span>"
            f"<span style='color:{META_VALUE_COLOR};'>　{safe}</span>"
            f"</span>"
        )
    return (
        f"<div style='font-size:{META_FONT_SIZE};"
        f"font-family:{QUESTION_FONT_STACK};"
        f"line-height:{META_LINE_HEIGHT};'>"
        + "".join(parts) +
        "</div>"
    )


def difficulty_stars(q) -> str:
    """难度星标，如 ★★★☆☆。"""
    return "★" * q.difficulty + "☆" * (5 - q.difficulty)


def standard_meta_items(q, *, with_grade: bool = False):
    """题目卡片统一的元信息条目。"""
    knowledge_txt = "、".join(q.knowledge_list) if q.knowledge_list else "—"
    tags_txt = "、".join(q.tag_list) if q.tag_list else "—"
    items = [
        ("来源：", q.source),
        ("难度：", difficulty_stars(q)),
    ]
    if with_grade:
        items.append(("年级：", q.grade))
    items += [
        ("章节：", q.chapter),
        ("知识点：", knowledge_txt),
        ("标签：", tags_txt),
    ]
    return items


def render_thumbnails(image_list, key_prefix: str = "img"):
    """一排小缩略图，无点击放大功能。"""
    if not image_list:
        return
    cols = st.columns(min(6, len(image_list)))
    for i, rel in enumerate(image_list):
        with cols[i % len(cols)]:
            p = file_utils.abs_path(rel)
            if p.is_file():
                st.image(str(p), width=THUMB_WIDTH)
            else:
                st.caption("图片已丢失")


def render_body(q, *, key: str, meta_items=None, with_grade: bool = False,
                thumb_prefix: str = "card"):
    """题目正文：元信息 + 分割线 + 题干 + 选项 + 配图。

    整体包在 st.container(key=f"qdisp_{key}_{q.id}") 里，
    app.py 的全局 CSS 据此把这一块统一成宋体六号。
    调用方请把按钮放在这个容器外面，避免按钮字号被一起改掉。
    """
    if meta_items is None:
        meta_items = standard_meta_items(q, with_grade=with_grade)

    with st.container(key=f"qdisp_{key}_{q.id}"):
        st.markdown(meta_block(meta_items), unsafe_allow_html=True)
        st.markdown(TIGHT_HR, unsafe_allow_html=True)
        st.markdown(md(q.stem) or "_（空题干）_")

        # 选项（选择题才显示）
        if q.qtype in CHOICE_TYPES and q.options_list:
            for o in q.options_list:
                text = (o.get("text", "") or "").strip()
                if text:
                    st.markdown(f"**{o.get('key', '')}．** " + md(text))

        # 配图（紧跟题干最后一行之后）
        render_thumbnails(q.image_list, key_prefix=thumb_prefix)


def render_answer_expander(q, *, key: str, expanded: bool = False,
                           label: str = "📖 查看答案与解析"):
    """卡片下方的「答案与解析」折叠面板。"""
    with st.expander(label, expanded=expanded):
        with st.container(key=f"qdisp_{key}_ans_{q.id}"):
            st.markdown("**答案**")
            st.markdown(md(q.answer) or "_略_")
            st.markdown("**解析**")
            st.markdown(md(q.analysis) or "_略_")
