# -*- coding: utf-8 -*-
"""题目筛选面板（公共组件）。

「搜索筛选」和「手动组卷」的选题区共用同一个面板，保证两处的搜索栏完全一致。

用法：
    filters = qf.render_filter_panel("search_")     # 或 "pp_"
    rows = qs.search_questions(**filters, limit=..., offset=...)

所有 widget 的 key 都会加上传入的前缀，因此两个页面互不干扰。
每个页面需要先调用一次 `init_filter_state(prefix)`，再调用 `render_filter_panel`。
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.config import DIFFICULTY_LABELS, GRADES, QTYPES
from src.services import data_cache as dc

ORDER_LABELS = {
    "最近更新": "updated_desc",
    "最早更新": "updated_asc",
    "最近创建": "created_desc",
    "最早创建": "created_asc",
    "难度从高到低": "difficulty_desc",
    "难度从低到高": "difficulty_asc",
}

# 需要清空的 widget key（不含前缀）
_FILTER_KEYS = [
    "kw", "qtypes", "grades", "chapters", "sources",
    "difficulties", "knowledge", "tags",
    "use_date", "date_from", "date_to", "order",
]

# 页面级状态（不含前缀）：记录上一次的筛选指纹和页码
_STATE_KEYS = ["filter_fp", "page"]


def init_filter_state(prefix: str) -> None:
    """初始化该前缀下的筛选状态。页面 render() 开头调用。"""
    st.session_state.setdefault(prefix + "filter_fp", None)
    st.session_state.setdefault(prefix + "page", 1)


def clear_filters(prefix: str) -> None:
    """清空该前缀下的所有筛选项（供「清空筛选」按钮使用）。"""
    for k in _FILTER_KEYS:
        st.session_state.pop(prefix + k, None)
    st.session_state[prefix + "page"] = 1
    st.session_state[prefix + "filter_fp"] = None


def filters_fingerprint(filters: dict) -> str:
    """把筛选条件压成一个可比较的字符串，用于「条件变了就回到第 1 页」。"""
    return "|".join(f"{k}={filters.get(k)}" for k in sorted(filters))


def render_filter_panel(prefix: str, *, expanded: bool = True,
                        reset_page: bool = True) -> dict:
    """渲染关键词框 + 高级筛选面板，返回筛选条件 dict。

    prefix 用于区分不同页面的 widget key，例如 "search_" / "pp_"。
    """
    p = prefix

    st.text_input(
        "🔍 关键词",
        key=p + "kw",
        placeholder="题干 / 答案 / 解析 / 来源 / 标签 / 知识点 / 章节 均可匹配",
    )

    # 下拉候选走缓存（写题时会自动失效），避免每次 rerun 都全表扫描一遍
    all_chapters = dc.get_all_chapters()
    all_sources = dc.get_all_sources()
    all_knowledge = dc.get_all_knowledge()
    all_tags = dc.get_all_tags()

    with st.expander("⚙️ 高级筛选", expanded=expanded):
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
            if st.button("🔄 清空筛选", width="stretch", key=p + "clear"):
                clear_filters(p)
                st.rerun()

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

    # 条件变化 → 回到第 1 页
    if reset_page:
        fp = filters_fingerprint(filters)
        if st.session_state.get(p + "filter_fp") != fp:
            st.session_state[p + "filter_fp"] = fp
            st.session_state[p + "page"] = 1

    return filters


def count_matching(filters: dict) -> int:
    """按筛选条件（不含排序）统计总数。"""
    return dc.count_search_questions(
        **{k: v for k, v in filters.items() if k != "order_by"}
    )
