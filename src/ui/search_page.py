# -*- coding: utf-8 -*-
"""搜索与筛选页面：多条件组合、结果批量操作。"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.config import DIFFICULTY_LABELS, GRADES, QTYPES
from src.services import question_service as qs
from src.ui import question_card as qc
from src.utils.latex import md

PAGE_SIZE_OPTIONS = [20, 50, 100, 200]
SS_PREFIX = "search_"

ORDER_LABELS = {
    "最近更新": "updated_desc",
    "最早更新": "updated_asc",
    "最近创建": "created_desc",
    "最早创建": "created_asc",
    "难度从高到低": "difficulty_desc",
    "难度从低到高": "difficulty_asc",
}


# ============================================================
# session_state
# ============================================================
def _init_state():
    st.session_state.setdefault(SS_PREFIX + "page", 1)
    st.session_state.setdefault(SS_PREFIX + "page_size", 20)
    st.session_state.setdefault(SS_PREFIX + "confirm_batch_delete", False)
    st.session_state.setdefault(SS_PREFIX + "selected_ids", set())
    st.session_state.setdefault(SS_PREFIX + "filter_fp", None)


def _clear_filters():
    """清空所有筛选项。"""
    keys_to_clear = [
        "kw", "qtypes", "grades", "chapters", "sources",
        "difficulties", "knowledge", "tags",
        "use_date", "date_from", "date_to",
        "order",
    ]
    for k in keys_to_clear:
        st.session_state.pop(SS_PREFIX + k, None)
    st.session_state[SS_PREFIX + "page"] = 1


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
# 筛选面板
# ============================================================
def _render_filters():
    """渲染关键词框 + 高级筛选面板，返回筛选条件 dict。"""
    p = SS_PREFIX

    kw = st.text_input(
        "🔍 关键词",
        key=p + "kw",
        placeholder="题干 / 答案 / 解析 / 来源 / 标签 / 知识点 / 章节 均可匹配",
    )

    # 下拉框字典（每次渲染都取最新，保证新增题目后能立刻出现）
    all_chapters = qs.get_all_chapters()
    all_sources = qs.get_all_sources()
    all_knowledge = qs.get_all_knowledge()
    all_tags = qs.get_all_tags()

    with st.expander("⚙️ 高级筛选", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.multiselect("题型", QTYPES, key=p + "qtypes", placeholder="不限")
            st.multiselect("年级", GRADES, key=p + "grades", placeholder="不限")
        with c2:
            st.multiselect("章节", all_chapters, key=p + "chapters", placeholder="不限")
            st.multiselect("来源", all_sources, key=p + "sources", placeholder="不限")
        with c3:
            st.multiselect(
                "难度", [1, 2, 3, 4, 5],
                format_func=lambda x: DIFFICULTY_LABELS[x],
                key=p + "difficulties", placeholder="不限",
            )
            st.selectbox(
                "排序", list(ORDER_LABELS.keys()),
                key=p + "order", index=0,
            )

        c4, c5 = st.columns(2)
        with c4:
            st.multiselect("知识点", all_knowledge, key=p + "knowledge", placeholder="不限")
        with c5:
            st.multiselect("标签", all_tags, key=p + "tags", placeholder="不限")

        c6, c7, c8 = st.columns([1, 2, 2])
        with c6:
            st.checkbox("按创建时间", key=p + "use_date")
        use_date = st.session_state.get(p + "use_date", False)
        with c7:
            st.date_input(
                "从", value=date.today() - timedelta(days=30),
                key=p + "date_from", disabled=not use_date,
            )
        with c8:
            st.date_input(
                "到", value=date.today(),
                key=p + "date_to", disabled=not use_date,
            )

        cl, cr = st.columns([5, 1])
        with cr:
            if st.button("🔄 清空筛选", width="stretch"):
                _clear_filters()
                st.rerun()

    # 组装筛选条件
    use_date = st.session_state.get(p + "use_date", False)
    filters = {
        "keyword": st.session_state.get(p + "kw", ""),
        "qtypes": st.session_state.get(p + "qtypes", []) or None,
        "grades": st.session_state.get(p + "grades", []) or None,
        "chapters": st.session_state.get(p + "chapters", []) or None,
        "difficulties": st.session_state.get(p + "difficulties", []) or None,
        "sources": st.session_state.get(p + "sources", []) or None,
        "knowledge_list": st.session_state.get(p + "knowledge", []) or None,
        "tags": st.session_state.get(p + "tags", []) or None,
        "created_from": st.session_state.get(p + "date_from") if use_date else None,
        "created_to": st.session_state.get(p + "date_to") if use_date else None,
    }
    order_label = st.session_state.get(p + "order", "最近更新")
    filters["order_by"] = ORDER_LABELS.get(order_label, "updated_desc")
    return filters


# ============================================================
# 结果列表
# ============================================================
def _render_results(filters: dict):
    p = SS_PREFIX
    count_filters = {k: v for k, v in filters.items() if k != "order_by"}
    total = qs.count_search_questions(**count_filters)

    st.divider()
    if total == 0:
        st.info("没有匹配的题目。试试放宽筛选条件，或点「🔄 清空筛选」。")
        return

    # 筛选条件变化 → 清空已选
    fp = json.dumps({k: str(v) for k, v in filters.items()}, sort_keys=True)
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
    rows = qs.search_questions(
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
    st.caption("组合多个条件精确定位题目；在结果表格中可多选后批量操作。")

    filters = _render_filters()
    _render_results(filters)