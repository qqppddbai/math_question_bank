# -*- coding: utf-8 -*-
"""手动组卷页面：列表 → 编辑器（上：试卷结构 / 下：从题库选题）。

草稿（draft）保存在 st.session_state["pp_draft"]，结构见 paper_service 顶部注释。
草稿不是 widget key，可随时修改；只有真正绑定到 widget 的 key 才受 Streamlit 限制。

选题方式：题目以卡片展示（与「题目管理」同一套渲染），
每张卡片一个「➕ 加入试卷」按钮，点一次追加一道，
因此试卷中题目的顺序 = 点击先后顺序。
"""
from __future__ import annotations

import uuid

import streamlit as st

from src.config import GRADES, QTYPES
from src.services import paper_service as ps
from src.services import question_service as qs
from src.ui import question_card as qc
from src.utils.latex import strip_latex_for_preview

SS = "pp_"

PICKER_PAGE_SIZE = 10   # 选题区每页显示多少张题目卡片


def _cb_add_section():
    """添加大题的按钮回调（在 widget 渲染前执行，可安全写 session_state）。"""
    draft = st.session_state.get(SS + "draft")
    if not draft:
        return
    title = (st.session_state.get(SS + "new_sec_title") or "").strip() \
            or f"大题{len(draft['sections']) + 1}"
    draft["sections"].append({"sec_id": _uid(), "title": title, "items": []})
    st.session_state[SS + "new_sec_title"] = ""   # 回调里可改

def _uid() -> str:
    return uuid.uuid4().hex[:8]


# ============================================================
# 状态
# ============================================================
def _init_state():
    st.session_state.setdefault(SS + "editing", None)          # None / 'new' / int
    st.session_state.setdefault(SS + "draft", None)
    st.session_state.setdefault(SS + "loaded_for", "__none__") # 上次加载的 editing 值
    st.session_state.setdefault(SS + "confirm_delete", None)
    st.session_state.setdefault(SS + "picker_page", 1)
    st.session_state.setdefault(SS + "picker_fp", None)


def _flash(msg: str, kind: str = "success"):
    st.session_state["_flash"] = (kind, msg)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


def _close_editor():
    st.session_state[SS + "editing"] = None
    st.session_state[SS + "draft"] = None
    st.session_state[SS + "loaded_for"] = "__none__"
    st.session_state[SS + "picker_page"] = 1
    st.session_state[SS + "picker_fp"] = None


# ============================================================
# 列表页
# ============================================================
def _render_list():
    st.header("📝 手动组卷")
    st.caption("从题库挑题组成试卷，可自由设置分值和大题；保存后可到「试卷导出」页导出。")

    _, top_r = st.columns([4, 1])
    with top_r:
        if st.button("➕ 新建试卷", type="primary", use_container_width=True):
            st.session_state[SS + "editing"] = "new"
            st.rerun()

    papers = ps.list_papers()
    if not papers:
        st.info("还没有试卷。点右上角「➕ 新建试卷」开始组卷。")
        return

    for p in papers:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([5, 1, 1, 1])
            with c1:
                st.markdown(f"**#{p['id']} {p['title']}**")
                sub_line = f"{p['subtitle']} · " if p["subtitle"] else ""
                st.caption(
                    f"{sub_line}共 {p['item_count']} 题 · 总分 {p['total_score']} · "
                    f"{p['exam_minutes']} 分钟 · 更新于 {p['updated_at']:%Y-%m-%d %H:%M}"
                )
            with c2:
                if st.button("✏️ 编辑", key=f"{SS}p_edit_{p['id']}", use_container_width=True):
                    st.session_state[SS + "editing"] = p["id"]
                    st.rerun()
            with c3:
                if st.session_state.get(SS + "confirm_delete") == p["id"]:
                    if st.button("⚠️ 确认", key=f"{SS}p_cdel_{p['id']}",
                                 type="primary", use_container_width=True):
                        ps.soft_delete_paper(p["id"])
                        st.session_state[SS + "confirm_delete"] = None
                        _flash("试卷已删除（可在回收站还原）", "warning")
                        st.rerun()
                else:
                    if st.button("🗑️ 删除", key=f"{SS}p_del_{p['id']}",
                                 use_container_width=True):
                        st.session_state[SS + "confirm_delete"] = p["id"]
                        st.rerun()
            with c4:
                if st.session_state.get(SS + "confirm_delete") == p["id"]:
                    if st.button("取消", key=f"{SS}p_cancel_{p['id']}",
                                 use_container_width=True):
                        st.session_state[SS + "confirm_delete"] = None
                        st.rerun()


# ============================================================
# 编辑器：草稿加载
# ============================================================
def _new_draft(paper_id=None) -> dict | None:
    """从数据库加载（或新建）一份草稿。paper_id=None 表示新建。"""
    if paper_id is None:
        return {
            "id": None,
            "title": "未命名试卷",
            "subtitle": "",
            "exam_minutes": 120,
            "sections": [{"sec_id": _uid(), "title": "一、单选题", "items": []}],
        }

    detail = ps.get_paper_detail(int(paper_id))
    if detail is None:
        return None

    sections = []
    for sec in detail["sections"]:
        sections.append({
            "sec_id": _uid(),
            "title": sec["title"],
            "items": [
                {"item_id": _uid(), "question_id": it["question_id"], "score": it["score"]}
                for it in sec["items"]
            ],
        })
    return {
        "id": detail["id"],
        "title": detail["title"],
        "subtitle": detail["subtitle"],
        "exam_minutes": detail["exam_minutes"],
        "sections": sections,
    }


def _ensure_draft():
    """进入编辑器时确保草稿已加载；切换试卷时重新加载。"""
    editing = st.session_state.get(SS + "editing")
    loaded = st.session_state.get(SS + "loaded_for")
    if editing == loaded and st.session_state.get(SS + "draft") is not None:
        return

    draft = _new_draft(None if editing == "new" else int(editing))
    if draft is None:
        st.error("试卷不存在或已被删除。")
        st.session_state[SS + "editing"] = None
        st.rerun()
        return

    st.session_state[SS + "draft"] = draft
    st.session_state[SS + "loaded_for"] = editing

    # 表单 key 与 draft 同步（必须在 widget 渲染之前做）
    st.session_state[SS + "title_in"] = draft["title"]
    st.session_state[SS + "subtitle_in"] = draft["subtitle"]
    st.session_state[SS + "minutes_in"] = draft["exam_minutes"]


# ============================================================
# 编辑器主体
# ============================================================
def _render_editor():
    draft = st.session_state[SS + "draft"]

    head_l, head_r = st.columns([5, 1])
    with head_l:
        st.header("➕ 新建试卷" if draft["id"] is None else f"✏️ 编辑试卷 #{draft['id']}")
    with head_r:
        if st.button("⬅️ 返回列表", use_container_width=True):
            _close_editor()
            st.rerun()

    _render_structure(draft)
    st.divider()
    _render_picker(draft)

    st.divider()
    b1, b2, _, _ = st.columns([1, 1, 1, 4])
    with b1:
        if st.button("💾 保存试卷", type="primary", use_container_width=True):
            _save(draft)
    with b2:
        if st.button("取消", use_container_width=True):
            _close_editor()
            st.rerun()


# ------------------------------------------------------------
# 选题区：题目卡片 + 逐题加入（顺序 = 点击顺序）
# ------------------------------------------------------------
def _render_picker(draft):
    st.subheader("📚 从题库选题")
    st.caption(
        "题目展示与「题目管理」一致。点卡片上的 **➕ 加入试卷**，"
        "就会**按你点击的先后顺序**追加到所选大题的末尾。"
    )

    with st.expander("🔎 筛选条件", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.text_input("关键词", key=SS + "f_kw", placeholder="题干/来源/标签")
        with c2:
            st.selectbox("题型", [""] + QTYPES, key=SS + "f_qtype")
        with c3:
            st.selectbox("年级", [""] + GRADES, key=SS + "f_grade")

    kw = st.session_state.get(SS + "f_kw", "")
    f_qtype = st.session_state.get(SS + "f_qtype", "")
    f_grade = st.session_state.get(SS + "f_grade", "")

    # 筛选条件变了就回到第 1 页
    fp = f"{kw}|{f_qtype}|{f_grade}"
    if st.session_state.get(SS + "picker_fp") != fp:
        st.session_state[SS + "picker_fp"] = fp
        st.session_state[SS + "picker_page"] = 1

    # ---- 加入目标大题 & 默认分值 ----
    if not draft["sections"]:
        st.warning("请先在上方「试卷结构」里创建一个大题，再回来选题。")
        return

    # 保证 index 合法（大题可能被删过）
    if st.session_state.get(SS + "target_sec", 0) >= len(draft["sections"]):
        st.session_state[SS + "target_sec"] = 0
    c1, c2 = st.columns([2, 1])
    with c1:
        target_idx = st.selectbox(
            "加入到大题",
            options=list(range(len(draft["sections"]))),
            format_func=lambda i: draft["sections"][i]["title"] or f"大题{i + 1}",
            key=SS + "target_sec",
        )
    with c2:
        default_score = st.number_input("默认分值", 1, 50, 5, key=SS + "default_score")

    total = qs.count_questions(keyword=kw, qtype=f_qtype, grade=f_grade)
    if total == 0:
        st.info("没有匹配的题目。调整筛选条件试试。")
        return

    # ---- 分页导航 ----
    total_pages = max(1, (total + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = min(max(1, st.session_state.get(SS + "picker_page", 1)), total_pages)
    st.session_state[SS + "picker_page"] = page

    nav_l, nav_c, nav_r = st.columns([1, 3, 1])
    with nav_l:
        if st.button("⬅️ 上一页", disabled=(page <= 1), width="stretch",
                     key=SS + "pk_prev"):
            st.session_state[SS + "picker_page"] = page - 1
            st.rerun()
    with nav_c:
        st.markdown(
            f"<div style='text-align:center;padding-top:6px;color:#666'>"
            f"共 <b>{total}</b> 道 · 第 <b>{page}</b> / {total_pages} 页</div>",
            unsafe_allow_html=True,
        )
    with nav_r:
        if st.button("下一页 ➡️", disabled=(page >= total_pages), width="stretch",
                     key=SS + "pk_next"):
            st.session_state[SS + "picker_page"] = page + 1
            st.rerun()

    rows = qs.list_questions(
        keyword=kw, qtype=f_qtype, grade=f_grade,
        limit=PICKER_PAGE_SIZE, offset=(page - 1) * PICKER_PAGE_SIZE,
    )

    already = {it["question_id"] for s in draft["sections"] for it in s["items"]}
    for q in rows:
        _render_picker_card(draft, q, target_idx, int(default_score), q.id in already)


def _render_picker_card(draft, q, target_idx, score, already_in):
    """选题卡片：题目展示与「题目管理」完全一致，右侧按钮换成本题「加入试卷」。"""
    sec_title = draft["sections"][target_idx]["title"] or f"大题{target_idx + 1}"

    with st.container(border=True):
        body_col, action_col = st.columns([9, 1.6])

        with body_col:
            qc.render_body(q, key="pick", thumb_prefix=f"pk_{q.id}")

        with action_col:
            # key 用题目 id，保证同一张卡片的按钮身份稳定
            if already_in:
                st.button("✅ 已在试卷", key=f"{SS}pick_add_{q.id}",
                          width="stretch", disabled=True)
            elif st.button("➕ 加入试卷", key=f"{SS}pick_add_{q.id}",
                           type="primary", width="stretch"):
                _add_one(draft, target_idx, q, score)
                st.rerun()
            st.caption(f"→ {sec_title}")

    qc.render_answer_expander(q, key="pick")


def _add_one(draft, target_idx, q, score):
    """把一道题追加到目标大题的末尾 —— 因此卷内顺序就是点击顺序。"""
    sec = draft["sections"][target_idx]
    if any(it["question_id"] == q.id
           for s in draft["sections"] for it in s["items"]):
        _flash(f"题目 #{q.id} 已经在试卷里了，已跳过", "warning")
        return
    sec["items"].append({"item_id": _uid(), "question_id": q.id, "score": int(score)})
    sec_title = sec["title"] or f"大题{target_idx + 1}"
    _flash(f"题目 #{q.id} 已加入「{sec_title}」第 {len(sec['items'])} 题")


# ------------------------------------------------------------
# 试卷结构
# ------------------------------------------------------------
def _render_structure(draft):
    st.subheader("📝 试卷结构")

    # ---- 基本信息 ----
    c1, c2, c3 = st.columns([3, 3, 1])
    with c1:
        draft["title"] = st.text_input("试卷标题", key=SS + "title_in")
    with c2:
        draft["subtitle"] = st.text_input("副标题 / 说明", key=SS + "subtitle_in")
    with c3:
        draft["exam_minutes"] = st.number_input(
            "时长(分)", min_value=0, max_value=600, key=SS + "minutes_in"
        )

    total_items = sum(len(s["items"]) for s in draft["sections"])
    total_score = sum(it["score"] for s in draft["sections"] for it in s["items"])
    st.caption(f"共 **{total_items}** 题，总分 **{total_score}** 分")

    # ---- 一次性批量拿题目信息 ----
    all_qids = [it["question_id"] for s in draft["sections"] for it in s["items"]]
    qmap = ps.get_questions_by_ids(all_qids)

    # ---- 添加大题 ----
    with st.expander("➕ 添加大题", expanded=False):
        nc1, nc2 = st.columns([3, 1])
        with nc1:
            st.text_input("大题标题", key=SS + "new_sec_title",
                          placeholder="如：二、填空题")
        with nc2:
            st.write("")  # 对齐
            st.button("添加", use_container_width=True, key=SS + "add_sec",
                      on_click=_cb_add_section)

    # ---- 遍历每个大题 ----
    for si, sec in enumerate(draft["sections"]):
        with st.container(border=True):
            head_l, head_r = st.columns([5, 1])
            with head_l:
                sec["title"] = st.text_input(
                    "大题标题",
                    value=sec["title"],
                    key=f"{SS}sec_title_{sec['sec_id']}",
                    label_visibility="collapsed",
                )
            with head_r:
                if st.button("🗑️ 删除大题", key=f"{SS}del_sec_{sec['sec_id']}",
                             use_container_width=True):
                    draft["sections"].pop(si)
                    st.rerun()

            items = sec["items"]
            if not items:
                st.caption("_该大题还没有题目_")
            else:
                for ii, it in enumerate(items):
                    _render_item_row(sec, si, ii, it, qmap)

    if total_items == 0:
        st.info("试卷还是空的。请从左侧选题后加入。")


def _render_item_row(sec, si, ii, it, qmap):
    qid = it["question_id"]
    q = qmap.get(qid)

    c1, c2, c3, c4, c5 = st.columns([6, 1, 1, 1, 1])
    with c1:
        if q is None:
            st.markdown(f"⚠️ **{ii + 1}.** 题目 #{qid}（已在题库中删除）")
        else:
            preview = strip_latex_for_preview(q.stem, 55) or "（空题干）"
            st.markdown(f"**{ii + 1}.** `{q.qtype or '—'}` {preview}")
    with c2:
        new_score = st.number_input(
            "分", min_value=1, max_value=100,
            value=int(it["score"]),
            key=f"{SS}score_{it['item_id']}",
            label_visibility="collapsed",
        )
        if int(new_score) != int(it["score"]):
            it["score"] = int(new_score)
    with c3:
        if st.button("⬆️", key=f"{SS}up_{it['item_id']}",
                     disabled=(ii == 0), use_container_width=True):
            sec["items"][ii - 1], sec["items"][ii] = sec["items"][ii], sec["items"][ii - 1]
            st.rerun()
    with c4:
        if st.button("⬇️", key=f"{SS}dn_{it['item_id']}",
                     disabled=(ii == len(sec["items"]) - 1), use_container_width=True):
            sec["items"][ii + 1], sec["items"][ii] = sec["items"][ii], sec["items"][ii + 1]
            st.rerun()
    with c5:
        if st.button("✖", key=f"{SS}rm_{it['item_id']}", use_container_width=True):
            sec["items"].pop(ii)
            st.rerun()


# ------------------------------------------------------------
# 保存
# ------------------------------------------------------------
def _save(draft):
    title = (draft["title"] or "").strip() or "未命名试卷"
    if not any(s["items"] for s in draft["sections"]):
        st.error("试卷里至少要有 1 道题才能保存。")
        return
    try:
        if draft["id"] is None:
            new_id = ps.create_paper(
                title=title,
                subtitle=draft["subtitle"],
                exam_minutes=draft["exam_minutes"],
                sections=draft["sections"],
            )
            _flash(f"试卷已保存，编号 #{new_id}")
        else:
            ok = ps.update_paper(
                paper_id=draft["id"],
                title=title,
                subtitle=draft["subtitle"],
                exam_minutes=draft["exam_minutes"],
                sections=draft["sections"],
            )
            if not ok:
                st.error("保存失败：试卷不存在或已被删除。")
                return
            _flash(f"试卷 #{draft['id']} 已更新")
    except Exception as e:
        st.error(f"保存失败：{e}")
        return
    _close_editor()
    st.rerun()


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()
    _show_flash()

    if st.session_state[SS + "editing"] is None:
        _render_list()
    else:
        _ensure_draft()
        _render_editor()