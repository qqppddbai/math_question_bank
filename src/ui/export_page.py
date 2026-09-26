# -*- coding: utf-8 -*-
"""试卷导出页面：选卷 → 选格式 → 生成 → 下载。"""
from __future__ import annotations

import re
from datetime import datetime

import streamlit as st

from src.config import EXPORT_DIR
from src.exporters.common import build_paper_view
from src.exporters.html_exporter import export_html
from src.exporters.markdown_exporter import export_markdown
from src.exporters.word_exporter import export_word
from src.services import paper_service as ps

SS = "ex_"


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name or "")
    return name.strip() or "paper"


def _init_state():
    st.session_state.setdefault(SS + "result", None)
    st.session_state.setdefault(SS + "last_paper_id", None)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


# ============================================================
# 生成
# ============================================================
def _generate(paper_id: int, fmt: str, include_answer: bool,
              include_analysis: bool, answers_at_end: bool, include_images: bool):
    detail = ps.get_paper_detail(paper_id)
    if detail is None:
        st.error("试卷不存在或已被删除。")
        return

    qids = [it["question_id"] for s in detail["sections"] for it in s["items"]]
    qmap = ps.get_questions_by_ids(qids)
    view = build_paper_view(detail, qmap)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _safe_filename(view.title)

    try:
        if fmt.startswith("Word"):
            filename = f"{base}_{timestamp}.docx"
            target = EXPORT_DIR / filename
            export_word(view, target,
                        include_answer=include_answer,
                        include_analysis=include_analysis,
                        answers_at_end=answers_at_end,
                        include_images=include_images)
            data = target.read_bytes()
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif fmt.startswith("HTML"):
            filename = f"{base}_{timestamp}.html"
            target = EXPORT_DIR / filename
            content = export_html(view,
                                  include_answer=include_answer,
                                  include_analysis=include_analysis,
                                  answers_at_end=answers_at_end,
                                  include_images=include_images)
            target.write_text(content, encoding="utf-8")
            data = content.encode("utf-8")
            mime = "text/html"
        else:
            filename = f"{base}_{timestamp}.md"
            target = EXPORT_DIR / filename
            content = export_markdown(view,
                                      include_answer=include_answer,
                                      include_analysis=include_analysis,
                                      answers_at_end=answers_at_end,
                                      include_images=include_images)
            target.write_text(content, encoding="utf-8")
            data = content.encode("utf-8")
            mime = "text/markdown"
    except Exception as e:
        st.error(f"生成失败：{e}")
        return

    st.session_state[SS + "result"] = {
        "filename": filename,
        "path": str(target),
        "data": data,
        "mime": mime,
    }
    st.rerun()


# ============================================================
# 结果展示
# ============================================================
def _show_result(result):
    st.divider()
    st.subheader("✅ 生成完成")
    st.markdown(f"**文件名：** `{result['filename']}`")
    st.caption(f"同时已保存到：`{result['path']}`")
    st.download_button(
        label="⬇️ 下载到本机",
        data=result["data"],
        file_name=result["filename"],
        mime=result["mime"],
        type="primary",
        key=SS + "dl",
    )
    if result["filename"].endswith(".html"):
        st.info(
            "提示：用浏览器打开下载的 HTML 文件 → 按 **Ctrl + P** → "
            "目标打印机选「另存为 PDF」即可得到 PDF。"
            "首次打开需要联网加载 KaTeX（公式渲染库），之后浏览器会缓存。"
        )
    elif result["filename"].endswith(".docx"):
        st.info(
            "提示：公式已转成 Word 原生公式（OMML），可以像普通公式一样选中、改字号。"
            "若看到的还是 LaTeX 原文，说明缺少 latex2mathml / mathml2omml 依赖，"
            "运行 `pip install -r requirements.txt` 后再导出一次即可。"
        )


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()
    _show_flash()

    st.header("📤 试卷导出")
    st.caption("导出的 HTML 可在浏览器里直接打印成 PDF；Word 供二次编辑；Markdown 供进一步排版。")

    papers = ps.list_papers()
    if not papers:
        st.info("还没有试卷。请先到「📝 手动组卷」创建。")
        return

    labels = {
        f"#{p['id']} {p['title']}（{p['item_count']} 题 / {p['total_score']} 分）": p["id"]
        for p in papers
    }
    chosen = st.selectbox("选择试卷", list(labels.keys()), key=SS + "paper")
    paper_id = labels[chosen]

    # 切换试卷时清掉上次的生成结果
    if st.session_state[SS + "last_paper_id"] != paper_id:
        st.session_state[SS + "result"] = None
        st.session_state[SS + "last_paper_id"] = paper_id

    st.divider()
    st.subheader("导出选项")

    c1, c2, c3 = st.columns(3)
    with c1:
        fmt = st.radio(
            "文件格式",
            ["Word（.docx）", "HTML（可打印 PDF）", "Markdown（.md）"],
            key=SS + "fmt",
        )
    with c2:
        include_answer = st.checkbox("包含答案", value=True, key=SS + "ans")
        include_analysis = st.checkbox("包含解析", value=True, key=SS + "ana")
        include_images = st.checkbox("包含题目图片", value=True, key=SS + "img")
    with c3:
        disable_pos = not (include_answer or include_analysis)
        pos = st.radio(
            "答案位置",
            ["每题后", "卷末统一"],
            key=SS + "pos",
            disabled=disable_pos,
        )
        answers_at_end = (pos == "卷末统一")

    st.divider()
    if st.button("🛠️ 生成文件", type="primary"):
        _generate(paper_id, fmt, include_answer, include_analysis,
                  answers_at_end, include_images)

    result = st.session_state.get(SS + "result")
    if result:
        _show_result(result)