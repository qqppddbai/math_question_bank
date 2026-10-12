# -*- coding: utf-8 -*-
"""题目管理页面：列表 + 新增/编辑表单 + 详情展开 + 软删除。

「不丢位置」是这个页面的一条硬约定：
- 分页页码 `q_page` 一直留在 session_state 里，编辑完回到的还是原来那一页；
- 进编辑页前记住是哪一道题（`q_focus_id`），回到列表后由 `_apply_focus_scroll`
  把页面滚回这道题所在的位置，并给它套一圈绿边——注意**不是**把它搬到列表顶部，
  列表顺序和进去之前完全一样；
- 唯一的例外是「新增」：新题编号最大、必然在最后一页，`_page_of_question`
  会先把页码翻过去，否则保存完停在第 1 页根本看不到它。
"""
from __future__ import annotations

import re

import streamlit as st
import streamlit.components.v1 as components

from src.config import (CHOICE_TYPES, DIFFICULTY_LABELS, GRADES, OPTION_KEYS,
                        QTYPES)
from src.services import data_cache as dc
from src.services import question_service as qs
from src.ui import question_card as qc
from src.utils import file_utils
from src.utils import latex_check
from src.utils.latex import md
from src.utils.rich_text import marker_syntax, placement_report

PAGE_SIZE = 20
THUMB_WIDTH = qc.THUMB_WIDTH   # 缩略图宽度（像素）
EDIT_PREFIX = "q_edit_"   # 编辑表单所有 widget key 的前缀，便于整体清空

# 插入标记时"待插入的目标"暂存在这个 session_state key 里，
# 由按钮回调读取（回调早于 widget 渲染，所以必须先存好）。
PENDING_MARKER = "_pending_marker"

# ============================================================
# session_state 初始化与工具
# ============================================================
def _init_state():
    st.session_state.setdefault("q_editing", None)   # None / 'new' / int
    st.session_state.setdefault("q_page", 1)
    st.session_state.setdefault("q_confirm_delete", None)
    # 刚保存过的题目 id：回到列表时把它单独提到最上面，
    # 免得老师保存完还得上下翻半天找自己刚改的那道题。
    st.session_state.setdefault("q_focus_id", None)


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


def _leave_editor(keep_focus_qid=None):
    """离开编辑页回列表。

    如果刚才是从列表里某一道题点进来的，就把它的 id 记下来，
    回到列表后由 _apply_focus_scroll 滚回它那儿——取消编辑也一样，
    不然点错进编辑页再退出来，同样会丢掉位置。
    """
    if keep_focus_qid is not None:
        st.session_state["q_focus_id"] = int(keep_focus_qid)
    _close_editor()
    st.rerun()


def _flash(msg: str, kind: str = "success"):
    """暂存一条提示，下次 rerun 时展示。"""
    st.session_state["_flash"] = (kind, msg)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


# ------------------------------------------------------------
# 公式体检：编辑器里就直接提醒，别等保存完才发现是一片红字
# ------------------------------------------------------------
def _cb_fix_latex_field(state_key: str):
    """把某个编辑框里 KaTeX 不支持的公式写法改成等价写法。"""
    fixed, n = latex_check.fix_text(st.session_state.get(state_key, ""))
    if n:
        st.session_state[state_key] = fixed
        _flash(f"已自动修复 {n} 处公式写法，确认无误后记得保存。")


def _latex_hint(text: str, key: str, state_key: str) -> None:
    """在实时预览下面给一行公式提示（有问题才显示）。"""
    issues = latex_check.check_text(text or "")
    if not issues:
        return
    first = issues[0]
    st.caption(("🔴 " if first.is_error else "🟡 ") + first.message)
    if len(issues) > 1:
        st.caption(f"（另有 {len(issues) - 1} 处类似问题）")
    if any(i.fixable for i in issues):
        st.button("🔧 自动修复公式", key=key,
                  on_click=_cb_fix_latex_field, args=(state_key,),
                  help="只改写 KaTeX 不支持的写法（如 \\begin{array}{*{35}{l}}），"
                       "其余内容原样保留。")


# ============================================================
# 列表页
# ============================================================
#: 刚保存的题目外面套的那层容器 key 前缀，同时也被下面的脚本当作定位目标。
FOCUS_ANCHOR = "q_focus_"

# 让页面滚回刚编辑的那道题。
#
# Streamlit 没有官方的"滚动到某个元素"接口，切页面 / 重跑之后浏览器会把滚动条
# 拉回顶部，所以只能借 components.html 里的脚本，让同源 iframe 去操作父页面。
# 之所以可行：Streamlit 给组件 iframe 的 sandbox 里带了 allow-same-origin
# （见 streamlit/static/.../IFrameUtil.*.js），window.parent.document 是能读到的。
#
# 脚本里用 __ANCHOR__ 占位，避免和 JS 自身的大括号打架。
_SCROLL_JS = """<script>
(function () {
  var doc = window.parent.document;
  var box = doc.querySelector('[class*="st-key-__ANCHOR__"]');
  if (!box) { return; }
  function go() { box.scrollIntoView({block: 'center', behavior: 'auto'}); }
  go();
  // 布局稳定后 Streamlit 偶尔还会再改一次滚动位置，隔一小会儿再对齐一次
  setTimeout(go, 250);
})();
</script>"""


def _page_of_question(qid, current_page, kw, qtype, grade, chapter):
    """算出某道题在「当前筛选条件下的第几页」。

    新增的题目编号最大，一定落在最后一页；不翻过去的话，保存完还是停在第 1 页，
    根本看不到刚建的那道题。找不到（比如改完不再符合筛选条件）就返回原页码。
    """
    ids = [q.id for q in dc.list_questions(
        keyword=kw, qtype=qtype, grade=grade, chapter=chapter)]
    try:
        return ids.index(qid) // PAGE_SIZE + 1
    except ValueError:
        return current_page


def _apply_focus_scroll(rows, focus_id):
    """把列表滚回刚编辑的那道题所在的位置（列表顺序 / 页码都不动）。

    只做一次：调完就把 q_focus_id 清掉，之后正常浏览不会再被拽回去。
    """
    if not focus_id:
        return
    st.session_state["q_focus_id"] = None

    if not any(q.id == focus_id for q in rows):
        # 改完题干 / 年级后可能不再符合当前筛选条件，那它也就在这一页之外了
        st.caption(f"（刚保存的题目 #{focus_id} 不在当前筛选条件下，"
                   f"可以在「🔍 搜索筛选」里找到它）")
        return

    components.html(_SCROLL_JS.replace("__ANCHOR__", FOCUS_ANCHOR + str(focus_id)),
                    height=0)


def _render_list():
    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.subheader("📚 题目管理")
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

    total = dc.count_questions(keyword=kw, qtype=f_qtype, grade=f_grade, chapter=f_chapter)
    if total == 0:
        st.info("没有符合条件的题目。可以调整筛选条件，或点右上角「➕ 新增题目」。")
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(1, st.session_state.get("q_page", 1)), total_pages)

    # 刚保存的题目可能不在当前这一页：新增的题永远排在最末，一定落在最后一页。
    # 这里先把它所在的那一页算出来并翻过去，后面才能滚到它那儿。
    focus_id = st.session_state.get("q_focus_id")
    if focus_id:
        page = _page_of_question(focus_id, page, kw, f_qtype, f_grade, f_chapter)
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

    rows = dc.list_questions(
        keyword=kw, qtype=f_qtype, grade=f_grade, chapter=f_chapter,
        limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE,
    )

    for q in rows:
        if focus_id and q.id == focus_id:
            # 刚保存的这一道：位置不动，只是多套一层容器当锚点，
            # 好在下面的脚本里定位它，并靠 CSS 给它描一圈绿边
            with st.container(key=FOCUS_ANCHOR + str(q.id)):
                _render_question_card(q)
        else:
            _render_question_card(q)

    _apply_focus_scroll(rows, focus_id)


def _render_question_card(q):
    """题目卡片。

    题目展示部分（元信息 / 题干 / 选项 / 配图 / 答案与解析）统一走
    src/ui/question_card.py，与「搜索筛选」「手动组卷」共用同一套渲染，
    保证三处版面完全一致（宋体六号）。

    结构：
        [内容区（约 6/7 宽）]                   [操作区]
            [带边框容器 · 题目内容]             [✏️ 编辑]
            [折叠面板：📖 查看答案与解析]       [🗑️ 删除]
    操作按钮竖排在卡片右侧，不占题目正文的宽度，也不再压在卡片下方。

    其它页面各有一套操作按钮（搜索页是「☐ 选择」、组卷页是「➕ 加入试卷」、
    学生页是「✏️ 编辑 / 🗑️ 删除」），都已经是"右侧竖排"的样式，无需改动。
    """
    content_col, action_col = st.columns([14, 1], vertical_alignment="top")

    # ---------- 左：卡片主体 + 答案与解析 ----------
    with content_col:
        with st.container(border=True):
            qc.render_body(q, key="card", thumb_prefix=f"card_{q.id}")
        qc.render_answer_expander(q, key="card")

    # ---------- 右：编辑 / 删除 ----------
    with action_col:
        confirming = st.session_state.get("q_confirm_delete") == q.id

        if st.button("✏️", key=f"edit_{q.id}", width="stretch"):
            _open_edit(q.id)
            st.rerun()

        if confirming:
            # 删除是不可逆的软删除，保留"点两次"的确认流程，避免手滑
            if st.button("⚠️ 确认", key=f"confirm_del_{q.id}", type="primary",
                         width="stretch"):
                qs.soft_delete_question(q.id)
                st.session_state["q_confirm_delete"] = None
                _flash(f"题目 #{q.id} 已移入回收站")
                st.rerun()
            if st.button("取消", key=f"cancel_del_{q.id}", width="stretch"):
                st.session_state["q_confirm_delete"] = None
                st.rerun()
        else:
            if st.button("🗑️", key=f"del_{q.id}", width="stretch"):
                st.session_state["q_confirm_delete"] = q.id
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

    # 已有图片：按「题干配图 / 解析配图」分成两组，每组一个"标记删除"复选框
    stem_imgs, analysis_imgs = file_utils.split_images(q.image_list if q else [])
    for group in ("stem", "analysis"):
        rels = stem_imgs if group == "stem" else analysis_imgs
        setdef(EDIT_PREFIX + f"{group}_images", list(rels))
        for i, _ in enumerate(st.session_state[EDIT_PREFIX + f"{group}_images"]):
            setdef(EDIT_PREFIX + f"{group}_del_{i}", False)


def _render_image_group(label: str, group: str, caption: str = "") -> None:
    """渲染一组图片：缩略图 + 可复制的定位标记 + 上传框 + 安置提示。

    group 取值 "stem" / "analysis"，同时决定 session_state 的 key 前缀
    （q_edit_stem_images / q_edit_analysis_images 等）、上传框的 key，
    以及它对应的正文字段（题干 / 解析），两组互不干扰。

    每个缩略图下面给一个 st.code 标记（自带复制按钮），粘到正文里就能把
    这张图放到那个位置。
    """
    existing = st.session_state.get(EDIT_PREFIX + f"{group}_images", [])

    st.markdown(f"**{label}**")
    if caption:
        st.caption(caption)

    if existing:
        icols = st.columns(min(6, len(existing)))
        # 只有一张图时标记可以省掉序号（![[img]] 就是第 1 张），更省事
        single = len(existing) == 1
        for i, rel in enumerate(existing):
            with icols[i % len(icols)]:
                p = file_utils.abs_path(file_utils.real_image_path(rel))
                if p.is_file():
                    st.image(str(p), width=THUMB_WIDTH)
                else:
                    st.caption("图片已丢失")
                # 缩略图下方给出可直接复制的标记（st.code 自带复制按钮）。
                # 把它粘到文字里想放图片的位置即可。
                st.code(marker_syntax(i + 1, compact=single), language=None)
                st.checkbox("删", key=EDIT_PREFIX + f"{group}_del_{i}")
    else:
        st.caption("_（暂无）_")

    st.file_uploader(
        f"上传{label}（png / jpg / webp / gif，≤5MB，可多选）",
        type=["png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=True,
        key=EDIT_PREFIX + f"{group}_uploader",
    )

    # 告诉老师哪几张图还没放进文字里
    field = GROUP_FIELD[group]
    text = st.session_state.get(EDIT_PREFIX + field, "")
    report = placement_report(text, existing)
    if existing:
        if report["unplaced"]:
            nums = "、".join(f"第 {n} 张" for n in report["unplaced"])
            st.caption(f"⚠️ 还没安置：{nums}（不写标记时会排在文字最后）")
        elif report["placed"]:
            st.caption("✅ 所有图片都已用标记安置好")
    if report["bad"]:
        nums = "、".join(str(n) for n in report["bad"])
        st.caption(f"❗ 文字里引用了不存在的序号：{nums}")

    if existing:
        _render_insert_tools(field, group, label, existing)


# 图片分组 ←→ 正文字段 的对应关系（标记里的序号按各自分组从 1 数）
GROUP_FIELD = {"stem": "stem", "analysis": "analysis"}


def _paragraphs(text: str):
    """按空行切段（只用于"插到第几段之后"的选项，不影响正文渲染）。"""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "")]
    return [p for p in parts if p]


def _insert_marker(paragraph_index: int, number: int, width):
    """按钮回调：把标记写到段落后面。段落下标 -1 表示插到最前面。"""
    key = st.session_state.pop(PENDING_MARKER, None)
    if key is None:
        return
    field, group = key
    text_key = EDIT_PREFIX + field
    marker = marker_syntax(number, width)

    text = st.session_state.get(text_key, "") or ""
    paragraphs = _paragraphs(text)
    if paragraph_index < 0:
        st.session_state[text_key] = marker + "\n\n" + text
    elif paragraph_index >= len(paragraphs):
        st.session_state[text_key] = text.rstrip() + "\n\n" + marker
    else:
        target = paragraphs[paragraph_index]
        pos = text.find(target)
        cut = pos + len(target) if pos >= 0 else len(text)
        st.session_state[text_key] = text[:cut] + "\n\n" + marker + "\n\n" + text[cut:]


def _render_insert_tools(field: str, group: str, label: str, existing) -> None:
    """把某张图自动插到某一段之后（不想手抄标记时用）。"""
    if not existing:
        return
    text = st.session_state.get(EDIT_PREFIX + field, "") or ""
    paragraphs = _paragraphs(text)

    with st.expander("✍️ 不想手抄标记？用这里插入", expanded=False):
        st.caption(
            "选好「把哪张图」和「放到哪儿」，点插入即可。"
            "插入后记得点右下角「💾 保存」。"
        )
        c1, c2, c3 = st.columns([1.2, 1.6, 1])
        with c1:
            number = st.selectbox(
                "用哪张图", list(range(1, len(existing) + 1)),
                format_func=lambda n: f"第 {n} 张", key=f"{EDIT_PREFIX}ins_n_{group}",
            )
        with c2:
            options = ["正文最前面"] + [
                f"第 {i} 段之后（{p[:14]}…）" if len(p) > 14 else f"第 {i} 段之后（{p}）"
                for i, p in enumerate(paragraphs, start=1)
            ] + ["正文最后面"]
            where = st.selectbox("放到哪儿", options, key=f"{EDIT_PREFIX}ins_w_{group}")
            paragraph_index = options.index(where) - 1
            if paragraph_index >= len(paragraphs):
                paragraph_index = len(paragraphs)
        with c3:
            st.write("")
            st.button(
                "插入标记", key=f"{EDIT_PREFIX}ins_go_{group}",
                width="stretch",
                on_click=_insert_marker,
                args=(paragraph_index, number, None),
            )
            st.session_state[PENDING_MARKER] = (field, group)


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
            _leave_editor(None if is_new else q.id)

    st.caption("公式用 LaTeX 书写，例如 $x^2+y^2=r^2$；行内用单个 $ 包裹，独立公式用 $$。")
    st.caption(
        "图片想插在文字中间？在下面「图片」区每个缩略图下方都有可复制的标记"
        "（只有一张图时是 `![[img]]`，多张图是 `![[img:1]]`、`![[img:2]]`），"
        "把它粘到想放图片的位置即可；想指定宽度写成 `![[img:1|300]]`。"
        "**不写标记的图片会排在文字最后。**"
    )

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
            if stem_now.strip():
                # 与正式卡片同一套分段渲染：图片按 ![[img:N]] 插到文字之间
                qc.render_text_blocks(
                    stem_now,
                    st.session_state.get(EDIT_PREFIX + "stem_images", []),
                )
            else:
                st.markdown("_（暂无内容）_")
        _latex_hint(st.session_state.get(EDIT_PREFIX + "stem", ""),
                    key="q_edit_latex_stem", state_key=EDIT_PREFIX + "stem")

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
        st.caption("解析里要插图？在下方「图片 → 解析配图」上传，会显示在题目详情的答案与解析面板中。")
    with ac2:
        st.caption("实时预览")
        with st.container(border=True, height=200, key="qdisp_preview_analysis"):
            ana_now = st.session_state.get(EDIT_PREFIX + "analysis", "")
            if ana_now.strip():
                # 与正式卡片同一套分段渲染：图片按 ![[img:N]] 插到文字之间
                qc.render_text_blocks(
                    ana_now,
                    st.session_state.get(EDIT_PREFIX + "analysis_images", []),
                )
            else:
                st.markdown("_（暂无内容）_")
        _latex_hint(st.session_state.get(EDIT_PREFIX + "analysis", ""),
                    key="q_edit_latex_analysis", state_key=EDIT_PREFIX + "analysis")

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
    # 题干配图和解析配图分开管理：上传在哪一组，就显示在题目的对应位置。
    st.divider()
    st.markdown("### 图片")
    st.caption("图片分两组：**题干配图**显示在题干下方，**解析配图**显示在「答案与解析」里。")

    _render_image_group(
        "题干配图", "stem",
        caption="显示在题干下方（例如几何图形、函数图象）。",
    )
    st.write("")
    _render_image_group(
        "解析配图", "analysis",
        caption="显示在折叠的「📖 查看答案与解析」面板里（例如辅助线、解题步骤图）。",
    )
    st.write("")
    st.caption("❗ 点保存时，**两组上传框里的图片会一起入库**；上传完记得点右下角「💾 保存」。")

    # -------- 保存 / 取消 --------
    st.divider()
    bcol1, bcol2, _ = st.columns([1, 1, 4])
    with bcol1:
        if st.button("💾 保存", type="primary", width="stretch"):
            _save_current(q, is_new)
    with bcol2:
        if st.button("取消", width="stretch"):
            _leave_editor(None if is_new else q.id)


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

    # 图片：分成「题干 / 解析」两组，各自过滤掉被标记删除的
    keep_stem, keep_analysis, to_delete = [], [], []
    for group in ("stem", "analysis"):
        existing = st.session_state.get(p + f"{group}_images", [])
        keep, drop = [], []
        for i, rel in enumerate(existing):
            if st.session_state.get(p + f"{group}_del_{i}", False):
                drop.append(rel)
            else:
                keep.append(rel)
        if group == "stem":
            keep_stem = keep
        else:
            keep_analysis = keep
        to_delete += drop

    data["_keep_stem_images"] = keep_stem
    data["_keep_analysis_images"] = keep_analysis
    # 真正删除磁盘文件放到 save 成功后
    data["_to_delete_files"] = to_delete
    return data


def _save_current(q, is_new: bool):
    data = _collect_data_from_state()

    if not data["stem"].strip():
        st.error("题干不能为空，请先填写题干。")
        return

    # 处理新上传的图片：题干配图 / 解析配图 两个上传框分别处理
    new_stem, new_analysis = [], []
    for group, bucket in (("stem", new_stem), ("analysis", new_analysis)):
        uploaded = st.session_state.get(EDIT_PREFIX + f"{group}_uploader") or []
        try:
            for f in uploaded:
                bucket.append(file_utils.save_uploaded_image(f))
        except ValueError as e:
            st.error(str(e))
            return
        except Exception as e:
            st.error(f"图片保存失败：{e}")
            return

    final_images = file_utils.join_images(
        list(data["_keep_stem_images"]) + new_stem,
        list(data["_keep_analysis_images"]) + new_analysis,
    )
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
            saved_id = new_id
            msg = f"新增成功，题目编号 #{new_id}"
        else:
            ok = qs.update_question(q.id, payload)
            if not ok:
                st.error("保存失败：题目不存在或已被删除。")
                return
            saved_id = q.id
            msg = f"题目 #{q.id} 已更新"
    except Exception as e:
        st.error(f"保存失败：{e}")
        return

    # 保存成功后再真正删除被标记的磁盘图片
    for rel in data["_to_delete_files"]:
        file_utils.delete_file_silently(rel)

    # 记住刚保存的是哪一道：回到列表页会把它单独提到最上面，
    # 不用再上下翻找（新增的题目排在最后一页，更需要这个）。
    st.session_state["q_focus_id"] = saved_id
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