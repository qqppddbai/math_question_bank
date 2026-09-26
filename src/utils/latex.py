# -*- coding: utf-8 -*-
"""LaTeX / Markdown 预览辅助。

Streamlit 的 st.markdown 默认使用 KaTeX 渲染 $...$ 与 $$...$$，
我们只需把纯文本转成能保留换行的 markdown 即可。
"""


def md(text: str) -> str:
    """把用户输入转成 markdown：
    - 单换行 -> 行尾补两个空格，保证换行生效
    - 空值直接返回空串
    不做 HTML 转义，由 st.markdown 默认的安全模式处理。
    """
    if not text:
        return ""
    return str(text).replace("\r\n", "\n").replace("\n", "  \n")


def strip_latex_for_preview(text: str, limit: int = 80) -> str:
    """去掉常见 LaTeX 标记，供列表标题这种纯文本场景使用。"""
    if not text:
        return ""
    s = str(text)
    s = s.replace("\\", "")
    s = s.replace("$", "")
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    if len(s) > limit:
        s = s[:limit] + "…"
    return s