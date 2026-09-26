# -*- coding: utf-8 -*-
"""回收站页面：题目 + 试卷的软删除恢复、批量彻底删除。

规则：题目如果还被试卷引用，彻底删除会被拦截（在 service 层判断），
因为试卷里删掉一题会破坏整卷结构。想删的话先去试卷里移除该题。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import DIFFICULTY_LABELS
from src.services import paper_service as ps
from src.services import question_service as qs
from src.utils.latex import strip_latex_for_preview

SS = "rc_"


def _init_state():
    st.session_state.setdefault(SS + "confirm_empty_q", False)
    st.session_state.setdefault(SS + "confirm_empty_p", False)
    st.session_state.setdefault(SS + "df_version", 0)  # 用于重置 dataframe 选择


def _flash(msg: str, kind: str = "success"):
    st.session_state["_flash"] = (kind, msg)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


def _bump_version():
    """每次改动回收站内容后 +1，让 dataframe key 变化，清掉旧选择。"""
    st.session_state[SS + "df_version"] = st.session_state.get(SS + "df_version", 0) + 1


# ============================================================
# 题目回收站
# ============================================================
def _render_question_trash():
    rows = qs.list_deleted_questions()
    if not rows:
        st.info("题目回收站是空的。")
        return

    st.caption(
        f"共 **{len(rows)}** 道已删除题目。还原后会回到题目管理中；"
        f"彻底删除不可恢复。"
    )

    df = pd.DataFrame([{
        "ID": q.id,
        "题型": q.qtype or "—",
        "难度": "★" * q.difficulty,
        "年级": q.grade or "—",
        "章节": q.chapter or "—",
        "题干预览": strip_latex_for_preview(q.stem, 60) or "（空）",
        "删除时间": q.deleted_at.strftime("%Y-%m-%d %H:%M") if q.deleted_at else "—",
    } for q in rows])

    version = st.session_state.get(SS + "df_version", 0)
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(500, 60 + 36 * len(df)),
        on_select="rerun",
        selection_mode="multi-row",
        key=f"{SS}q_df_{version}",
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
            "题干预览": st.column_config.TextColumn(width="large"),
        },
    )

    sel_indices = event.selection.rows if event and event.selection else []
    selected = [rows[i] for i in sel_indices if 0 <= i < len(rows)]
    selected_ids = [q.id for q in selected]

    st.caption(f"已选 **{len(selected_ids)}** 道")

    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 1, 4])
        with c1:
            if st.button(
                f"♻️ 还原选中",
                disabled=not selected_ids,
                use_container_width=True,
                key=SS + "btn_restore_q",
            ):
                n = qs.batch_restore_questions(selected_ids)
                _bump_version()
                _flash(f"已还原 {n} 道题目")
                st.rerun()
        with c2:
            if st.button(
                "❌ 彻底删除选中",
                disabled=not selected_ids,
                use_container_width=True,
                key=SS + "btn_hard_q",
            ):
                result = qs.batch_hard_delete_questions(selected_ids)
                _bump_version()
                msg = f"彻底删除 {result['deleted']} 道"
                if result["blocked"]:
                    ids_str = ", ".join(f"#{i}" for i in result["blocked_ids"][:10])
                    msg += f"；{result['blocked']} 道被试卷引用，已跳过（{ids_str}）"
                    _flash(msg, "warning")
                else:
                    _flash(msg)
                st.rerun()
        with c3:
            st.caption("提示：被试卷引用的题目无法彻底删除，请先在对应试卷中移除该题。")


def _render_empty_question_trash():
    if st.session_state.get(SS + "confirm_empty_q"):
        c1, c2, c3 = st.columns([1, 1, 4])
        with c1:
            if st.button("⚠️ 确认清空", type="primary",
                         use_container_width=True, key=SS + "cfm_empty_q"):
                result = qs.empty_question_trash()
                _bump_version()
                st.session_state[SS + "confirm_empty_q"] = False
                msg = f"已清空题目回收站：删除 {result['deleted']} 道"
                if result["blocked"]:
                    msg += f"，{result['blocked']} 道被试卷引用而保留"
                _flash(msg, "warning" if result["blocked"] else "success")
                st.rerun()
        with c2:
            if st.button("取消", use_container_width=True, key=SS + "cancel_empty_q"):
                st.session_state[SS + "confirm_empty_q"] = False
                st.rerun()
        with c3:
            st.warning("清空后无法恢复！")
    else:
        if st.button("🧹 清空题目回收站", key=SS + "btn_empty_q"):
            st.session_state[SS + "confirm_empty_q"] = True
            st.rerun()


# ============================================================
# 试卷回收站
# ============================================================
def _render_paper_trash():
    rows = ps.list_deleted_papers()
    if not rows:
        st.info("试卷回收站是空的。")
        return

    st.caption(f"共 **{len(rows)}** 份已删除试卷。还原后回到手动组卷列表中。")

    df = pd.DataFrame([{
        "ID": p["id"],
        "标题": p["title"],
        "题数": p["item_count"],
        "删除时间": p["deleted_at"].strftime("%Y-%m-%d %H:%M") if p["deleted_at"] else "—",
    } for p in rows])

    version = st.session_state.get(SS + "df_version", 0)
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(500, 60 + 36 * len(df)),
        on_select="rerun",
        selection_mode="multi-row",
        key=f"{SS}p_df_{version}",
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
            "标题": st.column_config.TextColumn(width="large"),
        },
    )

    sel_indices = event.selection.rows if event and event.selection else []
    selected_ids = [rows[i]["id"] for i in sel_indices if 0 <= i < len(rows)]

    st.caption(f"已选 **{len(selected_ids)}** 份")

    with st.container(border=True):
        c1, c2, _ = st.columns([1, 1, 4])
        with c1:
            if st.button(
                "♻️ 还原选中",
                disabled=not selected_ids,
                use_container_width=True,
                key=SS + "btn_restore_p",
            ):
                n = ps.batch_restore_papers(selected_ids)
                _bump_version()
                _flash(f"已还原 {n} 份试卷")
                st.rerun()
        with c2:
            if st.button(
                "❌ 彻底删除选中",
                disabled=not selected_ids,
                use_container_width=True,
                key=SS + "btn_hard_p",
            ):
                n = ps.batch_hard_delete_papers(selected_ids)
                _bump_version()
                _flash(f"彻底删除 {n} 份试卷")
                st.rerun()


def _render_empty_paper_trash():
    if st.session_state.get(SS + "confirm_empty_p"):
        c1, c2, c3 = st.columns([1, 1, 4])
        with c1:
            if st.button("⚠️ 确认清空", type="primary",
                         use_container_width=True, key=SS + "cfm_empty_p"):
                n = ps.empty_paper_trash()
                _bump_version()
                st.session_state[SS + "confirm_empty_p"] = False
                _flash(f"已清空试卷回收站：删除 {n} 份", "warning")
                st.rerun()
        with c2:
            if st.button("取消", use_container_width=True, key=SS + "cancel_empty_p"):
                st.session_state[SS + "confirm_empty_p"] = False
                st.rerun()
        with c3:
            st.warning("清空后无法恢复！")
    else:
        if st.button("🧹 清空试卷回收站", key=SS + "btn_empty_p"):
            st.session_state[SS + "confirm_empty_p"] = True
            st.rerun()


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()
    _show_flash()

    st.header("🗑️ 回收站")
    st.caption("删除的题目和试卷会先进入这里；确认不再需要时再彻底删除。")

    q_n = qs.count_deleted_questions()
    p_n = ps.count_deleted_papers()

    c1, c2 = st.columns(2)
    c1.metric("已删除题目", f"{q_n} 道")
    c2.metric("已删除试卷", f"{p_n} 份")
    st.divider()

    tab_q, tab_p = st.tabs(["📚 题目回收站", "📝 试卷回收站"])
    with tab_q:
        _render_question_trash()
        if q_n > 0:
            st.divider()
            _render_empty_question_trash()
    with tab_p:
        _render_paper_trash()
        if p_n > 0:
            st.divider()
            _render_empty_paper_trash()