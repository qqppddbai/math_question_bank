# -*- coding: utf-8 -*-
"""批量导入页面：粘贴 JSON / 上传文件 → 校验预览 → 一键入库。

关键约定：
- text_area 的唯一数据源是 st.session_state["import_textarea"]；
- 所有对它的写入都在 on_click / on_change 回调里做（回调早于 widget 渲染）；
- 主流程只读取，不再赋值，避免 Streamlit 抛 "widget already instantiated"。
"""
from __future__ import annotations

import streamlit as st

from src.config import DIFFICULTY_LABELS
from src.services import import_service as imp
from src.utils.latex import strip_latex_for_preview

SS = "import_"
TEXT_KEY = SS + "textarea"     # text_area 的 key，也是唯一数据源

SAMPLE_JSON = '''[
  {
    "grade": "高三",
    "chapter": "导数",
    "knowledge": "不等式证明,极值点,分类讨论",
    "qtype": "解答题",
    "difficulty": 5,
    "stem": "(1) 证明：当 $0<x<1$ 时，$x-x^2<\\\\sin x<x$；\\n(2) 已知函数 $f(x)=\\\\cos ax-\\\\ln(1-x^2)$，若 $x=0$ 是 $f(x)$ 的极大值点，求 $a$ 的取值范围。",
    "options": "",
    "answer": "(1) 证明见解析；\\n(2) $(-\\\\infty,-\\\\sqrt{2})\\\\cup(\\\\sqrt{2},+\\\\infty)$",
    "analysis": "构造 $F(x)=x-\\\\sin x$ 求导证明。",
    "source": "2023年新课标全国Ⅱ卷",
    "tags": "高考真题,新高考II卷"
  }
]'''


# ============================================================
# 状态初始化
# ============================================================
def _init_state():
    st.session_state.setdefault(TEXT_KEY, "")
    st.session_state.setdefault(SS + "report", None)
    st.session_state.setdefault(SS + "skip_dup", True)


# ============================================================
# 回调（必须放在 widget 渲染之前执行）
# ============================================================
def _cb_fill_sample():
    st.session_state[TEXT_KEY] = SAMPLE_JSON


def _cb_clear():
    st.session_state[TEXT_KEY] = ""
    st.session_state[SS + "report"] = None


def _cb_on_upload():
    """文件上传变化时，把内容读进 text_area。"""
    up = st.session_state.get(SS + "uploader")
    if up is None:
        return
    try:
        content = up.read().decode("utf-8")
        st.session_state[TEXT_KEY] = content
        st.session_state[SS + "upload_msg"] = ("success", f"已读取：{up.name}")
    except UnicodeDecodeError:
        st.session_state[SS + "upload_msg"] = ("error", "文件不是 UTF-8 编码，请另存为 UTF-8 后重试。")
    except Exception as e:
        st.session_state[SS + "upload_msg"] = ("error", f"读取失败：{e}")


def _cb_parse():
    """解析按钮回调：结果存进 session_state，主流程只负责展示。"""
    text = st.session_state.get(TEXT_KEY, "")
    st.session_state[SS + "report"] = imp.parse_json_text(text)


# ============================================================
# 输入区
# ============================================================
def _render_input():
    st.subheader("① 粘贴或上传 JSON")
    st.caption(
        "支持标准 JSON 数组。字段缺失会自动用默认值；"
        "只有 **题干为空、题型非法、难度非法** 才拒绝入库。"
    )

    tab_paste, tab_file, tab_sample = st.tabs(
        ["📋 粘贴文本", "📁 上传文件", "📖 格式说明 / 示例"]
    )

    with tab_paste:
        st.text_area(
            "JSON 文本",
            height=320,
            key=TEXT_KEY,                     # 唯一数据源，不再传 value
            label_visibility="collapsed",
            placeholder='[\n  { "grade": "高三", "qtype": "解答题", "difficulty": 5, "stem": "..." }\n]',
        )

    with tab_file:
        st.file_uploader(
            "选择 .json 文件（UTF-8 编码）",
            type=["json", "txt"],
            key=SS + "uploader",
            on_change=_cb_on_upload,
        )
        msg = st.session_state.pop(SS + "upload_msg", None)
        if msg:
            kind, text = msg
            getattr(st, kind, st.info)(text)

    with tab_sample:
        st.markdown(
            """
**字段说明**

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `stem` | ✅ | 题干，含 LaTeX |
| `qtype` | 建议填 | 单选题 / 多选题 / 填空题 / 解答题 / 判断题 / 作图题，默认"解答题" |
| `difficulty` | 建议填 | 1~5 整数，默认 3 |
| `options` | 选择题必填 | 多行文本：`"A. xxx\\nB. yyy\\nC. zzz\\nD. www"` |
| `grade` | 建议填 | 初一~高三 |
| `chapter` | 建议填 | 如"导数" |
| `knowledge` / `tags` | 选填 | 逗号分隔 |
| `answer` / `analysis` | 选填 | 答案与解析 |
| `source` | 选填 | 来源 |

**易错点**

- LaTeX 里的反斜杠要转义：`\\sin` → `\\\\sin`。
- 换行用 `\\n`，不要按回车。
- 最外层必须是 `[ ]`。
            """
        )
        st.code(SAMPLE_JSON, language="json")
        st.button("📥 把示例填入文本框", key=SS + "btn_sample", on_click=_cb_fill_sample)

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        st.button(
            "🔍 解析并预览",
            type="primary",
            use_container_width=True,
            key=SS + "btn_parse",
            on_click=_cb_parse,              # 关键：用回调，不在主流程里改状态
        )
    with c2:
        st.button(
            "🧹 清空内容",
            use_container_width=True,
            key=SS + "btn_clear",
            on_click=_cb_clear,
        )


# ============================================================
# 预览区
# ============================================================
def _render_preview():
    report: imp.ParseResult = st.session_state.get(SS + "report")
    if report is None:
        return

    st.divider()
    st.subheader("② 校验结果")

    if report.fatal_error:
        st.error(report.fatal_error)
        if st.button("重新输入", key=SS + "btn_back"):
            st.session_state[SS + "report"] = None
            st.rerun()
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总条数", report.total)
    c2.metric("可入库", report.ok_count)
    c3.metric("有问题", report.error_count)
    c4.metric("与库内重复", report.dup_count)

    if report.ok_count == 0:
        st.error("没有任何一条可通过校验，请根据下方提示修改后重新解析。")

    table_rows = []
    for r in report.rows:
        if not r.ok:
            status = "❌ 错误"
        elif r.is_duplicate:
            status = "⚠️ 重复"
        elif r.warnings:
            status = "⚠️ 提醒"
        else:
            status = "✅ 正常"

        d = r.data or {}
        note_parts = r.errors + r.warnings
        if r.is_duplicate:
            note_parts = [f"与 #{',#'.join(map(str, r.duplicate_ids[:5]))} 重复"] + note_parts

        table_rows.append({
            "#": r.index + 1,
            "状态": status,
            "题型": d.get("qtype", ""),
            "难度": DIFFICULTY_LABELS.get(d.get("difficulty", 3), ""),
            "年级": d.get("grade", ""),
            "章节": d.get("chapter", ""),
            "题干预览": strip_latex_for_preview(d.get("stem", ""), 60),
            "备注": "；".join(note_parts) if note_parts else "—",
        })

    st.dataframe(
        table_rows,
        use_container_width=True,
        hide_index=True,
        height=min(600, 60 + 36 * len(table_rows)),
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "状态": st.column_config.TextColumn(width="small"),
            "题干预览": st.column_config.TextColumn(width="large"),
            "备注": st.column_config.TextColumn(width="large"),
        },
    )

    bad = [r for r in report.rows if not r.ok]
    if bad:
        with st.expander(f"❌ 查看 {len(bad)} 条错误详情", expanded=False):
            for r in bad:
                st.markdown(f"**第 {r.index + 1} 条**")
                for e in r.errors:
                    st.markdown(f"- {e}")
                if r.data.get("stem"):
                    st.caption("题干：" + strip_latex_for_preview(r.data["stem"], 120))
                st.divider()

    warn = [r for r in report.rows if r.ok and r.warnings]
    if warn:
        with st.expander(f"⚠️ 查看 {len(warn)} 条提醒", expanded=False):
            for r in warn:
                st.markdown(f"**第 {r.index + 1} 条**：" + "；".join(r.warnings))

    if report.ok_count > 0:
        st.divider()
        st.subheader("③ 确认入库")
        st.checkbox(
            "跳过与库内重复的题目（推荐）",
            key=SS + "skip_dup",
            help="按题干内容判定重复。取消勾选会强制导入。",
        )

        dup_n = report.dup_count
        will_insert = report.ok_count - (dup_n if st.session_state.get(SS + "skip_dup", True) else 0)

        b1, b2, _ = st.columns([1, 1, 4])
        with b1:
            if st.button(f"✅ 导入 {will_insert} 道题", type="primary",
                         use_container_width=True, key=SS + "btn_commit"):
                try:
                    stats = imp.commit_import(
                        report.rows,
                        skip_duplicates=st.session_state.get(SS + "skip_dup", True),
                    )
                except Exception as e:
                    st.error(f"入库失败：{e}")
                    return
                st.session_state["_flash"] = (
                    "success",
                    f"导入完成：新增 {stats['inserted']} 道，"
                    f"跳过重复 {stats['skipped_dup']} 道，"
                    f"跳过错误 {stats['skipped_err']} 道",
                )
                st.session_state[SS + "report"] = None
                st.session_state[SS + "clear_text_next_run"] = True   # 交给 render() 处理
                st.rerun()
        with b2:
            if st.button("取消", use_container_width=True, key=SS + "btn_cancel"):
                st.session_state[SS + "report"] = None
                st.rerun()


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()

    # 上一轮导入成功后置的标记：在下一次 rerun 的 widget 渲染之前清空文本框
    if st.session_state.pop(SS + "clear_text_next_run", False):
        st.session_state[TEXT_KEY] = ""

    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)

    st.header("📥 批量导入")
    st.caption("把题库备份的 JSON 数组粘贴进来，一次可导入几十上百道题。")

    _render_input()
    _render_preview()