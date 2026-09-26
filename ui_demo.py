# -*- coding: utf-8 -*-
"""
数学题库管理系统 —— 界面组件演示（UI 原型）
=================================================
用途：
    给数学老师直观展示"数学题库管理系统"最终会长什么样，
    同时演示 Streamlit 常用 UI 组件的实际效果。

运行：
    pip install streamlit pandas
    streamlit run ui_demo.py

版本：
    Streamlit >= 1.37（st.dialog 需要），其余组件 >= 1.29。
    低版本会自动降级，不会崩溃。
"""

import time
import json
import random
import pandas as pd
import streamlit as st

# ============================================================
# 全局配置（必须是第一个 st 命令）
# ============================================================
st.set_page_config(
    page_title="数学题库管理系统",
    page_icon="📐",
    layout="wide",                     # 宽屏布局
    initial_sidebar_state="expanded",  # 侧边栏默认展开
)

HAS_DIALOG = hasattr(st, "dialog")     # 判断是否支持模态对话框


# ============================================================
# 示例数据
# ============================================================
SAMPLE_QUESTIONS = [
    {
        "id": 1,
        "grade": "高三",
        "chapter": "导数",
        "knowledge": "不等式证明,极值点,分类讨论",
        "qtype": "解答题",
        "difficulty": 5,
        "stem": (
            "(1) 证明：当 $0<x<1$ 时，$x-x^2<\\sin x<x$；\n"
            "(2) 已知函数 $f(x)=\\cos ax-\\ln(1-x^2)$，若 $x=0$ 是 $f(x)$ 的极大值点，"
            "求 $a$ 的取值范围。"
        ),
        "options": "",
        "answer": "(1) 证明见解析；\n(2) $(-\\infty,-\\sqrt{2})\\cup(\\sqrt{2},+\\infty)$",
        "analysis": (
            "(1) 构造 $F(x)=x-\\sin x$ 和 $G(x)=\\sin x-(x-x^2)$，求导证明。\n"
            "(2) $f(x)$ 为偶函数，讨论 $a^2\\le 2$ 与 $a^2>2$ 两种情况。"
        ),
        "source": "2023年新课标全国Ⅱ卷",
        "tags": "高考真题,新高考II卷",
    },
    {
        "id": 2,
        "grade": "高二",
        "chapter": "圆锥曲线",
        "knowledge": "椭圆,离心率",
        "qtype": "选择题",
        "difficulty": 3,
        "stem": "已知椭圆 $\\dfrac{x^2}{a^2}+\\dfrac{y^2}{b^2}=1$ 的离心率为 $\\dfrac{\\sqrt{3}}{2}$，则 $\\dfrac{b}{a}=$（　　）",
        "options": "A. $\\dfrac{1}{2}$\nB. $\\dfrac{\\sqrt{2}}{2}$\nC. $\\dfrac{\\sqrt{3}}{2}$\nD. $1$",
        "answer": "A",
        "analysis": "由 $e=\\dfrac{c}{a}=\\dfrac{\\sqrt{3}}{2}$ 得 $\\dfrac{b^2}{a^2}=1-e^2=\\dfrac{1}{4}$，故 $\\dfrac{b}{a}=\\dfrac{1}{2}$。",
        "source": "校本练习",
        "tags": "基础题",
    },
    {
        "id": 3,
        "grade": "高一",
        "chapter": "数列",
        "knowledge": "等差数列,通项公式",
        "qtype": "填空题",
        "difficulty": 2,
        "stem": "等差数列 $\\{a_n\\}$ 中，$a_1=2$，$d=3$，则 $a_{10}=$ ______。",
        "options": "",
        "answer": "$29$",
        "analysis": "$a_{10}=a_1+9d=2+27=29$。",
        "source": "课本例题改编",
        "tags": "基础题,同步练习",
    },
]


# ============================================================
# 会话状态初始化（相当于内存里的"数据库"）
# ============================================================
def init_state():
    if "questions" not in st.session_state:
        st.session_state.questions = [dict(q) for q in SAMPLE_QUESTIONS]
    if "trash" not in st.session_state:
        st.session_state.trash = []
    if "paper" not in st.session_state:
        st.session_state.paper = []
    if "import_preview" not in st.session_state:
        st.session_state.import_preview = None


def _next_id():
    """生成新的题目 ID"""
    ids = [q["id"] for q in st.session_state.questions]
    ids += [q["id"] for q in st.session_state.trash]
    return max(ids, default=0) + 1


def _move_to_trash(ids):
    """把指定 ID 的题目移入回收站"""
    keep, move = [], []
    for q in st.session_state.questions:
        (move if q["id"] in ids else keep).append(q)
    st.session_state.questions = keep
    st.session_state.trash.extend(move)


# ============================================================
# 页面 1：术语速查
# ============================================================
def page_terms():
    st.header("📖 术语速查表")
    st.caption("左边是口语说法，中间是专业名词，右边是 Streamlit 代码。写提示词时直接用中间那列。")

    data = [
        {"口语说法": "页面框内嵌", "专业名词": "带边框容器 / 卡片", "Streamlit 代码": "st.container(border=True)", "实际效果": "一组控件被包在圆角边框里"},
        {"口语说法": "下拉", "专业名词": "下拉选择框", "Streamlit 代码": "st.selectbox", "实际效果": "点开选一项"},
        {"口语说法": "多选下拉", "专业名词": "多选选择框", "Streamlit 代码": "st.multiselect", "实际效果": "点开可勾多项，显示为标签"},
        {"口语说法": "展开折叠", "专业名词": "折叠面板", "Streamlit 代码": "st.expander", "实际效果": "默认收起，点标题展开"},
        {"口语说法": "标签页", "专业名词": "选项卡", "Streamlit 代码": "st.tabs", "实际效果": "页面上方一排页签"},
        {"口语说法": "分栏", "专业名词": "列布局", "Streamlit 代码": "st.columns", "实际效果": "控件横向并排"},
        {"口语说法": "侧边导航", "专业名词": "侧边栏", "Streamlit 代码": "st.sidebar", "实际效果": "左侧固定导航区"},
        {"口语说法": "弹窗", "专业名词": "模态对话框", "Streamlit 代码": "st.dialog", "实际效果": "浮在页面中央，需处理才关闭"},
        {"口语说法": "表单", "专业名词": "表单容器", "Streamlit 代码": "st.form + st.form_submit_button", "实际效果": "填完一次性提交"},
        {"口语说法": "输入框", "专业名词": "单行文本输入", "Streamlit 代码": "st.text_input", "实际效果": "一行输入"},
        {"口语说法": "大文本框", "专业名词": "多行文本域", "Streamlit 代码": "st.text_area", "实际效果": "多行输入，可拉伸"},
        {"口语说法": "数字框", "专业名词": "数字输入框", "Streamlit 代码": "st.number_input", "实际效果": "带加减按钮的数字"},
        {"口语说法": "滑条", "专业名词": "滑块", "Streamlit 代码": "st.slider", "实际效果": "拖动选择数值或范围"},
        {"口语说法": "单选按钮", "专业名词": "单选组", "Streamlit 代码": "st.radio", "实际效果": "一排圆点，选一个"},
        {"口语说法": "勾选框", "专业名词": "复选框", "Streamlit 代码": "st.checkbox", "实际效果": "方框打勾"},
        {"口语说法": "开关", "专业名词": "开关", "Streamlit 代码": "st.toggle", "实际效果": "滑动开关"},
        {"口语说法": "上传文件", "专业名词": "文件上传器", "Streamlit 代码": "st.file_uploader", "实际效果": "拖拽或点击上传"},
        {"口语说法": "下载按钮", "专业名词": "下载按钮", "Streamlit 代码": "st.download_button", "实际效果": "点击下载文件"},
        {"口语说法": "表格", "专业名词": "数据表格", "Streamlit 代码": "st.dataframe", "实际效果": "只读表格，可排序"},
        {"口语说法": "可勾选表格", "专业名词": "数据编辑器", "Streamlit 代码": "st.data_editor", "实际效果": "表格里能直接改、能勾选"},
        {"口语说法": "数字卡片", "专业名词": "指标", "Streamlit 代码": "st.metric", "实际效果": "大数字 + 小标题"},
        {"口语说法": "提示条", "专业名词": "消息提示", "Streamlit 代码": "st.success / info / warning / error", "实际效果": "绿/蓝/黄/红 色条"},
        {"口语说法": "小浮层提示", "专业名词": "吐司提示", "Streamlit 代码": "st.toast", "实际效果": "右下角短暂弹出"},
        {"口语说法": "转圈", "专业名词": "加载动画", "Streamlit 代码": "st.spinner", "实际效果": "转圈 + 文字"},
        {"口语说法": "进度条", "专业名词": "进度条", "Streamlit 代码": "st.progress", "实际效果": "横向填充条"},
        {"口语说法": "步骤状态", "专业名词": "状态容器", "Streamlit 代码": "st.status", "实际效果": "带图标的可折叠步骤区"},
        {"口语说法": "分割线", "专业名词": "分隔线", "Streamlit 代码": "st.divider", "实际效果": "一条灰线"},
        {"口语说法": "公式", "专业名词": "LaTeX 渲染", "Streamlit 代码": "st.latex / st.markdown", "实际效果": "行内 $...$，独立 $$...$$"},
        {"口语说法": "没有数据时", "专业名词": "空状态提示", "Streamlit 代码": "st.info", "实际效果": "显示\"暂无数据\""},
        {"口语说法": "危险操作确认", "专业名词": "二次确认", "Streamlit 代码": "st.dialog 或 checkbox + button", "实际效果": "必须再点一次才执行"},
    ]
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("写提示词时的替换建议")
    st.markdown(
        """
| 口语说法 | 提示词里应该写 |
|---|---|
| 页面框内嵌 | 带边框容器 / 卡片 / 嵌套容器 |
| 下拉 | 下拉选择框 |
| 展开折叠 | 折叠面板 / 可展开区域 |
| 弹窗 | 模态对话框 |
| 提示条 | 消息提示 / 告警条 |
| 小浮层 | 吐司提示 |
| 可勾选表格 | 数据编辑器（带选择列） |
| 没有数据时 | 空状态提示 |
| 翻页 | 分页器 |
"""
    )


# ============================================================
# 页面 2：基础组件
# ============================================================
def page_basics():
    st.header("🎨 基础组件实际效果")

    # ---------- 指标卡 ----------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("题目总数", len(st.session_state.questions))
    c2.metric("试卷数", 1)
    c3.metric("回收站", len(st.session_state.trash))
    c4.metric("本周新增", "12", delta="较上周 +3")

    st.divider()

    # ---------- 卡片 / 带边框容器 ----------
    with st.container(border=True):
        st.subheader("① 卡片（带边框容器）")
        st.write("`st.container(border=True)` 把一组内容包进圆角边框，用来做区块分组。")
        st.markdown("行内公式：$x^2 + y^2 = r^2$")
        st.latex(r"\int_0^1 x^2\,\mathrm{d}x = \frac{1}{3}")
        st.caption("上面这行是块级公式，居中显示。")

    # ---------- 折叠面板 ----------
    with st.expander("② 折叠面板：点击展开查看完整题目详情", expanded=False):
        q = st.session_state.questions[0]
        st.markdown(f"**题干**\n\n{q['stem']}")
        st.markdown(f"**答案**\n\n{q['answer']}")
        st.markdown(f"**解析**\n\n{q['analysis']}")

    # ---------- 消息提示 ----------
    st.subheader("③ 四种消息提示条")
    st.success("成功：已保存 3 道题目。")
    st.info("说明：导入前建议先备份数据库文件。")
    st.warning("注意：删除的题目可在回收站恢复。")
    st.error("错误：第 2 条数据缺少字段 qtype。")

    st.divider()

    # ---------- 吐司 + 加载 + 进度 ----------
    st.subheader("④ 吐司提示 / 加载动画 / 进度条")
    c1, c2 = st.columns(2)
    if c1.button("点我触发吐司提示", use_container_width=True):
        st.toast("已复制到剪贴板 ✅", icon="✅")
    if c2.button("点我模拟导入（约 3 秒）", use_container_width=True):
        with st.spinner("正在导入题目..."):
            prog = st.progress(0)
            for i in range(100):
                time.sleep(0.02)
                prog.progress(i + 1)
        st.success("导入完成！")

    # ---------- 状态容器 ----------
    st.subheader("⑤ 状态容器（分步骤显示）")
    if st.button("运行状态容器演示"):
        with st.status("正在处理...", expanded=True) as s:
            st.write("步骤 1/3：读取文件")
            time.sleep(0.4)
            st.write("步骤 2/3：解析 JSON")
            time.sleep(0.4)
            st.write("步骤 3/3：写入数据库")
            time.sleep(0.4)
            s.update(label="处理完成！", state="complete", expanded=False)

    st.divider()

    # ---------- 选项卡 ----------
    st.subheader("⑥ 选项卡")
    t1, t2, t3 = st.tabs(["新增题目", "题目列表", "统计"])
    t1.write("这里是「新增题目」选项卡的内容。")
    t2.write("这里是「题目列表」选项卡的内容。")
    t3.write("这里是「统计」选项卡的内容。")

    st.divider()

    # ---------- 各类输入控件 ----------
    st.subheader("⑦ 常用输入控件")
    c1, c2 = st.columns(2)
    with c1:
        st.toggle("显示答案解析", value=True)
        st.checkbox("我确认要删除")
        st.radio("导出格式", ["Word", "Markdown", "HTML"], horizontal=True)
        st.selectbox("年级", ["高一", "高二", "高三"])
    with c2:
        st.slider("难度范围", 1, 5, (2, 4))
        st.number_input("题目数量", min_value=1, max_value=50, value=10)
        st.multiselect("知识点", ["导数", "圆锥曲线", "数列", "概率"], default=["导数"])
        st.text_input("来源", placeholder="如：2023年新课标全国Ⅱ卷")


# ============================================================
# 页面 3：搜索与筛选
# ============================================================
def page_search():
    st.header("🔍 搜索与筛选")
    st.caption("演示：列布局 + 多条件筛选 + 结果计数 + 分页")

    with st.container(border=True):
        r1 = st.columns([2, 1, 1, 1])
        keyword = r1[0].text_input("关键词", placeholder="输入题干或答案中的关键词", key="f_kw")
        grade = r1[1].selectbox("年级", ["全部", "高一", "高二", "高三"], key="f_grade")
        qtype = r1[2].selectbox("题型", ["全部", "选择题", "填空题", "解答题"], key="f_qtype")
        source = r1[3].text_input("来源", key="f_source")

        r2 = st.columns([2, 2, 1])
        chapters = r2[0].multiselect("章节", ["导数", "圆锥曲线", "数列"], key="f_chapter")
        knowledge = r2[1].multiselect("知识点", ["不等式证明", "极值点", "椭圆", "等差数列"], key="f_know")
        diff = r2[2].slider("难度", 1, 5, (1, 5), key="f_diff")

        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("重置筛选", use_container_width=True):
            for k in ["f_kw", "f_grade", "f_qtype", "f_source", "f_chapter", "f_know", "f_diff", "f_page"]:
                st.session_state.pop(k, None)
            st.rerun()
        c2.caption("筛选即时生效")

    # ---------- 执行筛选 ----------
    result = []
    for q in st.session_state.questions:
        if keyword and keyword not in q["stem"] and keyword not in q["answer"]:
            continue
        if grade != "全部" and q["grade"] != grade:
            continue
        if qtype != "全部" and q["qtype"] != qtype:
            continue
        if source and source not in q["source"]:
            continue
        if chapters and q["chapter"] not in chapters:
            continue
        if knowledge and not any(k in q["knowledge"] for k in knowledge):
            continue
        if not (diff[0] <= q["difficulty"] <= diff[1]):
            continue
        result.append(q)

    st.success(f"共筛选出 **{len(result)}** 道题")

    if not result:
        st.info("暂无符合条件的题目，请调整筛选条件。")
        return

    # ---------- 分页 ----------
    page_size = 2
    total_pages = max(1, (len(result) + page_size - 1) // page_size)
    page = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="f_page")
    start = (page - 1) * page_size
    page_items = result[start: start + page_size]

    st.caption(f"第 {page} / {total_pages} 页，每页 {page_size} 条")

    for q in page_items:
        with st.container(border=True):
            st.markdown(f"**[ID {q['id']}] {q['qtype']} · {q['grade']} · 难度 {q['difficulty']}**")
            st.markdown(q["stem"])
            with st.expander("查看答案与解析"):
                st.markdown(f"**答案：** {q['answer']}")
                st.markdown(f"**解析：** {q['analysis']}")
                st.caption(f"来源：{q['source']}　标签：{q['tags']}")


# ============================================================
# 页面 4：题目管理
# ============================================================
def page_manage():
    st.header("📝 题目管理")

    tab_add, tab_list = st.tabs(["➕ 新增题目", "📋 题目列表"])

    # ---------------- 新增 ----------------
    with tab_add:
        with st.form("form_add", clear_on_submit=True):
            st.subheader("基本信息")
            c1, c2, c3, c4 = st.columns(4)
            grade = c1.selectbox("年级 *", ["高一", "高二", "高三"])
            chapter = c2.text_input("章节 *", placeholder="如：导数")
            qtype = c3.selectbox("题型 *", ["选择题", "填空题", "解答题"])
            difficulty = c4.slider("难度 *", 1, 5, 3)

            stem = st.text_area("题干 *", height=120, placeholder="支持 LaTeX，如 $x^2+y^2=1$")
            options = st.text_area("选项（选择题填，每行一个）", height=80)
            answer = st.text_area("答案 *", height=80)
            analysis = st.text_area("解析", height=120)

            c5, c6, c7 = st.columns(3)
            knowledge = c5.text_input("知识点（逗号分隔）")
            source = c6.text_input("来源")
            tags = c7.text_input("标签（逗号分隔）")

            submitted = st.form_submit_button("保存题目", type="primary", use_container_width=True)

        if submitted:
            if not stem.strip() or not answer.strip():
                st.error("保存失败：题干和答案为必填项。")
            else:
                st.session_state.questions.append({
                    "id": _next_id(),
                    "grade": grade, "chapter": chapter or "未分类",
                    "knowledge": knowledge, "qtype": qtype,
                    "difficulty": difficulty, "stem": stem,
                    "options": options, "answer": answer,
                    "analysis": analysis, "source": source or "未填写",
                    "tags": tags,
                })
                st.success(f"已保存题目，当前题库共 {len(st.session_state.questions)} 道。")
                st.toast("保存成功 ✅", icon="✅")

    # ---------------- 列表 ----------------
    with tab_list:
        if not st.session_state.questions:
            st.info("题库为空，请先新增或导入题目。")
            return

        df = pd.DataFrame([{
            "选择": False,
            "ID": q["id"],
            "题型": q["qtype"],
            "年级": q["grade"],
            "章节": q["chapter"],
            "难度": q["difficulty"],
            "知识点": q["knowledge"],
            "来源": q["source"],
        } for q in st.session_state.questions])

        st.caption("提示：勾选左侧「选择」列后，点下方按钮可批量移入回收站。")
        edited = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={"选择": st.column_config.CheckboxColumn("选择")},
            key="editor_questions",
        )

        selected_ids = edited.loc[edited["选择"] == True, "ID"].tolist()  # noqa: E712

        c1, c2 = st.columns([1, 4])
        if c1.button("移入回收站", type="primary", disabled=not selected_ids, use_container_width=True):
            if HAS_DIALOG:
                _confirm_trash_dialog(selected_ids)
            else:
                st.session_state["_pending_trash"] = selected_ids
        c2.caption(f"已选中 {len(selected_ids)} 道题")

        # 低版本降级：复选框二次确认
        if not HAS_DIALOG and st.session_state.get("_pending_trash"):
            ids = st.session_state["_pending_trash"]
            if st.checkbox(f"我确认把这 {len(ids)} 道题移入回收站"):
                if st.button("确认移入回收站"):
                    _move_to_trash(ids)
                    st.session_state["_pending_trash"] = None
                    st.rerun()

        st.divider()
        st.subheader("题目详情预览")
        for q in st.session_state.questions[:3]:
            with st.expander(f"[ID {q['id']}] {q['qtype']} · {q['chapter']} · 难度 {q['difficulty']}"):
                st.markdown(q["stem"])
                if q["options"]:
                    st.markdown(q["options"])
                st.markdown(f"**答案：** {q['answer']}")
                st.markdown(f"**解析：** {q['analysis']}")


if HAS_DIALOG:
    @st.dialog("确认移入回收站")
    def _confirm_trash_dialog(ids):
        st.warning(f"确定要把选中的 {len(ids)} 道题移入回收站吗？可在回收站恢复。")
        c1, c2 = st.columns(2)
        if c1.button("确认移入", type="primary", use_container_width=True):
            _move_to_trash(ids)
            st.rerun()
        if c2.button("取消", use_container_width=True):
            st.rerun()


# ============================================================
# 页面 5：批量导入
# ============================================================
IMPORT_EXAMPLE = r'''[
  {
    "grade": "高三",
    "chapter": "导数",
    "knowledge": "不等式证明,极值点,分类讨论",
    "qtype": "解答题",
    "difficulty": 5,
    "stem": "(1) 证明：当 $0<x<1$ 时，$x-x^2<\\sin x<x$；\n(2) 已知函数 $f(x)=\\cos ax-\\ln(1-x^2)$，若 $x=0$ 是 $f(x)$ 的极大值点，求 $a$ 的取值范围。",
    "options": "",
    "answer": "(1) 证明见解析；\n(2) $(-\\infty,-\\sqrt{2})\\cup(\\sqrt{2},+\\infty)$",
    "analysis": "(1) 构造 $F(x)=x-\\sin x$ 和 $G(x)=\\sin x-(x-x^2)$，求导证明。",
    "source": "2023年新课标全国Ⅱ卷",
    "tags": "高考真题,新高考II卷"
  }
]'''

REQUIRED_FIELDS = ["grade", "chapter", "qtype", "difficulty", "stem", "answer"]


def page_import():
    st.header("📥 批量导入")
    st.caption("支持上传 JSON 文件，或直接粘贴 JSON 文本。导入前会先预览。")

    with st.expander("📘 JSON 格式说明与示例（点击展开）", expanded=False):
        st.markdown(
            "**必填字段**：" + "、".join(f"`{f}`" for f in REQUIRED_FIELDS) + "\n\n"
            "- `stem` 题干、`answer` 答案、`analysis` 解析中可以直接写 LaTeX，行内用 `$...$`。\n"
            "- JSON 字符串里的反斜杠要写成 `\\\\`，例如 `\\\\sin x`。\n"
            "- `knowledge` 和 `tags` 用英文逗号分隔。"
        )
        st.code(IMPORT_EXAMPLE, language="json")

    c1, c2 = st.columns(2)
    with c1:
        uploaded = st.file_uploader("方式一：上传 JSON 文件", type=["json", "txt"])
    with c2:
        st.caption("方式二：直接粘贴到下方文本框")
        pasted = st.text_area("粘贴 JSON", height=180, placeholder="把 JSON 数组粘贴到这里...")

    raw_text = ""
    if uploaded is not None:
        try:
            raw_text = uploaded.getvalue().decode("utf-8")
            st.success(f"已读取文件：{uploaded.name}")
        except UnicodeDecodeError:
            st.error("文件编码不是 UTF-8，请另存为 UTF-8 后重试。")
    elif pasted.strip():
        raw_text = pasted

    if st.button("解析并预览", type="primary"):
        if not raw_text.strip():
            st.error("请先上传文件或粘贴 JSON 文本。")
            return
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            st.error(f"JSON 解析失败：第 {e.lineno} 行第 {e.colno} 列 —— {e.msg}")
            return

        if not isinstance(data, list):
            st.error("格式错误：顶层必须是 JSON 数组（用 [ ] 包裹）。")
            return

        ok, bad = [], []
        for i, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                bad.append((i, "该条不是对象（{ }）"))
                continue
            missing = [f for f in REQUIRED_FIELDS if not str(item.get(f, "")).strip()]
            if missing:
                bad.append((i, f"缺少必填字段：{', '.join(missing)}"))
                continue
            ok.append(item)

        st.session_state.import_preview = {"ok": ok, "bad": bad}

    # ---------- 预览 ----------
    preview = st.session_state.import_preview
    if preview:
        st.divider()
        st.subheader("导入预览")
        st.success(f"可导入 **{len(preview['ok'])}** 条")
        if preview["bad"]:
            st.error(f"有问题 **{len(preview['bad'])}** 条：")
            st.dataframe(
                pd.DataFrame(preview["bad"], columns=["行号", "问题"]),
                use_container_width=True, hide_index=True,
            )

        if preview["ok"]:
            st.dataframe(
                pd.DataFrame([{
                    "年级": q.get("grade"), "章节": q.get("chapter"),
                    "题型": q.get("qtype"), "难度": q.get("difficulty"),
                    "题干（截断）": str(q.get("stem", ""))[:40] + "…",
                    "来源": q.get("source", ""),
                } for q in preview["ok"]]),
                use_container_width=True, hide_index=True,
            )

            if st.button("确认导入", type="primary"):
                prog = st.progress(0)
                for i, q in enumerate(preview["ok"]):
                    st.session_state.questions.append({
                        "id": _next_id(),
                        "grade": q.get("grade", ""),
                        "chapter": q.get("chapter", ""),
                        "knowledge": q.get("knowledge", ""),
                        "qtype": q.get("qtype", ""),
                        "difficulty": int(q.get("difficulty", 3)),
                        "stem": q.get("stem", ""),
                        "options": q.get("options", ""),
                        "answer": q.get("answer", ""),
                        "analysis": q.get("analysis", ""),
                        "source": q.get("source", ""),
                        "tags": q.get("tags", ""),
                    })
                    prog.progress((i + 1) / len(preview["ok"]))
                st.session_state.import_preview = None
                st.success(f"导入完成，成功 {len(preview['ok'])} 条。")
                st.rerun()


# ============================================================
# 页面 6：组卷
# ============================================================
def page_paper():
    st.header("📄 组卷")
    st.caption("演示：选项卡 + 数据编辑器勾选 + 表单自动抽题")

    tab_manual, tab_auto = st.tabs(["✋ 手动选题", "🤖 自动组卷"])

    # ---------------- 手动选题 ----------------
    with tab_manual:
        if not st.session_state.questions:
            st.info("题库为空，无法组卷。")
            return

        df = pd.DataFrame([{
            "选择": False, "ID": q["id"], "题型": q["qtype"],
            "年级": q["grade"], "难度": q["difficulty"], "章节": q["chapter"],
        } for q in st.session_state.questions])

        edited = st.data_editor(
            df, use_container_width=True, hide_index=True,
            column_config={"选择": st.column_config.CheckboxColumn("选择")},
            key="editor_paper",
        )
        ids = edited.loc[edited["选择"] == True, "ID"].tolist()  # noqa: E712
        st.caption(f"已选中 {len(ids)} 道题")

        if st.button("生成试卷", type="primary", disabled=not ids):
            st.session_state.paper = [
                q for q in st.session_state.questions if q["id"] in ids
            ]
            st.success(f"已生成试卷，共 {len(st.session_state.paper)} 道题。")

    # ---------------- 自动组卷 ----------------
    with tab_auto:
        with st.form("form_auto"):
            c1, c2 = st.columns(2)
            types = c1.multiselect("题型", ["选择题", "填空题", "解答题"],
                                   default=["选择题", "填空题", "解答题"])
            grades = c2.multiselect("年级", ["高一", "高二", "高三"], default=[])

            c3, c4 = st.columns(2)
            knows = c3.multiselect("知识点（留空=不限）", ["不等式证明", "极值点", "椭圆", "等差数列"])
            diff = c4.slider("难度范围", 1, 5, (1, 5))

            c5, c6 = st.columns(2)
            n_choice = c5.number_input("选择题数量", 0, 20, 2)
            n_fill = c6.number_input("填空题数量", 0, 20, 1)
            n_solve = st.number_input("解答题数量", 0, 20, 1)

            go = st.form_submit_button("自动生成试卷", type="primary", use_container_width=True)

        if go:
            pool = [q for q in st.session_state.questions if diff[0] <= q["difficulty"] <= diff[1]]
            if types:
                pool = [q for q in pool if q["qtype"] in types]
            if grades:
                pool = [q for q in pool if q["grade"] in grades]
            if knows:
                pool = [q for q in pool if any(k in q["knowledge"] for k in knows)]

            picked, shortage = [], []
            for tname, cnt in [("选择题", n_choice), ("填空题", n_fill), ("解答题", n_solve)]:
                cand = [q for q in pool if q["qtype"] == tname]
                if len(cand) < cnt:
                    shortage.append(f"{tname}：需要 {cnt} 道，题库只有 {len(cand)} 道")
                picked.extend(random.sample(cand, min(cnt, len(cand))))

            if shortage:
                st.warning("题量不足：\n\n- " + "\n- ".join(shortage))
            if picked:
                st.session_state.paper = picked
                st.success(f"已生成试卷，共 {len(picked)} 道题。")
            else:
                st.error("没有抽到任何题目，请放宽筛选条件。")

    # ---------------- 试卷预览 ----------------
    st.divider()
    st.subheader("试卷预览")
    if not st.session_state.paper:
        st.info("暂无试卷，请先手动选题或自动组卷。")
        return

    st.metric("试卷题目数", len(st.session_state.paper))
    for i, q in enumerate(st.session_state.paper, start=1):
        with st.container(border=True):
            st.markdown(f"**{i}. （{q['qtype']}，难度 {q['difficulty']}）**")
            st.markdown(q["stem"])
            if q["options"]:
                st.markdown(q["options"])
            with st.expander("答案与解析"):
                st.markdown(f"**答案：** {q['answer']}")
                st.markdown(f"**解析：** {q['analysis']}")


# ============================================================
# 页面 7：试卷导出
# ============================================================
def _build_markdown(paper, title, with_answer=True):
    lines = [f"# {title}\n"]
    for i, q in enumerate(paper, start=1):
        lines.append(f"**{i}. （{q['qtype']}，难度 {q['difficulty']}）**\n")
        lines.append(q["stem"] + "\n")
        if q["options"]:
            lines.append(q["options"] + "\n")
    if with_answer:
        lines.append("\n---\n\n## 参考答案与解析\n")
        for i, q in enumerate(paper, start=1):
            lines.append(f"**{i}.** {q['answer']}\n")
            if q["analysis"]:
                lines.append(f"> 解析：{q['analysis']}\n")
    return "\n".join(lines)


def _build_html(paper, title, with_answer=True):
    body = []
    for i, q in enumerate(paper, start=1):
        body.append(f"<p><b>{i}. （{q['qtype']}，难度 {q['difficulty']}）</b></p>")
        body.append(f"<p>{q['stem'].replace(chr(10), '<br>')}</p>")
        if q["options"]:
            body.append(f"<p>{q['options'].replace(chr(10), '<br>')}</p>")
    if with_answer:
        body.append("<hr><h2>参考答案与解析</h2>")
        for i, q in enumerate(paper, start=1):
            body.append(f"<p><b>{i}.</b> {q['answer']}</p>")
            if q["analysis"]:
                body.append(f"<blockquote>解析：{q['analysis']}</blockquote>")

    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<script>window.MathJax={tex:{inlineMath:[['$','$']]}};</script>"
        "<script src='https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js' async></script>"
        "</head><body>"
        f"<h1>{title}</h1>" + "\n".join(body) + "</body></html>"
    )


def _build_docx(paper, title, with_answer=True):
    """需要 pip install python-docx；未安装返回 None。"""
    try:
        from docx import Document
    except ImportError:
        return None

    doc = Document()
    doc.add_heading(title, level=1)
    for i, q in enumerate(paper, start=1):
        doc.add_paragraph(f"{i}. （{q['qtype']}，难度 {q['difficulty']}）")
        doc.add_paragraph(q["stem"])
        if q["options"]:
            doc.add_paragraph(q["options"])
    if with_answer:
        doc.add_page_break()
        doc.add_heading("参考答案与解析", level=2)
        for i, q in enumerate(paper, start=1):
            doc.add_paragraph(f"{i}. {q['answer']}")
            if q["analysis"]:
                doc.add_paragraph(f"解析：{q['analysis']}")

    import io
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def page_export():
    st.header("📤 试卷导出")

    if not st.session_state.paper:
        st.info("暂无试卷，请先到「组卷」页面生成试卷。")
        return

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        title = c1.text_input("试卷标题", value="高三数学练习卷")
        fmt = c2.selectbox("导出格式", ["Markdown", "HTML", "Word", "PDF"])
        with_answer = c3.toggle("包含答案解析", value=True)

    # ---------- 预览 ----------
    st.subheader("预览")
    for i, q in enumerate(st.session_state.paper, start=1):
        st.markdown(f"**{i}. （{q['qtype']}）**")
        st.markdown(q["stem"])
        if q["options"]:
            st.markdown(q["options"])

    # ---------- 下载 ----------
    st.divider()
    st.subheader("下载")

    if fmt == "Markdown":
        data = _build_markdown(st.session_state.paper, title, with_answer).encode("utf-8")
        st.download_button("⬇️ 下载 Markdown", data, file_name=f"{title}.md",
                           mime="text/markdown", type="primary")
    elif fmt == "HTML":
        data = _build_html(st.session_state.paper, title, with_answer).encode("utf-8")
        st.download_button("⬇️ 下载 HTML", data, file_name=f"{title}.html",
                           mime="text/html", type="primary")
    elif fmt == "Word":
        data = _build_docx(st.session_state.paper, title, with_answer)
        if data is None:
            st.warning("未安装 python-docx，无法导出 Word。请先运行：`pip install python-docx`")
        else:
            st.download_button(
                "⬇️ 下载 Word", data, file_name=f"{title}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
            )
    else:  # PDF
        st.warning(
            "PDF 导出为可选功能。推荐两种方案：\n\n"
            "1. 先导出 HTML，用浏览器「打印 → 另存为 PDF」；\n"
            "2. 安装 `pip install weasyprint` 后由程序生成（依赖较多，MVP 阶段可不做）。"
        )


# ============================================================
# 页面 8：回收站
# ============================================================
def page_trash():
    st.header("🗑️ 回收站")
    st.caption("演示：空状态提示 + 危险操作二次确认")

    if not st.session_state.trash:
        st.info("回收站为空。删除的题目会先进入这里，可随时恢复。")
        return

    st.metric("回收站题目数", len(st.session_state.trash))

    df = pd.DataFrame([{
        "ID": q["id"], "题型": q["qtype"], "年级": q["grade"],
        "章节": q["chapter"], "难度": q["difficulty"],
        "题干（截断）": q["stem"][:35] + "…",
    } for q in st.session_state.trash])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 3])

    if c1.button("全部恢复", use_container_width=True):
        st.session_state.questions.extend(st.session_state.trash)
        st.session_state.trash = []
        st.success("已全部恢复。")
        st.rerun()

    confirm = c2.checkbox("我确认清空")
    if c2.button("清空回收站", type="primary", disabled=not confirm, use_container_width=True):
        st.session_state.trash = []
        st.success("回收站已清空。")
        st.rerun()

    st.divider()
    st.subheader("逐条操作")
    for q in st.session_state.trash:
        with st.container(border=True):
            st.markdown(f"**[ID {q['id']}] {q['qtype']} · {q['chapter']}**")
            st.markdown(q["stem"][:100] + ("…" if len(q["stem"]) > 100 else ""))
            cc1, cc2, _ = st.columns([1, 1, 5])
            if cc1.button("恢复", key=f"restore_{q['id']}", use_container_width=True):
                st.session_state.questions.append(q)
                st.session_state.trash = [x for x in st.session_state.trash if x["id"] != q["id"]]
                st.rerun()
            if cc2.button("彻底删除", key=f"purge_{q['id']}", use_container_width=True):
                st.session_state.trash = [x for x in st.session_state.trash if x["id"] != q["id"]]
                st.rerun()


# ============================================================
# 侧边栏导航 + 主入口
# ============================================================
def main():
    init_state()

    PAGES = {
        "📖 术语速查": page_terms,
        "🎨 基础组件": page_basics,
        "🔍 搜索与筛选": page_search,
        "📝 题目管理": page_manage,
        "📥 批量导入": page_import,
        "📄 组卷": page_paper,
        "📤 试卷导出": page_export,
        "🗑️ 回收站": page_trash,
    }

    with st.sidebar:
        st.title("📐 数学题库")
        st.caption("UI 原型演示")
        st.divider()

        choice = st.radio("导航", list(PAGES.keys()), label_visibility="collapsed")

        st.divider()
        st.metric("题库总量", len(st.session_state.questions))
        st.metric("回收站", len(st.session_state.trash))
        st.caption(f"Streamlit {st.__version__}")
        if not HAS_DIALOG:
            st.warning("当前版本 < 1.37，弹窗已降级为复选框确认。")

    PAGES[choice]()


if __name__ == "__main__":
    main()