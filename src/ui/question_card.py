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

from src.config import (CHOICE_TYPES, DEFAULT_IMAGE_WIDTH_PX,
                        QUESTION_FONT_STACK, UI_QUESTION_FONT_SIZE)
from src.utils import file_utils
from src.utils.latex import md
from src.utils.rich_text import markdown_to_blocks

THUMB_WIDTH = 140        # 编辑器里的缩略图宽度（像素）
# 正文里插在文字之间的图片默认宽度（像素）。
# 数值统一在 src/config.py 的 DEFAULT_IMAGE_WIDTH_PX 里改，这里只是引用。
# 标记里写了宽度的（![[img:1|300]]）优先用标记里的值。
BLOCK_IMAGE_WIDTH = DEFAULT_IMAGE_WIDTH_PX

# 正文里插图用的 class（样式定义在 app.py 的全局 CSS 里，跟着题目字号走）
IMAGE_WRAP_CLASS = "qimg-wrap"
IMAGE_CLASS = "qimg"

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
    """一排小缩略图（编辑器里用），无点击放大功能。

    image_list 里可能是带归属前缀的路径（如 "analysis:xxx.png"），
    这里统一用 real_image_path 还原成真实文件路径。
    """
    if not image_list:
        return
    cols = st.columns(min(6, len(image_list)))
    for i, rel in enumerate(image_list):
        with cols[i % len(cols)]:
            p = file_utils.abs_path(file_utils.real_image_path(rel))
            if p.is_file():
                st.image(str(p), width=THUMB_WIDTH)
            else:
                st.caption("图片已丢失")


def render_block_image(block, *, center: bool = True) -> None:
    """渲染一个图片块（正文里插在文字之间的那种）。

    用一段 HTML 而不是 st.image：这样能控制居中、最大宽度，
    而且同一张图重复引用时不会产生重复的组件 key。

    宽度取标记里写的值（![[img:1|300]]），没写就用默认宽度。
    图片文件不存在 / 序号写错时，原地给一行提示，不至于整块消失。

    图片下面**不加"图 N"之类的图注** —— 序号你自己写在标记里，
    再显示一遍纯属多余。
    """
    rel = block.get("path")
    number = block.get("number")

    if not rel:
        st.markdown(
            f"<div style='color:#c0392b;font-size:0.9em;'>"
            f"［配图 {number} 不存在：请检查 ![[img:{number}]] 的序号］</div>",
            unsafe_allow_html=True,
        )
        return

    path = file_utils.abs_path(file_utils.real_image_path(rel))
    if not path.is_file():
        st.markdown(
            f"<div style='color:#c0392b;font-size:0.9em;'>"
            f"［配图 {number} 文件已丢失］</div>",
            unsafe_allow_html=True,
        )
        return

    width = block.get("size") or BLOCK_IMAGE_WIDTH
    align = "center" if center else "left"
    st.markdown(
        f"<div class='{IMAGE_WRAP_CLASS}' style='text-align:{align};'>"
        f"<img class='{IMAGE_CLASS}' "
        f"src=\"data:image/{_ext(path)};base64,{_b64(path)}\" "
        f"style=\"width:{width}px;\" alt=\"配图 {number}\">"
        f"</div>",
        unsafe_allow_html=True,
    )


def _b64(path) -> str:
    import base64
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _ext(path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return "jpeg" if suffix in ("jpg", "jpeg") else (suffix or "png")


def render_text_blocks(text: str, images, *, center_images: bool = True) -> None:
    """按 ![[img:N]] 标记，把文字和图片交替渲染出来。

    - 没有标记 → 一段文字 + 末尾一串图片（和改动前完全一致）
    - 有标记   → 图片插在标记所在的位置
    文字仍然走 st.markdown，所以 KaTeX 公式、字号、CSS 全部照旧。
    """
    for block in markdown_to_blocks(text, list(images or [])):
        if block["type"] == "text":
            st.markdown(md(block["text"]))
        else:
            render_block_image(block, center=center_images)


def render_body(q, *, key: str, meta_items=None, with_grade: bool = False,
                thumb_prefix: str = "card"):
    """题目正文：元信息 + 分割线 + 题干（含插图位置）+ 选项。

    整体包在 st.container(key=f"qdisp_{key}_{q.id}") 里，
    app.py 的全局 CSS 据此把这一块统一成宋体六号。
    调用方请把按钮放在这个容器外面，避免按钮字号被一起改掉。
    """
    if meta_items is None:
        meta_items = standard_meta_items(q, with_grade=with_grade)

    # 题干配图 = 图片数组里没有解析归属前缀的那些（旧数据全部属于这里）
    stem_images, _analysis_images = file_utils.split_images(q.image_list)

    with st.container(key=f"qdisp_{key}_{q.id}"):
        st.markdown(meta_block(meta_items), unsafe_allow_html=True)
        st.markdown(TIGHT_HR, unsafe_allow_html=True)

        if (q.stem or "").strip():
            render_text_blocks(q.stem, stem_images)
        else:
            st.markdown("_（空题干）_")

        # 选项（选择题才显示）
        if q.qtype in CHOICE_TYPES and q.options_list:
            for o in q.options_list:
                text = (o.get("text", "") or "").strip()
                if text:
                    st.markdown(f"**{o.get('key', '')}．** " + md(text))


def render_answer_expander(q, *, key: str, expanded: bool = False,
                           label: str = "📖 查看答案与解析"):
    """卡片下方的「答案与解析」折叠面板。

    解析文字同样支持 ![[img:N]] 标记，图片会插在解析文字的对应位置。

    这里**故意不加 on_change="rerun"**：加了之后折叠面板的展开/收起会触发
    一次整页重跑，一页几十张卡片时会明显变卡。不加的话展开/收起是纯浏览器
    行为，服务器完全不参与，点起来最跟手；代价是折叠着的内容也会被渲染，
    但它只是一点文本 + 缩略图，比"每点一次重跑整页"划算得多。
    """
    with st.expander(label, expanded=expanded):
        _stem_images, analysis_images = file_utils.split_images(q.image_list)
        with st.container(key=f"qdisp_ans_{key}_{q.id}"):
            st.markdown("**答案**")
            st.markdown(md(q.answer) or "_略_")
            st.markdown("**解析**")
            if (q.analysis or "").strip():
                render_text_blocks(q.analysis, analysis_images)
            else:
                st.markdown("_略_")
