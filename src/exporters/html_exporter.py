# -*- coding: utf-8 -*-
"""HTML 导出：内置 KaTeX CDN，图片以 base64 内嵌。浏览器打开即可打印成 PDF。"""
from __future__ import annotations

import html

from src.config import (EXPORT_QUESTION_FONT_PT, PAPER_PLAIN_FONT_PT,
                        PAPER_PLAIN_FONT_STACK, QUESTION_FONT_STACK)
from src.exporters.common import (PaperView, image_to_data_uri,
                                  resolve_image_path, text_image_blocks)

# 题目、答案、解析、题号：宋体 五号（10.5pt）
Q_SIZE_PT = EXPORT_QUESTION_FONT_PT
# 其他部分（标题 / 副标题 / 大题标题 / 大题说明 / 参考答案标题等）：黑体 小四（12pt）
P_SIZE_PT = PAPER_PLAIN_FONT_PT
P_FAMILY = PAPER_PLAIN_FONT_STACK

KATEX_VERSION = "0.16.9"
KATEX_CSS = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.css"
KATEX_JS = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.js"
KATEX_AUTO = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/contrib/auto-render.min.js"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def _section_meta(sec) -> str:
    if not sec.items:
        return ""
    return f"（共 {sec.count} 题）"


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


def _render_inline_images(block) -> str:
    """正文里按 ![[img:N]] 插进来的单张图片块。"""
    rel = block.get("path")
    number = block.get("number")
    if not rel:
        return (f'<div class="missing-image">'
                f'［配图 {number} 不存在：请检查 ![[img:{number}]] 的序号］</div>')
    uri = image_to_data_uri(rel)
    if not uri:
        return f'<div class="missing-image">［配图 {number} 文件已丢失］</div>'
    width = block.get("size")
    style = f' style="width:{int(width)}px;max-width:100%;"' if width else ""
    return f'<div class="inline-image"><img src="{uri}" alt="配图 {number}"{style}></div>'


def _render_mixed(text: str, images) -> str:
    """正文（题干 / 解析）：按标记把文字和图片交替排出来。

    文字部分保留原样交给 KaTeX 处理；图片部分单独成块。
    旧数据（没有标记）会得到"整段文字 + 末尾图片"，与以前一致。
    """
    out = []
    for block in text_image_blocks(text, images):
        if block["type"] == "text":
            out.append(f'<div class="text-part">{_esc(block["text"])}</div>')
        else:
            out.append(_render_inline_images(block))
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
    # 题干：按 ![[img:N]] 标记把图片插到文字之间（无标记则图片排在末尾）
    stem_inner = _render_mixed(it.stem, it.image_list) if include_images \
        else f'<div class="text-part">{_esc(it.stem)}</div>'
    parts.append(
        f'<div class="stem"><span class="num">{it.number}.</span> {stem_inner}</div>'
    )

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
            if include_images and it.analysis_images:
                a.append('<div class="ans-line"><b>解析：</b></div>')
                a.append(_render_mixed(it.analysis, it.analysis_images))
            else:
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

    # 说明：按需求不显示考试时间 / 满分 / 姓名班级得分，也不显示每题分值。

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
                if include_answer and it.answer:
                    block.append(_text_block("答案：", it.answer))
                if include_analysis and it.analysis:
                    if include_images and it.analysis_images:
                        block.append('<div class="ans-line"><b>解析：</b></div>')
                        block.append(_render_mixed(it.analysis, it.analysis_images))
                    else:
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
    font-size: {Q_SIZE_PT}pt;   /* 题目 / 答案 / 解析 / 题号：宋体 五号 */
    color: #000;
    padding: 0 1em;
  }}
  /* 下面这些「非题目部分」统一用黑体小四 */
  h1.title {{
    font-family: {P_FAMILY};
    font-size: {P_SIZE_PT}pt;
    text-align:center;
    margin-bottom: 0.3em;
  }}
  .subtitle {{
    font-family: {P_FAMILY};
    font-size: {P_SIZE_PT}pt;
    text-align:center; color:#555; margin-bottom: 1.6em;
  }}
  h2 {{
    font-family: {P_FAMILY};
    font-size: {P_SIZE_PT}pt;
    border-bottom: 1px solid #bbb;
    padding-bottom: 4px;
    margin-top: 2em;
    margin-bottom: 0.4em;
  }}
  .sec-meta {{
    font-family: {P_FAMILY};
    font-size: {P_SIZE_PT}pt;
    color:#666; margin-bottom: 1em;
  }}
  .item {{ margin-bottom: 1.4em; page-break-inside: avoid; }}
  .stem {{ white-space: pre-wrap; word-wrap: break-word; }}
  .num {{ font-weight: bold; margin-right: 0.2em; }}
  .options {{ margin-left: 2em; margin-top: 0.3em; }}
  .option {{ white-space: pre-wrap; word-wrap: break-word; }}
  .images {{ margin: 0.6em 0 0.6em 2em; }}
  .images img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0.4em 0;
  }}
  /* 正文里按 ![[img:N]] 插进来的图片：独占一行，跟在标记所在的位置 */
  .inline-image {{ margin: 0.6em 0 0.6em 2em; }}
  .inline-image img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0.2em 0;
  }}
  .text-part {{ white-space: pre-wrap; word-wrap: break-word; }}
  .missing-image {{
    font-family: {P_FAMILY};
    color: #999; font-size: {P_SIZE_PT}pt; font-style: italic;
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
    .inline-image img {{ max-width: 80%; }}
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