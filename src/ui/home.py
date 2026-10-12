# -*- coding: utf-8 -*-
"""首页：题库概览 + 使用说明 / 注意事项。"""
import streamlit as st
from sqlalchemy import func, select

from src.database import session_scope
from src.models import Paper, Question, Student

# ------------------------------------------------------------
# 使用说明：按老师实际操作的先后顺序写
# ------------------------------------------------------------
GUIDE_STEPS = [
    ("📥", "批量导入题目",
     "先到「批量导入」页粘贴 JSON 数组，或直接下载示例文件照着改。"
     "`stem`（题干）是必填项，题干、答案、解析里都可以直接写 LaTeX，"
     "行内公式使用单个 `$…$`，独立公式使用 `$$…$$`。"),
    ("📚", "整理题目",
     "在「题目管理」里可以改题干、选项、配图，并给每道题标注**年级 / 章节 / "
     "知识点 / 标签 / 难度**。这些标注填得越细，「搜索筛选」和「手动组卷」"
     "挑题就越准。\n\n"
     "配图分两组，上传在哪一组就显示在哪个位置：**题干配图**显示在题干下方，"
     "**解析配图**显示在「📖 查看答案与解析」面板里（例如辅助线、解题步骤图）。"
     "列表固定按题库编号排列，改完保存不会让题目换位置。\n\n"
     "**想把图片插到文字中间**（比如「如图」之后、解题步骤之间）：在「图片」区每个"
     "缩略图下面都有一个可复制的标记（只有一张图时是 `![[img]]`，多张图是 "
     "`![[img:1]]`、`![[img:2]]`），把它粘到正文里想放图片的位置即可；想指定图片"
     "宽度就写成 `![[img:1|300]]`（宽 300 像素）。**没有写标记的图片会排在文字最后**，"
     "所以老题目不用改。"),
    ("🔍", "搜题与筛选",
     "「搜索筛选」支持关键词 + 题型 / 年级 / 章节 / 来源 / 难度 / 知识点 / 标签 / "
     "创建时间的组合筛选，结果可以多选后批量加标签、移除标签、导出 JSON 或删除。"),
    ("📝", "手动组卷",
     "在「手动组卷」里挑题加入试卷，**加入顺序就是卷面顺序**。"
     "试卷会按题型自动分成「单选题 / 多选题 / 填空题 / 判断题 / 作图题 / 解答题」"
     "几个大题，没有的题型自动跳过。"),
    ("📤", "导出试卷",
     "「试卷导出」支持 Word（可继续编辑）、HTML（浏览器 Ctrl+P 另存为 PDF）、"
     "Markdown 三种格式，可选是否带答案、解析、题目配图，答案可以放在每题后或卷末。"),
    ("👨‍🎓", "学生档案",
     "在「学生档案」里建学生（登记**学校 / 班级**），把错题收进档案并记录学生的"
     "错答、错因和掌握程度。错题的图片在「编辑」里上传，会显示在错题卡片上。"),
]

NOTES = [
    "**数据都在本机**：题库、图片、导出文件分别放在项目目录的 `data/`、"
    "`data/images/`、`data/student_files/`、`data/exports/` 下，不联网、不上传。",
    "**定期备份**：到「系统设置」页导出备份（或直接复制 `data/` 整个目录）。"
    "删除题目前系统会先备份数据库。",
    "**删除是软删除**：题目、试卷、学生删除后进「回收站」，可以还原；"
    "只有「彻底删除」才不可恢复。被试卷引用的题目不能彻底删除，需要先从试卷里移除。",
    "**Word 里的公式**是 LaTeX 原文（如 `$x^2$`），不是 Word 原生公式，"
    "需要打印或排版时建议导出 HTML 用浏览器打开后`Ctrl+P`可转 PDF。",
    "**图片格式**：png / jpg / webp / gif 都可以上传，单张不超过 5MB；"
    "导出 Word 时会自动把不兼容的图片（webp、缺少标准文件头的 jpg）转成 png 再插入。",
    "**题目重复**：按题干去掉所有空白后的内容判重，导入时会提示重复题目。",
]


def render():
    st.header("🏠 首页概览")

    try:
        with session_scope() as s:
            q_total = s.scalar(
                select(func.count()).select_from(Question).where(Question.is_deleted.is_(False))
            ) or 0
            q_trash = s.scalar(
                select(func.count()).select_from(Question).where(Question.is_deleted.is_(True))
            ) or 0
            p_total = s.scalar(
                select(func.count()).select_from(Paper).where(Paper.is_deleted.is_(False))
            ) or 0
            stu_total = s.scalar(
                select(func.count()).select_from(Student).where(Student.is_deleted.is_(False))
            ) or 0
    except Exception as e:  # 数据库异常不至于白屏
        st.error(f"读取数据库失败：{e}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("题库题目", f"{q_total} 道")
    c2.metric("试卷", f"{p_total} 份")
    c3.metric("学生", f"{stu_total} 人")
    c4.metric("回收站", f"{q_trash} 道")

    st.divider()
    st.subheader("🧭 使用说明")

    for icon, title, desc in GUIDE_STEPS:
        with st.container(border=True):
            st.markdown(f"**{icon} {title}**")
            st.markdown(desc)

    st.divider()
    st.subheader("⚠️ 备注")
    for note in NOTES:
        st.markdown(f"- {note}")

    if q_total == 0:
        st.divider()
        st.info(
            "题库还是空的。建议先到 **📥 批量导入** 粘贴 JSON 数组导入，"
            "或到 **📚 题目管理** 手动新增第一道题。"
        )
