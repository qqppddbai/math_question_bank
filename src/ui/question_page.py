# -*- coding: utf-8 -*-
"""题目管理页面：列表 + 新增/编辑表单 + 详情展开 + 软删除。"""
from __future__ import annotations

import streamlit as st

from src.config import (CHOICE_TYPES, DIFFICULTY_LABELS, GRADES, OPTION_KEYS,
                        QTYPES)
from src.services import question_service as qs
from src.ui import question_card as qc
from src.utils import file_utils
from src.utils.latex import md

PAGE_SIZE = 20
THUMB_WIDTH = qc.THUMB_WIDTH   # 缩略图宽度（像素）
EDIT_PREFIX = "q_edit_"   # 编辑表单所有 widget key 的前缀，便于整体清空

# ============================================================
# session_state 初始化与工具
# ============================================================
def _init_state():
    st.session_state.setdefault("q_editing", None)   # None / 'new' / int
    st.session_state.setdefault("q_page", 1)
    st.session_state.setdefault("q_confirm_delete", None)


def _clear_edit_widgets():
    """清空编辑表单所有 widget 状态，避免切换到下一题时残留旧值。"""
    for k in list(st.session_state.keys()):
        if k.startswith(EDIT_PREFIX):
            del st.session_state[k]


def _open_new():
    _clear_edit_widgets()
    st.session_state["q_editing"] = "new"


def _open_edit(qid: int):
    _clear_edit_widgets()
    st.session_state["q_editing"] = int(qid)


def _close_editor():
    _clear_edit_widgets()
    st.session_state["q_editing"] = None


def _flash(msg: str, kind: str = "success"):
    """暂存一条提示，下次 rerun 时展示。"""
    st.session_state["_flash"] = (kind, msg)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


# ============================================================
# 列表页
# ============================================================
def _render_list():
    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.subheader("📚 题目管理")
        st.caption("点击题目卡片查看详情；点右上角 ➕ 新增。删除的题目可在「回收站」找回。")
    with top_r:
        st.write("")  # 让按钮与标题对齐
        if st.button("➕ 新增题目", type="primary", width="stretch"):
            _open_new()
            st.rerun()

    # ---------- 快捷筛选（详细筛选见「搜索筛选」页） ----------
    with st.expander("🔎 快捷筛选", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kw = st.text_input("关键词", key="q_filter_kw",
                               placeholder="题干 / 答案 / 来源 / 标签")
        with c2:
            f_qtype = st.selectbox("题型", [""] + QTYPES, key="q_filter_qtype")
        with c3:
            f_grade = st.selectbox("年级", [""] + GRADES, key="q_filter_grade")
        with c4:
            f_chapter = st.text_input("章节包含", key="q_filter_chapter")

    kw = st.session_state.get("q_filter_kw", "")
    f_qtype = st.session_state.get("q_filter_qtype", "")
    f_grade = st.session_state.get("q_filter_grade", "")
    f_chapter = st.session_state.get("q_filter_chapter", "")

    total = qs.count_questions(keyword=kw, qtype=f_qtype, grade=f_grade, chapter=f_chapter)
    if total == 0:
        st.info("没有符合条件的题目。可以调整筛选条件，或点右上角「➕ 新增题目」。")
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(1, st.session_state.get("q_page", 1)), total_pages)
    st.session_state["q_page"] = page

    # ---------- 分页导航 ----------
    nav_l, nav_c, nav_r = st.columns([1, 3, 1])
    with nav_l:
        if st.button("⬅️ 上一页", disabled=(page <= 1), width="stretch"):
            st.session_state["q_page"] = page - 1
            st.rerun()
    with nav_c:
        st.markdown(
            f"<div style='text-align:center;padding-top:6px;color:#666'>"
            f"共 <b>{total}</b> 道 · 第 <b>{page}</b> / {total_pages} 页</div>",
            unsafe_allow_html=True,
        )
    with nav_r:
        if st.button("下一页 ➡️", disabled=(page >= total_pages), width="stretch"):
            st.session_state["q_page"] = page + 1
            st.rerun()

    rows = qs.list_questions(
        keyword=kw, qtype=f_qtype, grade=f_grade, chapter=f_chapter,
        limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE,
    )

    for q in rows:
        _render_question_card(q)


def _render_question_card(q):
    """题目卡片。

    题目展示部分（元信息 / 题干 / 选项 / 配图 / 答案与解析）统一走
    src/ui/question_card.py，与「搜索筛选」「手动组卷」共用同一套渲染，
    保证三处版面完全一致（宋体六号）。

    结构：
        [带边框容器 · 无标题]
            [st-key-qdisp_card_* ：题目内容]
        [折叠面板：📖 查看答案与解析]
        [✏️ 编辑] [🗑️ 删除]
    """
    # ---------- 卡片主体 ----------
    with st.container(border=True):
        qc.render_body(q, key="card", thumb_prefix=f"card_{q.id}")

    # ---------- 答案与解析 ----------
    qc.render_answer_expander(q, key="card")

    # ---------- 编辑 / 删除 ----------
    act_l, act_m, act_r = st.columns([1, 1, 5])
    with act_l:
        if st.button("✏️ 编辑", key=f"edit_{q.id}", use_container_width=True):
            _open_edit(q.id)
            st.rerun()
    with act_m:
        if st.session_state.get("q_confirm_delete") == q.id:
            if st.button("⚠️ 确认删除", key=f"confirm_del_{q.id}",
                         type="primary", use_container_width=True):
                qs.soft_delete_question(q.id)
                st.session_state["q_confirm_delete"] = None
                _flash(f"题目 #{q.id} 已移入回收站")
                st.rerun()
        else:
            if st.button("🗑️ 删除", key=f"del_{q.id}", use_container_width=True):
                st.session_state["q_confirm_delete"] = q.id
                st.rerun()
    with act_r:
        if st.session_state.get("q_confirm_delete") == q.id:
            if st.button("取消删除", key=f"cancel_del_{q.id}"):
                st.session_state["q_confirm_delete"] = None
                st.rerun()

# ============================================================
# 编辑器
# ============================================================
def _init_edit_defaults(q):
    """按现有题目（或空）初始化编辑表单的 widget 状态。"""
    def setdef(key, value):
        if key not in st.session_state:
            st.session_state[key] = value

    setdef(EDIT_PREFIX + "qtype", q.qtype if q else "解答题")
    setdef(EDIT_PREFIX + "grade", q.grade if q else "")
    setdef(EDIT_PREFIX + "chapter", q.chapter if q else "")
    setdef(EDIT_PREFIX + "difficulty", q.difficulty if q else 3)
    setdef(EDIT_PREFIX + "stem", q.stem if q else "")
    setdef(EDIT_PREFIX + "answer", q.answer if q else "")
    setdef(EDIT_PREFIX + "analysis", q.analysis if q else "")
    setdef(EDIT_PREFIX + "knowledge", q.knowledge if q else "")
    setdef(EDIT_PREFIX + "tags", q.tags if q else "")
    setdef(EDIT_PREFIX + "source", q.source if q else "")

    opts = {o["key"]: o["text"] for o in (q.options_list if q else [])}
    for k in OPTION_KEYS:
        setdef(EDIT_PREFIX + f"opt_{k}", opts.get(k, ""))

    # 已有图片：列表 + 每张一个"标记删除"复选框
    setdef(EDIT_PREFIX + "existing_images", list(q.image_list) if q else [])
    for i, _ in enumerate(st.session_state[EDIT_PREFIX + "existing_images"]):
        setdef(EDIT_PREFIX + f"img_del_{i}", False)


def _render_editor():
    qid = st.session_state["q_editing"]
    is_new = (qid == "new")
    q = None if is_new else qs.get_question(qid)

    if not is_new and q is None:
        st.error("题目不存在或已被删除。")
        _close_editor()
        st.rerun()
        return

    _init_edit_defaults(q)

    head_l, head_r = st.columns([3, 1])
    with head_l:
        st.subheader("➕ 新增题目" if is_new else f"✏️ 编辑题目 #{q.id}")
    with head_r:
        if st.button("⬅️ 返回列表", width="stretch"):
            _close_editor()
            st.rerun()

    st.caption("公式用 LaTeX 书写，例如 $x^2+y^2=r^2$；行内用单个 $ 包裹，独立公式用 $$。")

    # -------- 分类信息 --------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.selectbox("题型", QTYPES, key=EDIT_PREFIX + "qtype")
    with c2:
        st.selectbox("年级", [""] + GRADES, key=EDIT_PREFIX + "grade")
    with c3:
        st.text_input("章节", key=EDIT_PREFIX + "chapter", placeholder="如：导数")
    with c4:
        st.selectbox(
            "难度", [1, 2, 3, 4, 5],
            format_func=lambda x: DIFFICULTY_LABELS[x],
            key=EDIT_PREFIX + "difficulty",
        )

    st.divider()

    # -------- 题干 + 实时预览 --------
    st.markdown("### 题干")
    sc1, sc2 = st.columns(2)
    with sc1:
        st.text_area(
            "题干（支持 LaTeX）",
            key=EDIT_PREFIX + "stem",
            height=240,
            label_visibility="collapsed",
            placeholder="例如：已知函数 $f(x)=x^2-2x$，求 ...",
        )
    with sc2:
        st.caption("实时预览")
        preview_box = st.container(border=True, height=240,
                                  key="qdisp_preview_stem")
        with preview_box:
            stem_now = st.session_state.get(EDIT_PREFIX + "stem", "")
            st.markdown(md(stem_now) if stem_now.strip() else "_（暂无内容）_")

    # -------- 选项（仅单选/多选） --------
    current_qtype = st.session_state.get(EDIT_PREFIX + "qtype", "")
    if current_qtype in CHOICE_TYPES:
        st.markdown("### 选项")
        st.caption("固定 A~D 四个选项，公式用 LaTeX。")
        ocols = st.columns(4)
        for i, k in enumerate(OPTION_KEYS):
            with ocols[i]:
                st.text_input(f"{k}．", key=EDIT_PREFIX + f"opt_{k}")

    # -------- 答案 & 解析 --------
    st.markdown("### 答案")
    st.text_area(
        "答案", key=EDIT_PREFIX + "answer", height=100,
        label_visibility="collapsed",
        placeholder="例如：(1) 见解析；(2) $(-\\infty,-\\sqrt{2})\\cup(\\sqrt{2},+\\infty)$",
    )

    st.markdown("### 解析")
    ac1, ac2 = st.columns(2)
    with ac1:
        st.text_area(
            "解析", key=EDIT_PREFIX + "analysis", height=200,
            label_visibility="collapsed",
        )
    with ac2:
        st.caption("实时预览")
        with st.container(border=True, height=200, key="qdisp_preview_analysis"):
            ana_now = st.session_state.get(EDIT_PREFIX + "analysis", "")
            st.markdown(md(ana_now) if ana_now.strip() else "_（暂无内容）_")

    # -------- 元信息 --------
    st.divider()
    m1, m2, m3 = st.columns(3)
    with m1:
        st.text_input("来源", key=EDIT_PREFIX + "source", placeholder="如：2023年新课标全国Ⅱ卷")
    with m2:
        st.text_input("知识点（逗号分隔）", key=EDIT_PREFIX + "knowledge",
                      placeholder="如：不等式证明,极值点,分类讨论")
    with m3:
        st.text_input("标签（逗号分隔）", key=EDIT_PREFIX + "tags",
                      placeholder="如：高考真题,新高考II卷")

    # -------- 图片 --------
    st.divider()
    st.markdown("### 图片")
    existing = st.session_state.get(EDIT_PREFIX + "existing_images", [])
    if existing:
        st.caption("已有图片（勾选“删”后保存即删除）")
        icols = st.columns(min(6, len(existing)))
        for i, rel in enumerate(existing):
            with icols[i % len(icols)]:
                p = file_utils.abs_path(rel)
                if p.is_file():
                    st.image(str(p), width=THUMB_WIDTH)
                else:
                    st.caption("图片已丢失")
                st.checkbox("删", key=EDIT_PREFIX + f"img_del_{i}")

    st.file_uploader(
        "上传新图片（png / jpg / webp / gif，≤5MB）",
        type=["png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=True,
        key=EDIT_PREFIX + "uploader",
    )

    # -------- 保存 / 取消 --------
    st.divider()
    bcol1, bcol2, _ = st.columns([1, 1, 4])
    with bcol1:
        if st.button("💾 保存", type="primary", width="stretch"):
            _save_current(q, is_new)
    with bcol2:
        if st.button("取消", width="stretch"):
            _close_editor()
            st.rerun()


def _collect_data_from_state():
    """从 session_state 收集表单数据，返回 dict。"""
    p = EDIT_PREFIX
    data = {
        "qtype": st.session_state.get(p + "qtype", ""),
        "grade": st.session_state.get(p + "grade", ""),
        "chapter": st.session_state.get(p + "chapter", ""),
        "difficulty": st.session_state.get(p + "difficulty", 3),
        "stem": st.session_state.get(p + "stem", ""),
        "answer": st.session_state.get(p + "answer", ""),
        "analysis": st.session_state.get(p + "analysis", ""),
        "knowledge": st.session_state.get(p + "knowledge", ""),
        "tags": st.session_state.get(p + "tags", ""),
        "source": st.session_state.get(p + "source", ""),
    }
    # 选项：仅选择类保留
    if data["qtype"] in CHOICE_TYPES:
        data["options_list"] = [
            {"key": k, "text": st.session_state.get(p + f"opt_{k}", "")}
            for k in OPTION_KEYS
        ]
    else:
        data["options_list"] = []

    # 图片：过滤掉被标记删除的，再追加新上传的
    existing = st.session_state.get(p + "existing_images", [])
    keep = [rel for i, rel in enumerate(existing)
            if not st.session_state.get(p + f"img_del_{i}", False)]
    # 真正删除磁盘文件放到 save 成功后
    data["_to_delete_files"] = [rel for i, rel in enumerate(existing)
                                if st.session_state.get(p + f"img_del_{i}", False)]
    data["_keep_images"] = keep
    return data


def _save_current(q, is_new: bool):
    data = _collect_data_from_state()

    if not data["stem"].strip():
        st.error("题干不能为空，请先填写题干。")
        return

    # 处理新上传的图片
    uploader_key = EDIT_PREFIX + "uploader"
    uploaded = st.session_state.get(uploader_key) or []
    new_files = []
    try:
        for f in uploaded:
            rel = file_utils.save_uploaded_image(f)
            new_files.append(rel)
    except ValueError as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"图片保存失败：{e}")
        return

    final_images = list(data["_keep_images"]) + new_files
    payload = {
        "qtype": data["qtype"], "grade": data["grade"], "chapter": data["chapter"],
        "difficulty": data["difficulty"], "stem": data["stem"],
        "answer": data["answer"], "analysis": data["analysis"],
        "knowledge": data["knowledge"], "tags": data["tags"], "source": data["source"],
        "options_list": data["options_list"], "image_list": final_images,
    }

    try:
        if is_new:
            new_id = qs.create_question(payload)
            msg = f"新增成功，题目编号 #{new_id}"
        else:
            ok = qs.update_question(q.id, payload)
            if not ok:
                st.error("保存失败：题目不存在或已被删除。")
                return
            msg = f"题目 #{q.id} 已更新"
    except Exception as e:
        st.error(f"保存失败：{e}")
        return

    # 保存成功后再真正删除被标记的磁盘图片
    for rel in data["_to_delete_files"]:
        file_utils.delete_file_silently(rel)

    _close_editor()
    _flash(msg)
    st.rerun()


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()
    _show_flash()
    if st.session_state["q_editing"] is None:
        _render_list()
    else:
        _render_editor()