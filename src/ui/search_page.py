# -*- coding: utf-8 -*-
"""搜索与筛选页面：多条件组合、结果批量操作。"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.services import data_cache as dc
from src.services import question_service as qs
from src.ui import question_card as qc
from src.ui import question_filter as qf
from src.utils.latex import md

PAGE_SIZE_OPTIONS = [20, 50, 100, 200]
SS_PREFIX = "search_"


# ============================================================
# session_state
# ============================================================
def _init_state():
    st.session_state.setdefault(SS_PREFIX + "page_size", 20)
    st.session_state.setdefault(SS_PREFIX + "confirm_batch_delete", False)
    st.session_state.setdefault(SS_PREFIX + "selected_ids", set())
    qf.init_filter_state(SS_PREFIX)


def _flash(msg: str, kind: str = "success"):
    st.session_state["_flash"] = (kind, msg)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


# ============================================================
# 回调（在 widget 渲染前执行，可安全写 session_state）
# ============================================================
def _cb_prev_page():
    p = SS_PREFIX
    st.session_state[p + "page"] = max(1, st.session_state.get(p + "page", 1) - 1)
    st.session_state[p + "selected_ids"] = set()


def _cb_next_page():
    p = SS_PREFIX
    st.session_state[p + "page"] = st.session_state.get(p + "page", 1) + 1
    st.session_state[p + "selected_ids"] = set()


def _cb_toggle_select(qid: int):
    p = SS_PREFIX
    s = set(st.session_state.get(p + "selected_ids", set()))
    if qid in s:
        s.discard(qid)
    else:
        s.add(qid)
    st.session_state[p + "selected_ids"] = s


# ============================================================
# 结果列表
# ============================================================
def _render_results(filters: dict):
    p = SS_PREFIX
    total = qf.count_matching(filters)

    st.divider()
    if total == 0:
        st.info("没有匹配的题目。试试放宽筛选条件，或点「🔄 清空筛选」。")
        return

    # 筛选条件变化 → 清空已选
    fp = qf.filters_fingerprint(filters)
    if st.session_state.get(p + "filter_fp") != fp:
        st.session_state[p + "filter_fp"] = fp
        st.session_state[p + "selected_ids"] = set()

    # ---------- 分页条 ----------
    top_l, top_m, top_r = st.columns([2, 3, 2])
    with top_l:
        st.markdown(f"**共 {total} 道**")
    with top_m:
        page_size = st.selectbox(
            "每页条数", PAGE_SIZE_OPTIONS,
            index=PAGE_SIZE_OPTIONS.index(st.session_state.get(p + "page_size", 20)),
            key=p + "page_size_sel",
            label_visibility="collapsed",
        )
        st.session_state[p + "page_size"] = page_size
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, st.session_state.get(p + "page", 1)), total_pages)
    st.session_state[p + "page"] = page

    with top_r:
        nav_l, nav_r = st.columns(2)
        with nav_l:
            st.button("⬅️", disabled=(page <= 1), use_container_width=True,
                      key=p + "prev", on_click=_cb_prev_page)
        with nav_r:
            st.button("➡️", disabled=(page >= total_pages), use_container_width=True,
                      key=p + "next", on_click=_cb_next_page)
        st.caption(f"第 {page} / {total_pages} 页")

    # ---------- 拉数据 ----------
    rows = dc.search_questions(
        **filters, limit=page_size, offset=(page - 1) * page_size,
    )

    st.caption("💡 点每张卡片右侧的「☐ 选择」加入批量操作；再点一次取消。")

    # ---------- 卡片列表 ----------
    for q in rows:
        _render_search_card(q)

    # ---------- 批量操作条 ----------
    selected_all = st.session_state.get(p + "selected_ids", set())
    current_page_ids = {q.id for q in rows}
    selected_ids = [qid for qid in selected_all if qid in current_page_ids]
    selected_qs = [q for q in rows if q.id in selected_ids]
    _render_batch_bar(selected_qs, selected_ids)


def _render_search_card(q):
    """搜索页的题目卡片：题目展示与「题目管理」共用 question_card，右侧为「选择」。"""
    is_selected = q.id in st.session_state.get(SS_PREFIX + "selected_ids", set())

    with st.container(border=True):
        content_col, action_col = st.columns([9, 1.6])

        with content_col:
            qc.render_body(q, key="scard", with_grade=True,
                           thumb_prefix=f"sr_{q.id}")

        with action_col:
            label = "✅ 已选" if is_selected else "☐ 选择"
            st.button(
                label,
                key=f"{SS_PREFIX}tog_{q.id}",
                use_container_width=True,
                on_click=_cb_toggle_select,
                args=(q.id,),
            )

    # 卡片下方折叠的答案与解析
    qc.render_answer_expander(q, key="scard")
# ============================================================
# 批量操作条
# ============================================================
def _render_batch_bar(selected_qs, selected_ids):
    p = SS_PREFIX
    if not selected_ids:
        return

    st.success(f"已选 **{len(selected_ids)}** 道题：{selected_ids[:20]}{' ...' if len(selected_ids) > 20 else ''}")

    with st.container(border=True):
        st.markdown("**批量操作**")

        c1, c2, c3 = st.columns(3)

        # ---- 加标签 ----
        with c1:
            new_tag_text = st.text_input(
                "追加标签（逗号分隔）", key=p + "add_tag_input",
                placeholder="如：易错题,复习",
            )
            if st.button("➕ 加标签", width="stretch", key=p + "btn_add_tag"):
                if new_tag_text.strip():
                    n = qs.batch_add_tags(selected_ids, new_tag_text.split(","))
                    _flash(f"已为 {n} 道题追加标签")
                    st.rerun()
                else:
                    st.warning("请输入要追加的标签。")

        # ---- 移除标签 ----
        with c2:
            rm_tag_text = st.text_input(
                "移除标签（逗号分隔）", key=p + "rm_tag_input",
                placeholder="如：单元测",
            )
            if st.button("➖ 移除标签", width="stretch", key=p + "btn_rm_tag"):
                if rm_tag_text.strip():
                    n = qs.batch_remove_tags(selected_ids, rm_tag_text.split(","))
                    _flash(f"已为 {n} 道题移除标签")
                    st.rerun()
                else:
                    st.warning("请输入要移除的标签。")

        # ---- 导出选中 ----
        with c3:
            st.write("")
            st.write("")
            if st.button("📤 导出为 JSON", width="stretch", key=p + "btn_export"):
                data = [{
                    "grade": q.grade, "chapter": q.chapter,
                    "knowledge": q.knowledge, "qtype": q.qtype,
                    "difficulty": q.difficulty, "stem": q.stem,
                    "options": q.options, "answer": q.answer,
                    "analysis": q.analysis, "source": q.source,
                    "tags": q.tags,
                } for q in selected_qs]
                st.download_button(
                    "⬇️ 点击下载 JSON",
                    data=json.dumps(data, ensure_ascii=False, indent=2),
                    file_name=f"selected_questions_{len(data)}.json",
                    mime="application/json",
                    width="stretch",
                    key=p + "dl_json",
                )

        # ---- 危险操作 ----
        st.divider()
        dl, dr = st.columns([1, 4])
        with dl:
            if not st.session_state.get(p + "confirm_batch_delete"):
                if st.button("🗑️ 删除选中", key=p + "btn_batch_del"):
                    st.session_state[p + "confirm_batch_delete"] = True
                    st.rerun()
            else:
                if st.button("⚠️ 确认删除", type="primary", key=p + "btn_confirm_del"):
                    n = qs.batch_soft_delete(selected_ids)
                    st.session_state[p + "confirm_batch_delete"] = False
                    _flash(f"已删除 {n} 道题，可在回收站还原", kind="warning")
                    st.rerun()
        with dr:
            if st.session_state.get(p + "confirm_batch_delete"):
                st.warning("删除后可在「回收站」找回。")
                if st.button("取消", key=p + "btn_cancel_del"):
                    st.session_state[p + "confirm_batch_delete"] = False
                    st.rerun()


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()
    _show_flash()

    st.header("🔍 搜索与筛选")
    st.caption("与「手动组卷」的选题区使用同一套筛选条件；在结果里可多选后批量操作。")

    filters = qf.render_filter_panel(SS_PREFIX)
    _render_results(filters)