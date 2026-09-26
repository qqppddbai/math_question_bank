# -*- coding: utf-8 -*-
"""数学题库管理系统 —— Streamlit 入口。
启动方式：在项目根目录执行  streamlit run app.py
"""
import sys
from pathlib import Path

# 保证以项目根目录为导入路径，任何方式启动都能 import src.*
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from src.config import APP_TITLE, QUESTION_FONT_STACK, UI_QUESTION_FONT_SIZE
from src.database import init_db
from src.ui import (export_page, home, import_page, paper_page, question_page,
                    recycle_page, search_page, student_page, settings_page)

# ---------- 页面基础配置（必须第一个 st 调用） ----------
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner=False)
def _bootstrap() -> bool:
    """应用启动时建表，只跑一次。"""
    init_db()
    return True


_bootstrap()

# ---------- 极简全局样式，让界面更干净 ----------
st.markdown(
    """
    <style>
      /* 收紧默认上下留白 */
      .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px;}
      /* 侧边栏导航项更好点 */
      section[data-testid="stSidebar"] .stRadio label {
          padding: 6px 8px; border-radius: 8px; cursor: pointer;
      }
      section[data-testid="stSidebar"] .stRadio label:hover {background: #f0f2f6;}
      h1, h2, h3 {letter-spacing: .5px;}
      /* 含分数 / 根号 / 上下堆叠的公式，增加上下留白，避免上下文拥挤 */
      .katex .mfrac,
      .katex .msqrt,
      .katex .mroot {
        padding: 0.22em 0;
      }
      /* 顺带：行内公式整体稍微宽容一点 */
      .katex {
        line-height: 1.4;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- 题目显示统一字体：宋体 六号（7.5pt ≈ 10px） ----------
# 只作用于 src/ui 里用 st.container(key="qdisp_...") 包起来的题目内容
# （题干 / 选项 / 答案 / 解析 / 卡片元信息），界面标题、按钮、筛选控件不受影响。
# KaTeX 公式自带数学字体，字号用 em，会随父级字号等比缩放，无需单独处理。
st.markdown(
    f"""
    <style>
      [class*="st-key-qdisp"] p,
      [class*="st-key-qdisp"] li,
      [class*="st-key-qdisp"] div[data-testid="stMarkdownContainer"] {{
        font-family: {QUESTION_FONT_STACK} !important;
        font-size: {UI_QUESTION_FONT_SIZE} !important;
        line-height: 1.75 !important;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- 路由表：新增页面只要在这里加一行 ----------
PAGES = {
    "🏠  首页概览": home.render,
    "📚  题目管理": question_page.render,
    "🔍  搜索筛选": search_page.render,
    "📥  批量导入": import_page.render,
    "📝  手动组卷": paper_page.render,
    "📤  试卷导出": export_page.render,
    "👨‍🎓  学生档案": student_page.render,
    "🗑️  回收站":   recycle_page.render,
    "⚙️  系统设置":  settings_page.render,
}

with st.sidebar:
    st.markdown(f"### 📘 {APP_TITLE}")
    st.caption("本地运行 · 数据存于 data/ 目录")
    st.divider()
    choice = st.radio("导航", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    st.caption("v0.1 · MVP")

PAGES[choice]()