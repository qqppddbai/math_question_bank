# -*- coding: utf-8 -*-
"""手动组卷页面：列表 → 编辑器（上：试卷结构 / 下：从题库选题）。

草稿（draft）保存在 st.session_state["pp_draft"]，是一个「按加入顺序排列的题目 id 列表」：
    {"id": int|None, "title": str, "subtitle": str, "question_ids": [12, 5, 30]}

- 题目顺序 = 点击「加入试卷」的先后顺序（组内）。
- **大题不用手工建**：保存/展示时按题目自己的题型自动分组，
  顺序固定为 单选题 → 多选题 → 填空题 → 判断题 → 作图题 → 解答题，没有的题型自动跳过。
- 不设分值：试卷不再涉及分数。
"""
from __future__ import annotations

import streamlit as st

from src.services import data_cache as dc
from src.services import paper_service as ps
from src.services import question_service as qs
from src.ui import question_card as qc
from src.ui import question_filter as qf
from src.utils.latex import strip_latex_for_preview

SS = "pp_"

PICKER_PAGE_SIZE = 10   # 选题区每页显示多少张题目卡片

# 大题的固定顺序；不在这个列表里的题型归到最后
SECTION_ORDER = ["单选题", "多选题", "填空题", "判断题", "作图题", "解答题"]
_FALLBACK_TYPE = "解答题"
_CN_DIGITS = "零一二三四五六七八九十"


def _cn_num(n: int) -> str:
    """1 -> 一，2 -> 二 …… 11 -> 十一。"""
    if n <= 10:
        return _CN_DIGITS[n]
    if n < 20:
        return "十" + _CN_DIGITS[n - 10]
    return str(n)


def _group_by_type(question_ids, qmap):
    """把题目 id 列表按题型分组。

    返回 [{"title": "一、单选题", "qtype": "单选题", "entries": [(平铺下标, qid), ...]}, ...]
    entries 里保留原始下标，方便上下移动时直接操作平铺列表。
    """
    buckets = {}
    for idx, qid in enumerate(question_ids):
        q = qmap.get(qid)
        qtype = (getattr(q, "qtype", "") or "").strip() or _FALLBACK_TYPE
        if qtype not in SECTION_ORDER:
            qtype = _FALLBACK_TYPE
        buckets.setdefault(qtype, []).append((idx, qid))

    groups = []
    for qtype in SECTION_ORDER:
        if qtype in buckets:
            groups.append({
                "qtype": qtype,
                "entries": buckets[qtype],
            })
    for i, g in enumerate(groups, start=1):
        g["title"] = f"{_cn_num(i)}、{g['qtype']}"
    return groups


# ============================================================
# 状态
# ============================================================
def _init_state():
    st.session_state.setdefault(SS + "editing", None)          # None / 'new' / int
    st.session_state.setdefault(SS + "draft", None)
    st.session_state.setdefault(SS + "loaded_for", "__none__")  # 上次加载的 editing 值
    st.session_state.setdefault(SS + "confirm_delete", None)
    qf.init_filter_state(SS)   # 提供 pp_page / pp_filter_fp


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
    qf.clear_filters(SS)


# ============================================================
# 列表页
# ============================================================
def _render_list():
    st.header("📝 手动组卷")
    st.caption(
        "从题库挑题组成试卷；加入顺序就是卷面顺序，"
        "大题会按题型自动分好，不用手工建。"
    )

    _, top_r = st.columns([4, 1])
    with top_r:
        if st.button("➕ 新建试卷", type="primary", width="stretch"):
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
                    f"{sub_line}共 {p['item_count']} 题 · "
                    f"更新于 {p['updated_at']:%Y-%m-%d %H:%M}"
                )
            with c2:
                if st.button("✏️ 编辑", key=f"{SS}p_edit_{p['id']}", width="stretch"):
                    st.session_state[SS + "editing"] = p["id"]
                    st.rerun()
            with c3:
                if st.session_state.get(SS + "confirm_delete") == p["id"]:
                    if st.button("⚠️ 确认", key=f"{SS}p_cdel_{p['id']}",
                                 type="primary", width="stretch"):
                        ps.soft_delete_paper(p["id"])
                        st.session_state[SS + "confirm_delete"] = None
                        _flash("试卷已删除（可在回收站还原）", "warning")
                        st.rerun()
                else:
                    if st.button("🗑️ 删除", key=f"{SS}p_del_{p['id']}",
                                 width="stretch"):
                        st.session_state[SS + "confirm_delete"] = p["id"]
                        st.rerun()
            with c4:
                if st.session_state.get(SS + "confirm_delete") == p["id"]:
                    if st.button("取消", key=f"{SS}p_cancel_{p['id']}",
                                 width="stretch"):
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
            "question_ids": [],
        }

    detail = ps.get_paper_detail(int(paper_id))
    if detail is None:
        return None

    # 已有试卷按库里的顺序（order_index）还原成平铺列表
    question_ids = [
        it["question_id"]
        for sec in detail["sections"]
        for it in sec["items"]
    ]
    return {
        "id": detail["id"],
        "title": detail["title"],
        "subtitle": detail["subtitle"],
        "question_ids": question_ids,
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


# ============================================================
# 编辑器主体
# ============================================================
def _render_editor():
    draft = st.session_state[SS + "draft"]

    head_l, head_r = st.columns([5, 1])
    with head_l:
        st.header("➕ 新建试卷" if draft["id"] is None else f"✏️ 编辑试卷 #{draft['id']}")
    with head_r:
        if st.button("⬅️ 返回列表", width="stretch"):
            _close_editor()
            st.rerun()

    _render_structure(draft)
    st.divider()
    _render_picker(draft)

    st.divider()
    b1, b2, _, _ = st.columns([1, 1, 1, 4])
    with b1:
        if st.button("💾 保存试卷", type="primary", width="stretch"):
            _save(draft)
    with b2:
        if st.button("取消", width="stretch"):
            _close_editor()
            st.rerun()


# ------------------------------------------------------------
# 选题区：题目卡片 + 逐题加入（顺序 = 点击顺序）
# ------------------------------------------------------------
def _render_picker(draft):
    st.subheader("📚 从题库选题")
    st.caption(
        "筛选条件与「搜索筛选」页一致。点卡片上的 **➕ 加入试卷**，"
        "就会**按你点击的先后顺序**加入；题型不同的大题由系统自动分好。"
    )

    filters = qf.render_filter_panel(SS, expanded=False)
    total = qf.count_matching(filters)
    if total == 0:
        st.info("没有匹配的题目。试试放宽筛选条件，或点「🔄 清空筛选」。")
        return

    # ---- 分页导航 ----
    total_pages = max(1, (total + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = min(max(1, st.session_state.get(SS + "page", 1)), total_pages)
    st.session_state[SS + "page"] = page

    nav_l, nav_c, nav_r = st.columns([1, 3, 1])
    with nav_l:
        if st.button("⬅️ 上一页", disabled=(page <= 1), width="stretch",
                     key=SS + "pk_prev"):
            st.session_state[SS + "page"] = page - 1
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
            st.session_state[SS + "page"] = page + 1
            st.rerun()

    rows = dc.search_questions(**filters, limit=PICKER_PAGE_SIZE,
                               offset=(page - 1) * PICKER_PAGE_SIZE)

    already = set(draft["question_ids"])
    for q in rows:
        _render_picker_card(draft, q, q.id in already)


def _render_picker_card(draft, q, already_in):
    """选题卡片：题目展示与「题目管理」完全一致，右侧按钮为本题「加入试卷」。"""
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
                _add_one(draft, q)
                st.rerun()
            st.caption(f"→ {q.qtype or '解答题'}")

    qc.render_answer_expander(q, key="pick")


def _add_one(draft, q):
    """把一道题追加到列表末尾 —— 因此卷内顺序就是点击顺序。"""
    if q.id in draft["question_ids"]:
        _flash(f"题目 #{q.id} 已经在试卷里了，已跳过", "warning")
        return
    draft["question_ids"].append(q.id)
    _flash(f"题目 #{q.id} 已加入「{q.qtype or '解答题'}」，共 {len(draft['question_ids'])} 题")


# ------------------------------------------------------------
# 试卷结构（按题型自动分组）
# ------------------------------------------------------------
def _render_structure(draft):
    st.subheader("📝 试卷结构")

    c1, c2 = st.columns([3, 3])
    with c1:
        draft["title"] = st.text_input("试卷标题", key=SS + "title_in")
    with c2:
        draft["subtitle"] = st.text_input("副标题 / 说明", key=SS + "subtitle_in")

    qids = draft["question_ids"]
    qmap = ps.get_questions_by_ids(qids)
    st.caption(f"共 **{len(qids)}** 题")

    if not qids:
        st.info("试卷还是空的。请在下方「从题库选题」里点「➕ 加入试卷」。")
        return

    groups = _group_by_type(qids, qmap)
    pos = 0   # 全卷连续编号
    for g in groups:
        with st.container(border=True):
            st.markdown(f"**{g['title']}**　"
                        f"<span style='color:#666;font-size:0.85em'>"
                        f"共 {len(g['entries'])} 题</span>",
                        unsafe_allow_html=True)
            for gi, (flat_idx, qid) in enumerate(g["entries"]):
                pos += 1
                _render_item_row(draft, g, gi, flat_idx, qid, pos, qmap)


def _render_item_row(draft, group, gi, flat_idx, qid, number, qmap):
    q = qmap.get(qid)
    c1, c2, c3, c4 = st.columns([7, 1, 1, 1])
    with c1:
        if q is None:
            st.markdown(f"⚠️ **{number}.** 题目 #{qid}（已在题库中删除）")
        else:
            preview = strip_latex_for_preview(q.stem, 50) or "（空题干）"
            st.markdown(f"**{number}.** {preview}")
    with c2:
        if st.button("⬆️", key=f"{SS}up_{qid}",
                     disabled=(gi == 0), width="stretch"):
            a = group["entries"][gi - 1][0]
            b = flat_idx
            draft["question_ids"][a], draft["question_ids"][b] = \
                draft["question_ids"][b], draft["question_ids"][a]
            st.rerun()
    with c3:
        if st.button("⬇️", key=f"{SS}dn_{qid}",
                     disabled=(gi == len(group["entries"]) - 1), width="stretch"):
            a = flat_idx
            b = group["entries"][gi + 1][0]
            draft["question_ids"][a], draft["question_ids"][b] = \
                draft["question_ids"][b], draft["question_ids"][a]
            st.rerun()
    with c4:
        if st.button("✖", key=f"{SS}rm_{qid}", width="stretch"):
            draft["question_ids"].pop(flat_idx)
            st.rerun()


# ------------------------------------------------------------
# 保存
# ------------------------------------------------------------
def _build_sections(draft) -> list:
    """按题型把题目组织成 paper_service 需要的 sections 结构（不含分值）。"""
    qmap = ps.get_questions_by_ids(draft["question_ids"])
    sections = []
    for g in _group_by_type(draft["question_ids"], qmap):
        sections.append({
            "title": g["title"],
            "items": [
                {"question_id": qid, "score": 0}
                for _, qid in g["entries"]
            ],
        })
    return sections


def _save(draft):
    title = (draft["title"] or "").strip() or "未命名试卷"
    if not draft["question_ids"]:
        st.error("试卷里至少要有 1 道题才能保存。")
        return
    sections = _build_sections(draft)
    try:
        if draft["id"] is None:
            new_id = ps.create_paper(
                title=title,
                subtitle=draft["subtitle"],
                exam_minutes=0,
                sections=sections,
            )
            _flash(f"试卷已保存，编号 #{new_id}")
        else:
            ok = ps.update_paper(
                paper_id=draft["id"],
                title=title,
                subtitle=draft["subtitle"],
                exam_minutes=0,
                sections=sections,
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
