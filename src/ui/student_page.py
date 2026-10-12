# -*- coding: utf-8 -*-
"""学生档案页面：列表 → 学生详情（信息 + 错题 + 学习图片）。

关键约定：
- 所有对 widget 状态的修改都发生在 widget 渲染之前（回调 / render 开头处理 flag）；
- 「添加错题」表单用 form_seq 生成一次性 widget key，避免切换题目时残留旧输入。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
import re

from datetime import datetime
from src.exporters import student_exporter as se
from src.services import question_service as qsvc
from src.services import student_service as ssvc
from src.ui import question_card as qc
from src.utils import file_utils
from src.utils.latex import md, strip_latex_for_preview
from src.config import EXPORT_DIR, GRADES, QTYPES


SS = "sp_"
THUMB_WIDTH = 110

MASTERY_LABELS = {
    0: "❌ 未掌握",
    1: "⚠️ 部分掌握",
    2: "✅ 基本掌握",
    3: "🌟 已掌握",
}


# ============================================================
# 状态
# ============================================================
def _init_state():
    st.session_state.setdefault(SS + "view", None)               # None | "new" | int
    st.session_state.setdefault(SS + "edit_info", False)
    st.session_state.setdefault(SS + "adding_mistake", False)
    st.session_state.setdefault(SS + "picker_qid", None)
    st.session_state.setdefault(SS + "form_seq", 0)
    st.session_state.setdefault(SS + "confirm_delete", None)
    st.session_state.setdefault(SS + "confirm_del_mistake", None)
    st.session_state.setdefault(SS + "editing_mistake", None)
    st.session_state.setdefault(SS + "upload_seq", 0)   # 上传器 key 的版本号
    st.session_state.setdefault(SS + "export_results", {})

def _flash(msg: str, kind: str = "success"):
    st.session_state["_flash"] = (kind, msg)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


def _open_add_mistake():
    st.session_state[SS + "adding_mistake"] = True
    st.session_state[SS + "picker_qid"] = None
    # 每次打开都换一组 widget key，避免上次输入残留
    st.session_state[SS + "form_seq"] = st.session_state.get(SS + "form_seq", 0) + 1


def _close_add_mistake():
    st.session_state[SS + "adding_mistake"] = False
    st.session_state[SS + "picker_qid"] = None


# ============================================================
# 缩略图
# ============================================================
def _render_thumbnails(files, key_prefix: str, allow_delete: bool = True):
    if not files:
        return
    cols = st.columns(min(6, len(files)))
    for i, f in enumerate(files):
        with cols[i % len(cols)]:
            p = file_utils.abs_path(f["path"])
            if p.is_file():
                st.image(str(p), width=THUMB_WIDTH)
            else:
                st.caption("图片丢失")
            if f.get("caption"):
                st.caption(f["caption"])
            if allow_delete:
                if st.button("✖ 删除", key=f"{SS}{key_prefix}_del_{f['id']}",
                             use_container_width=True):
                    ssvc.delete_student_file(f["id"])
                    _flash("图片已删除", "warning")
                    st.rerun()


# ============================================================
# 列表页
# ============================================================
def _render_list():
    st.header("👨‍🎓 学生档案")

    _, top_r = st.columns([4, 1])
    with top_r:
        if st.button("➕ 新建学生", type="primary", use_container_width=True):
            st.session_state[SS + "view"] = "new"
            st.rerun()

    # 筛选
    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("搜索（姓名 / 学校 / 班级 / 备注）", key=SS + "list_kw")
    with c2:
        schools = ssvc.get_all_schools()
        st.selectbox("学校", [""] + schools, key=SS + "list_school")
    with c3:
        classes = ssvc.get_all_classes()
        st.selectbox("班级", [""] + classes, key=SS + "list_class")

    kw = st.session_state.get(SS + "list_kw", "")
    school = st.session_state.get(SS + "list_school", "")
    cls = st.session_state.get(SS + "list_class", "")

    students = ssvc.list_students(keyword=kw, class_name=cls, school=school)
    if not students:
        st.info("暂无学生。点右上角「➕ 新建学生」开始建档。")
    else:
        st.caption(f"共 **{len(students)}** 位学生")
        for stu in students:
            _render_student_card(stu)

    # 已删除学生
    deleted = ssvc.list_students(include_deleted=True)
    if deleted:
        with st.expander(f"🗑️ 已删除学生（{len(deleted)}）", expanded=False):
            st.caption("还原后回到学生列表；彻底删除不可恢复，图片文件也会一并删除。")
            for stu in deleted:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([5, 1, 1])
                    with c1:
                        st.markdown(f"**{stu['name'] or '（未命名）'}**")
                        st.caption(
                            f"{stu['class_name'] or '—'} · "
                            f"错题 {stu['mistake_count']} 道 · 图片 {stu['file_count']} 张"
                        )
                    with c2:
                        if st.button("♻️ 还原", key=f"{SS}rst_{stu['id']}",
                                     use_container_width=True):
                            ssvc.restore_student(stu["id"])
                            _flash("学生已还原")
                            st.rerun()
                    with c3:
                        if st.button("❌ 彻底删", key=f"{SS}hd_{stu['id']}",
                                     use_container_width=True):
                            ssvc.hard_delete_student(stu["id"])
                            _flash("学生已彻底删除", "warning")
                            st.rerun()


def _render_student_card(stu):
    with st.container(border=True):
        c1, c2, c3 = st.columns([5, 1, 1])
        with c1:
            name = stu["name"] or "（未命名）"
            meta = [x for x in (stu.get("school"), stu.get("class_name")) if x]
            meta_str = " · ".join(meta)
            st.markdown(f"**{name}**" + (f"　{meta_str}" if meta_str else ""))
            st.caption(f"错题 {stu['mistake_count']} 道 · 图片 {stu['file_count']} 张")
        with c2:
            if st.button("查看", key=f"{SS}v_{stu['id']}", use_container_width=True):
                st.session_state[SS + "view"] = stu["id"]
                st.rerun()
        with c3:
            if st.session_state.get(SS + "confirm_delete") == stu["id"]:
                if st.button("⚠️ 确认", key=f"{SS}cd_{stu['id']}",
                             type="primary", use_container_width=True):
                    ssvc.soft_delete_student(stu["id"])
                    st.session_state[SS + "confirm_delete"] = None
                    _flash("学生已删除（可在「已删除学生」中还原）", "warning")
                    st.rerun()
            else:
                if st.button("删除", key=f"{SS}d_{stu['id']}",
                             use_container_width=True):
                    st.session_state[SS + "confirm_delete"] = stu["id"]
                    st.rerun()


# ============================================================
# 新建学生
# ============================================================
def _render_new_student():
    c1, c2 = st.columns([4, 1])
    with c1:
        st.header("➕ 新建学生")
    with c2:
        if st.button("⬅️ 返回列表", use_container_width=True):
            st.session_state[SS + "view"] = None
            st.rerun()

    with st.container(border=True):
        name = st.text_input("姓名 *", key=SS + "new_name")
        c1, c2 = st.columns(2)
        with c1:
            school = st.text_input("学校", key=SS + "new_school",
                                   placeholder="如：南京外国语学校")
        with c2:
            cls = st.text_input("班级", key=SS + "new_class",
                                placeholder="如：高一(3)班")
        notes = st.text_area("备注", key=SS + "new_notes", height=100)

        b1, b2, _ = st.columns([1, 1, 4])
        with b1:
            if st.button("💾 保存", type="primary", use_container_width=True):
                if not name.strip():
                    st.error("姓名不能为空。")
                else:
                    sid = ssvc.create_student(name, cls, school, notes)
                    _flash(f"已创建学生「{name.strip()}」")
                    st.session_state[SS + "view"] = sid
                    st.rerun()
        with b2:
            if st.button("取消", use_container_width=True, key=SS + "new_cancel"):
                st.session_state[SS + "view"] = None
                st.rerun()


# ============================================================
# 学生详情
# ============================================================
def _render_detail(sid: int):
    stu = ssvc.get_student(sid)
    if stu is None:
        st.error("学生不存在或已删除。")
        st.session_state[SS + "view"] = None
        st.rerun()
        return

    # 切换学生时，上一份导出结果作废
    prev = st.session_state.get(SS + "export_results") or {}
    if prev and any(v.get("student_id") != sid for v in prev.values()):
        st.session_state[SS + "export_results"] = {}

    # 顶部导航
    c1, c2 = st.columns([1, 6])
    with c1:
        if st.button("⬅️ 返回", use_container_width=True):
            st.session_state[SS + "view"] = None
            st.session_state[SS + "edit_info"] = False
            st.session_state[SS + "adding_mistake"] = False
            st.session_state[SS + "editing_mistake"] = None
            st.rerun()
    with c2:
        st.header(f"👤 {stu.name or '（未命名）'}")

    _render_info_block(stu)
    st.divider()
    _render_export_block(stu)
    st.divider()
    _render_mistakes_section(stu)
    st.divider()
    _render_student_files_block(stu)


def _render_info_block(stu):
    with st.container(border=True):
        if st.session_state.get(SS + "edit_info"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("姓名", value=stu.name, key=SS + "ei_name")
                school = st.text_input("学校", value=stu.school, key=SS + "ei_school")
            with c2:
                cls = st.text_input("班级", value=stu.class_name, key=SS + "ei_class")
                st.write("")
            notes = st.text_area("备注", value=stu.notes, key=SS + "ei_notes", height=80)

            b1, b2, _ = st.columns([1, 1, 4])
            with b1:
                if st.button("💾 保存", type="primary", use_container_width=True,
                             key=SS + "ei_save"):
                    ssvc.update_student(stu.id, name=name, school=school,
                                        class_name=cls, notes=notes)
                    st.session_state[SS + "edit_info"] = False
                    _flash("信息已保存")
                    st.rerun()
            with b2:
                if st.button("取消", use_container_width=True, key=SS + "ei_cancel"):
                    st.session_state[SS + "edit_info"] = False
                    st.rerun()
        else:
            c1, c2 = st.columns([5, 1])
            with c1:
                parts = []
                if stu.school:
                    parts.append(f"学校：{stu.school}")
                if stu.class_name:
                    parts.append(f"班级：{stu.class_name}")
                st.markdown("　".join(parts) if parts else "_（未填写学校 / 班级）_")
                if stu.notes:
                    st.caption(f"备注：{stu.notes}")
            with c2:
                if st.button("✏️ 编辑信息", use_container_width=True, key=SS + "ei_open"):
                    st.session_state[SS + "edit_info"] = True
                    st.rerun()


# ------------------------------------------------------------
# 导出错题集 / 学习图片集
# ------------------------------------------------------------
def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name or "").strip() or "student"


def _render_export_block(stu):
    with st.expander("📤 导出（错题记录 / 学习图片 分开导出）", expanded=False):
        st.caption(
            "错题记录和学习图片是**两个独立文件**。"
            "错题记录里答案与解析统一放在**最后一页**（Word/HTML 会自动另起一页），"
            "正文部分只放题干、题目/错题图片、学生错答和错因分析，并标注章节与知识点。"
            "HTML 可在浏览器里打印成 PDF。"
        )

        c1, c2 = st.columns([2, 3])
        with c1:
            kind_label = st.radio(
                "导出内容",
                ["📕 错题记录", "🖼️ 学习图片"],
                key=SS + f"exp_kind_{stu.id}",
            )
        with c2:
            fmt = st.radio(
                "格式",
                ["Word（.docx）", "HTML（可打印 PDF）", "Markdown（.md）"],
                key=SS + f"exp_fmt_{stu.id}",
            )

        kind = "mistakes" if kind_label.startswith("📕") else "pictures"
        if st.button("🛠️ 生成文件", type="primary",
                     key=SS + f"exp_btn_{stu.id}_{kind}"):
            _do_export(stu, kind, fmt)

        results = st.session_state.get(SS + "export_results") or {}
        result = results.get(kind)
        if result:
            st.divider()
            st.success(f"✅ 已生成：`{result['filename']}`")
            st.caption(f"同时保存到：`{result['path']}`")

            dl_col, open_col = st.columns([1, 1])
            with dl_col:
                st.download_button(
                    "⬇️ 下载到本机",
                    data=result["data"],
                    file_name=result["filename"],
                    mime=result["mime"],
                    type="primary",
                    width="stretch",
                    key=SS + f"exp_dl_{stu.id}_{kind}",
                )
            with open_col:
                if st.button("📂 打开文件所在目录", width="stretch",
                             key=SS + f"exp_open_{stu.id}_{kind}"):
                    if file_utils.open_file_location(result["path"]):
                        st.toast("已在文件管理器中打开，并选中该文件", icon="📂")
                    else:
                        st.warning(
                            f"打不开目录（文件可能已被移动或删除）：`{result['path']}`"
                        )

            if result["filename"].endswith(".html"):
                st.info("提示：用浏览器打开 HTML → 按 **Ctrl + P** → 目标选「另存为 PDF」。")
            elif result["filename"].endswith(".docx"):
                st.info("提示：公式已转成 Word 原生公式（OMML），可直接编辑。")


def _do_export(stu, kind: str, fmt: str):
    """kind: 'mistakes' 只导错题记录；'pictures' 只导学习图片。"""
    try:
        mistakes = ssvc.list_mistakes(stu.id) if kind == "mistakes" else []
        all_files = ssvc.list_student_files(stu.id) if kind == "pictures" else []
        loose_files = [f for f in all_files if f["mistake_id"] is None]
        view = se.build_student_view(stu, mistakes, loose_files)
    except Exception as e:
        st.error(f"读取数据失败：{e}")
        return

    if kind == "mistakes" and not view.mistakes:
        st.warning("这个学生还没有错题记录。")
        return
    if kind == "pictures" and not view.loose_images:
        st.warning("这个学生还没有学习图片。")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _safe_filename(
        f"{stu.name or '学生'}_" + ("错题记录" if kind == "mistakes" else "学习图片")
    )

    try:
        if fmt.startswith("Word"):
            filename = f"{base}_{timestamp}.docx"
            target = EXPORT_DIR / filename
            if kind == "mistakes":
                se.export_mistakes_word(view, target)
            else:
                se.export_pictures_word(view, target)
            data = target.read_bytes()
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif fmt.startswith("HTML"):
            filename = f"{base}_{timestamp}.html"
            target = EXPORT_DIR / filename
            content = (se.export_mistakes_html(view) if kind == "mistakes"
                       else se.export_pictures_html(view))
            target.write_text(content, encoding="utf-8")
            data = content.encode("utf-8")
            mime = "text/html"
        else:
            filename = f"{base}_{timestamp}.md"
            target = EXPORT_DIR / filename
            content = (se.export_mistakes_markdown(view) if kind == "mistakes"
                       else se.export_pictures_markdown(view))
            target.write_text(content, encoding="utf-8")
            data = content.encode("utf-8")
            mime = "text/markdown"
    except Exception as e:
        st.error(f"生成失败：{e}")
        return

    results = dict(st.session_state.get(SS + "export_results") or {})
    results[kind] = {
        "student_id": stu.id,
        "filename": filename,
        "path": str(target),
        "data": data,
        "mime": mime,
    }
    st.session_state[SS + "export_results"] = results
    st.rerun()


# ------------------------------------------------------------
# 错题区
# ------------------------------------------------------------
def _render_mistakes_section(stu):
    st.subheader("📕 错题记录")

    if not st.session_state.get(SS + "adding_mistake"):
        c1, _ = st.columns([1, 5])
        with c1:
            if st.button("➕ 添加错题", type="primary", use_container_width=True):
                _open_add_mistake()
                st.rerun()
    else:
        _render_add_mistake_form(stu)
        st.divider()

    mistakes = ssvc.list_mistakes(stu.id)
    if not mistakes:
        st.info("还没有错题记录。点上方「➕ 添加错题」开始收录。")
        return

    st.caption(f"共 **{len(mistakes)}** 条")
    for m in mistakes:
        _render_mistake_card(stu.id, m)


def _render_add_mistake_form(stu):
    with st.container(border=True):
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown("**添加错题 · 先从题库选一道题**")
        with head_r:
            if st.button("✖ 取消", use_container_width=True, key=SS + "am_cancel_top"):
                _close_add_mistake()
                st.rerun()

        seq = st.session_state.get(SS + "form_seq", 0)

        # ---- 题库筛选 ----
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            kw = st.text_input("关键词", key=f"{SS}form_{seq}_kw",
                               placeholder="题干 / 来源 / 标签")
        with fc2:
            qtype = st.selectbox("题型", [""] + QTYPES, key=f"{SS}form_{seq}_qtype")
        with fc3:
            grade = st.selectbox("年级", [""] + GRADES, key=f"{SS}form_{seq}_grade")

        rows = qsvc.list_questions(keyword=kw, qtype=qtype, grade=grade, limit=50)
        if not rows:
            st.warning("没有匹配的题目，调整筛选条件试试。")
            return

        df = pd.DataFrame([{
            "ID": q.id,
            "题型": q.qtype or "—",
            "难度": "★" * q.difficulty,
            "题干预览": strip_latex_for_preview(q.stem, 50) or "（空）",
        } for q in rows])

        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=min(320, 60 + 36 * len(df)),
            on_select="rerun",
            selection_mode="single-row",
            key=f"{SS}form_{seq}_picker",
            column_config={
                "ID": st.column_config.NumberColumn(width="small"),
                "题干预览": st.column_config.TextColumn(width="large"),
            },
        )
        sel_rows = event.selection.rows if event and event.selection else []
        if sel_rows:
            st.session_state[SS + "picker_qid"] = rows[sel_rows[0]].id

        qid = st.session_state.get(SS + "picker_qid")
        if qid is None:
            st.caption("👆 点表格左侧行号选中一道题。")
            return

        q = next((x for x in rows if x.id == qid), None) or qsvc.get_question(qid)
        if q is None:
            st.warning("选中的题目找不到了，请重新选择。")
            return

        preview = q.stem if len(q.stem) <= 300 else q.stem[:300] + "…"
        # 题目显示统一为宋体六号（全局 CSS 用 .st-key-qdisp* 定位）
        with st.container(key=f"qdisp_pick_{q.id}_{seq}"):
            st.markdown(f"**已选：题目 #{q.id}**")
            st.markdown(md(preview))

        st.markdown("**填写错题信息**")
        c1, c2 = st.columns(2)
        with c1:
            wrong = st.text_area("学生错答", key=f"{SS}form_{seq}_wrong", height=80)
            reason = st.text_area("错因分析", key=f"{SS}form_{seq}_reason", height=80)
        with c2:
            mastery = st.selectbox(
                "掌握程度",
                [0, 1, 2, 3],
                format_func=lambda x: MASTERY_LABELS[x],
                key=f"{SS}form_{seq}_mastery",
            )

        b1, b2, _ = st.columns([1, 1, 4])
        with b1:
            if st.button("💾 保存错题", type="primary", use_container_width=True,
                         key=f"{SS}form_{seq}_save"):
                try:
                    ssvc.add_mistake(stu.id, qid, wrong, reason, mastery)
                except ValueError as e:
                    st.error(str(e))
                else:
                    _close_add_mistake()
                    _flash("错题已添加")
                    st.rerun()
        with b2:
            if st.button("取消", use_container_width=True, key=f"{SS}form_{seq}_cancel"):
                _close_add_mistake()
                st.rerun()


class _QuestionSnapshot:
    """把错题快照包装成 `question_card.render_body()` 需要的形状。

    题干用快照（历史记录不变样），选项/配图取题库当前值（题库没了就留空），
    这样错题卡片的题目展示就和「题目管理」完全一致。
    `id` 只用于生成容器 key（用错题 id，保证同一页面内唯一）。
    """

    def __init__(self, m: dict):
        self.id = f"mistake{m.get('id')}"
        self.stem = m.get("snapshot_stem") or ""
        self.qtype = m.get("qtype") or ""
        self.options_list = list(m.get("q_options") or [])
        self.image_list = list(m.get("q_images") or [])


def _render_mistake_card(student_id: int, m: dict):
    with st.container(border=True):
        c1, c2, c3 = st.columns([5, 1, 1])
        with c1:
            # 题目显示统一为宋体六号（全局 CSS 用 .st-key-qdisp* 定位）
            with st.container(key=f"qdisp_head_{m['id']}"):
                st.markdown(
                    f"**题目 #{m['question_id']}**　·　"
                    f"{MASTERY_LABELS.get(m['mastery'], '—')}"
                )
            st.caption(f"记录于 {m['created_at']:%Y-%m-%d %H:%M}")
        with c2:
            label = "✏️ 关闭" if st.session_state.get(SS + "editing_mistake") == m["id"] else "✏️ 编辑"
            if st.button(label, key=f"{SS}me_{m['id']}", width="stretch"):
                st.session_state[SS + "editing_mistake"] = (
                    None if st.session_state.get(SS + "editing_mistake") == m["id"] else m["id"]
                )
                st.rerun()
        with c3:
            if st.session_state.get(SS + "confirm_del_mistake") == m["id"]:
                if st.button("⚠️ 确认", key=f"{SS}mcd_{m['id']}", type="primary",
                             width="stretch"):
                    ssvc.delete_mistake(m["id"])
                    st.session_state[SS + "confirm_del_mistake"] = None
                    _flash("错题记录已删除", "warning")
                    st.rerun()
            else:
                if st.button("🗑️ 删除", key=f"{SS}md_{m['id']}", width="stretch"):
                    st.session_state[SS + "confirm_del_mistake"] = m["id"]
                    st.rerun()

        # ---------- 题目展示：与「题目管理」同一套渲染 ----------
        meta_line = "　".join(
            x for x in (
                f"章节：{m['chapter']}" if m.get("chapter") else "",
                f"知识点：{m['knowledge']}" if m.get("knowledge") else "",
            ) if x
        )
        meta_items = [(f"{MASTERY_LABELS.get(m['mastery'], '—')}", "")]
        if meta_line:
            meta_items.append(("", meta_line))
        qc.render_body(_QuestionSnapshot(m), key=f"m{m['id']}",
                       meta_items=meta_items, thumb_prefix=f"mk_{m['id']}")

        # ---------- 学生上传的错题图片 ----------
        if m["files"]:
            st.markdown("**错题图片**")
            _render_thumbnails(m["files"], key_prefix=f"m_{m['id']}")

        # ---------- 学生错答 / 错因 ----------
        if m["wrong_answer"] or m["error_reason"]:
            with st.container(key=f"qdisp_note_{m['id']}"):
                if m["wrong_answer"]:
                    st.markdown(f"**学生错答：** {md(m['wrong_answer'])}")
                if m["error_reason"]:
                    st.markdown(f"**错因：** {md(m['error_reason'])}")

        # ---------- 编辑（含图片上传） ----------
        if st.session_state.get(SS + "editing_mistake") == m["id"]:
            _render_edit_mistake_form(m, student_id)


def _render_edit_mistake_form(m: dict, student_id: int):
    with st.container(border=True):
        st.markdown("**编辑错题信息**")
        c1, c2 = st.columns(2)
        with c1:
            wrong = st.text_area("错答", value=m["wrong_answer"],
                                 key=f"{SS}em_w_{m['id']}", height=80)
            reason = st.text_area("错因", value=m["error_reason"],
                                  key=f"{SS}em_r_{m['id']}", height=80)
        with c2:
            mastery = st.selectbox(
                "掌握程度",
                [0, 1, 2, 3],
                index=m["mastery"],
                format_func=lambda x: MASTERY_LABELS[x],
                key=f"{SS}em_m_{m['id']}",
            )
        b1, b2, _ = st.columns([1, 1, 4])
        with b1:
            if st.button("💾 保存", type="primary", width="stretch",
                         key=f"{SS}em_save_{m['id']}"):
                ssvc.update_mistake(m["id"], wrong_answer=wrong,
                                    error_reason=reason, mastery=mastery)
                st.session_state[SS + "editing_mistake"] = None
                _flash("已更新")
                st.rerun()
        with b2:
            if st.button("取消", width="stretch", key=f"{SS}em_cancel_{m['id']}"):
                st.session_state[SS + "editing_mistake"] = None
                st.rerun()

        # ---------- 题目图片上传（从卡片移到编辑里） ----------
        st.divider()
        st.markdown("**📎 上传错题图片**")
        st.caption("图片会显示在上面的错题卡片里；png / jpg / webp / gif，单张 ≤5MB。")
        up_seq = st.session_state.get(SS + "upload_seq", 0)
        st.file_uploader(
            "选择图片（可多选）",
            type=["png", "jpg", "jpeg", "webp", "gif"],
            key=f"{SS}up_m_{m['id']}_{up_seq}",
            accept_multiple_files=True,
        )
        st.text_input("图片说明", key=f"{SS}cap_m_{m['id']}")
        st.button(
            "上传",
            key=f"{SS}up_btn_m_{m['id']}",
            on_click=_cb_upload_mistake_files,
            args=(m["id"], student_id),
        )


def _cb_upload_mistake_files(mistake_id: int, student_id: int):
    """上传错题图片的按钮回调。

    file_uploader 是特殊 widget，不能用 session_state 直接清空，
    因此用 upload_seq 让 key 变化，下一轮就拿到全新上传器。
    """
    seq = st.session_state.get(SS + "upload_seq", 0)
    files = st.session_state.get(f"{SS}up_m_{mistake_id}_{seq}") or []
    if not files:
        st.session_state["_flash"] = ("warning", "请先选择文件。")
        return
    caption = st.session_state.get(f"{SS}cap_m_{mistake_id}", "")
    count, errors = 0, 0
    for f in files:
        try:
            ssvc.add_student_file(student_id, f, caption=caption, mistake_id=mistake_id)
            count += 1
        except Exception:
            errors += 1
    if count:
        msg = f"已上传 {count} 张图片"
        if errors:
            msg += f"，{errors} 张失败"
        st.session_state["_flash"] = ("success", msg)
    elif errors:
        st.session_state["_flash"] = ("error", "上传失败，请检查图片格式与大小（≤5MB）")
    # 关键：递增 seq，让 key 变化 → 上传器自动重置
    st.session_state[SS + "upload_seq"] = seq + 1

# ------------------------------------------------------------
# 学生级图片区
# ------------------------------------------------------------
def _render_student_files_block(stu):
    st.subheader("🖼️ 学习图片（不挂错题）")
    st.caption("适合放试卷扫描件、笔记照片等。要挂到具体错题上，请在上方对应错题的「📎 上传图片」中操作。")

    up_seq = st.session_state.get(SS + "upload_seq", 0)
    with st.expander("📎 上传新图片", expanded=False):
        st.file_uploader(
            "选择图片（可多选）",
            type=["png", "jpg", "jpeg", "webp", "gif"],
            key=f"{SS}up_stu_{stu.id}_{up_seq}",
            accept_multiple_files=True,
        )
        st.text_input("图片说明", key=f"{SS}cap_stu_{stu.id}")
        st.button(
            "上传",
            key=f"{SS}up_btn_stu_{stu.id}",
            on_click=_cb_upload_student_files,
            args=(stu.id,),
        )

    files = [f for f in ssvc.list_student_files(stu.id) if f["mistake_id"] is None]
    if not files:
        st.caption("_暂无学生级图片_")
        return
    _render_thumbnails(files, key_prefix=f"stu_{stu.id}")


def _cb_upload_student_files(student_id: int):
    seq = st.session_state.get(SS + "upload_seq", 0)
    files = st.session_state.get(f"{SS}up_stu_{student_id}_{seq}") or []
    if not files:
        st.session_state["_flash"] = ("warning", "请先选择文件。")
        return
    caption = st.session_state.get(f"{SS}cap_stu_{student_id}", "")
    count, errors = 0, 0
    for f in files:
        try:
            ssvc.add_student_file(student_id, f, caption=caption, mistake_id=None)
            count += 1
        except Exception:
            errors += 1
    if count:
        msg = f"已上传 {count} 张图片"
        if errors:
            msg += f"，{errors} 张失败"
        st.session_state["_flash"] = ("success", msg)
    elif errors:
        st.session_state["_flash"] = ("error", "上传失败，请检查图片格式与大小（≤5MB）")
    st.session_state[SS + "upload_seq"] = seq + 1

# ============================================================
# 入口
# ============================================================
def render():
    _init_state()
    _show_flash()

    view = st.session_state.get(SS + "view")
    if view is None:
        _render_list()
    elif view == "new":
        _render_new_student()
    else:
        _render_detail(int(view))