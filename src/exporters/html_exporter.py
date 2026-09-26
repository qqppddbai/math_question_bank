# -*- coding: utf-8 -*-
"""HTML 导出：内置 KaTeX CDN，图片以 base64 内嵌。浏览器打开即可打印成 PDF。"""
from __future__ import annotations

import html

from src.config import EXPORT_QUESTION_FONT_PT, QUESTION_FONT_STACK
from src.exporters.common import PaperView, image_to_data_uri

# 题目显示统一字体：宋体 五号（10.5pt）。要改字号只改 src/config.py。
Q_SIZE_PT = EXPORT_QUESTION_FONT_PT

KATEX_VERSION = "0.16.9"
KATEX_CSS = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.css"
KATEX_JS = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.js"
KATEX_AUTO = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/contrib/auto-render.min.js"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def _section_meta(sec) -> str:
    if not sec.items:
        return ""
    scores = {it.score for it in sec.items}
    if len(scores) == 1:
        s = next(iter(scores))
        return f"（共 {sec.count} 题，每题 {s} 分，共 {sec.total_score} 分）"
    return f"（共 {sec.count} 题，共 {sec.total_score} 分）"


def _render_images(image_list) -> str:
    if not image_list:
        return ""
    out = ['<div class="images">']
    for rel in image_list:
        uri = image_to_data_uri(rel)
        if uri:
            out.append(f'<img src="{uri}" alt="题图">')
        else:
            out.append('<div class="missing-image">［图片丢失］</div>')
    out.append('</div>')
    return "".join(out)


def _text_block(label: str, text: str) -> str:
    """答案 / 解析一行：多行文本必须走 .ans-line 才能保留换行。

    题干的换行靠 .stem 的 white-space: pre-wrap 生效；
    答案 / 解析如果只是裸 <div>，默认 white-space: normal 会把 \\n 折叠成空格，
    多行解析就会挤成一坨。所以这里统一挂 .ans-line 类。
    """
    return f'<div class="ans-line"><b>{label}</b>{_esc(text)}</div>'


def _render_item(it, include_answer, include_analysis, answers_at_end,
                 include_images) -> str:
    parts = ['<div class="item">']
    parts.append(
        f'<div class="stem"><span class="num">{it.number}.</span>'
        f'<span class="score">（{it.score} 分）</span> {_esc(it.stem)}</div>'
    )
    if include_images and it.image_list:
        parts.append(_render_images(it.image_list))

    if it.options:
        parts.append('<div class="options">')
        for o in it.options:
            text = (o.get("text") or "").strip()
            if not text:
                continue
            parts.append(
                f'<div class="option"><b>{_esc(o.get("key",""))}.</b> {_esc(text)}</div>'
            )
        parts.append('</div>')

    if not answers_at_end and (include_answer or include_analysis):
        a = []
        if include_answer and it.answer:
            a.append(_text_block("答案：", it.answer))
        if include_analysis and it.analysis:
            a.append(_text_block("解析：", it.analysis))
        if a:
            parts.append('<div class="answer-block">' + "".join(a) + '</div>')

    parts.append('</div>')
    return "".join(parts)


def export_html(view: PaperView, *, include_answer: bool = True,
                include_analysis: bool = True, answers_at_end: bool = False,
                include_images: bool = True) -> str:
    body = []
    body.append(f'<h1 class="title">{_esc(view.title)}</h1>')
    if view.subtitle:
        body.append(f'<div class="subtitle">{_esc(view.subtitle)}</div>')

    meta = []
    if view.exam_minutes:
        meta.append(f"考试时间：{view.exam_minutes} 分钟")
    meta.append(f"满分：{view.total_score} 分")
    body.append(f'<div class="meta">{"　".join(meta)}</div>')
    body.append('<div class="info-line">姓名：__________　学校：__________　得分：__________</div>')

    for sec in view.sections:
        body.append(f'<h2>{_esc(sec.title)}</h2>')
        m = _section_meta(sec)
        if m:
            body.append(f'<div class="sec-meta">{_esc(m)}</div>')
        for it in sec.items:
            body.append(_render_item(it, include_answer, include_analysis,
                                     answers_at_end, include_images))

    if answers_at_end and (include_answer or include_analysis):
        body.append('<div class="divider"></div>')
        body.append('<h1 class="title">参考答案与解析</h1>')
        for sec in view.sections:
            body.append(f'<h2>{_esc(sec.title)}</h2>')
            for it in sec.items:
                block = [f'<div class="item"><div class="stem">'
                         f'<span class="num">{it.number}.</span></div>']
                if include_images and it.image_list:
                    block.append(_render_images(it.image_list))
                if include_answer and it.answer:
                    block.append(_text_block("答案：", it.answer))
                if include_analysis and it.analysis:
                    block.append(_text_block("解析：", it.analysis))
                block.append('</div>')
                body.append("".join(block))

    content = "\n".join(body)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{_esc(view.title)}</title>
<link rel="stylesheet" href="{KATEX_CSS}">
<style>
  body {{
    font-family: {QUESTION_FONT_STACK};
    max-width: 800px;
    margin: 2em auto;
    line-height: 1.85;
    font-size: {Q_SIZE_PT}pt;   /* 题目正文：宋体 五号 */
    color: #000;
    padding: 0 1em;
  }}
  h1.title {{ text-align:center; font-size: 22px; margin-bottom: 0.3em; }}
  .subtitle {{ text-align:center; color:#555; margin-bottom: 0.8em; }}
  .meta {{ text-align:center; color:#333; margin-bottom: 0.5em; }}
  .info-line {{ text-align:center; letter-spacing: 2px; margin-bottom: 2.2em; }}
  h2 {{
    font-size: 17px;
    border-bottom: 1px solid #bbb;
    padding-bottom: 4px;
    margin-top: 2em;
    margin-bottom: 0.4em;
  }}
  .sec-meta {{ color:#666; font-size: 13px; margin-bottom: 1em; }}
  .item {{ margin-bottom: 1.4em; page-break-inside: avoid; }}
  .stem {{ white-space: pre-wrap; word-wrap: break-word; }}
  .num {{ font-weight: bold; margin-right: 0.2em; }}
  .score {{ color:#666; font-size: inherit; }}
  .options {{ margin-left: 2em; margin-top: 0.3em; }}
  .option {{ white-space: pre-wrap; word-wrap: break-word; }}
  .images {{ margin: 0.6em 0 0.6em 2em; }}
  .images img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0.4em 0;
  }}
  .missing-image {{
    color: #999; font-size: 13px; font-style: italic;
    padding: 4px 8px; border: 1px dashed #ccc; display: inline-block;
  }}
  .answer-block {{
    margin: 0.7em 0 0.7em 2em;
    padding: 0.6em 1em;
    background: #f5f6f8;
    border-left: 3px solid #99a;
    font-size: inherit;
    white-space: pre-wrap;
    word-wrap: break-word;
  }}
  /* 答案 / 解析正文：保留原始换行（卷末统一时没有 .answer-block 兜底） */
  .ans-line {{ white-space: pre-wrap; word-wrap: break-word; }}
  .divider {{ border-top: 1px dashed #bbb; margin: 2.2em 0; }}

  @media print {{
    body {{ max-width: 100%; margin: 0; padding: 0 15mm; font-size: {Q_SIZE_PT}pt; }}
    h2 {{ page-break-after: avoid; }}
    .answer-block {{ background: #fafafa; }}
    .images img {{ max-width: 80%; }}
  }}
</style>
</head>
<body>
{content}
<script src="{KATEX_JS}"></script>
<script src="{KATEX_AUTO}"></script>
<script>
  renderMathInElement(document.body, {{
    delimiters: [
      {{left: '$$', right: '$$', display: true}},
      {{left: '$', right: '$', display: false}},
      {{left: '\\\\(', right: '\\\\)', display: false}},
      {{left: '\\\\[', right: '\\\\]', display: true}}
    ],
    throwOnError: false
  }});
</script>
</body>
</html>
"""