# -*- coding: utf-8 -*-
"""学生错题与学习图片集导出：Word / HTML / Markdown。

与试卷导出同构：
    DB 数据 → build_student_view() → StudentView → 各格式 exporter
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.config import EXPORT_QUESTION_FONT_PT, QUESTION_FONT_NAME, QUESTION_FONT_STACK
from src.exporters.common import image_to_data_uri, resolve_image_path
from src.exporters.word_exporter import emit_text

# 与 student_page 保持一致；放在 exporter 里避免循环导入
MASTERY_LABELS = {
    0: "❌ 未掌握",
    1: "⚠️ 部分掌握",
    2: "✅ 基本掌握",
    3: "🌟 已掌握",
}

WORD_IMAGE_WIDTH_CM = 9.0

# 题目显示统一字体：宋体 五号（10.5pt）。要改字号只改 src/config.py。
Q_FONT = QUESTION_FONT_NAME
Q_SIZE = EXPORT_QUESTION_FONT_PT


# ============================================================
# 视图结构
# ============================================================
@dataclass
class MistakeView:
    number: int
    question_id: int
    stem: str
    answer: str
    wrong_answer: str
    error_reason: str
    mastery: int
    created_at: datetime | None
    images: List[str] = field(default_factory=list)      # 相对 data/ 的路径


@dataclass
class LooseImageView:
    path: str
    caption: str = ""


@dataclass
class StudentView:
    name: str
    class_name: str
    grade: str
    notes: str
    mistakes: List[MistakeView] = field(default_factory=list)
    loose_images: List[LooseImageView] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"{self.name or '学生'} · 错题与学习记录"


def build_student_view(student, mistakes: List[Dict],
                       loose_files: List[Dict]) -> StudentView:
    """从 service 层拿到的 dict 结构构造导出视图。"""
    mv: List[MistakeView] = []
    for i, m in enumerate(mistakes, start=1):
        mv.append(MistakeView(
            number=i,
            question_id=m.get("question_id") or 0,
            stem=m.get("snapshot_stem") or "",
            answer=m.get("snapshot_answer") or "",
            wrong_answer=m.get("wrong_answer") or "",
            error_reason=m.get("error_reason") or "",
            mastery=int(m.get("mastery", 0) or 0),
            created_at=m.get("created_at"),
            images=[f["path"] for f in m.get("files", []) if f.get("path")],
        ))

    loose = [LooseImageView(path=f["path"], caption=f.get("caption") or "")
             for f in loose_files if f.get("path")]

    return StudentView(
        name=student.name or "",
        class_name=student.class_name or "",
        grade=student.grade or "",
        notes=student.notes or "",
        mistakes=mv,
        loose_images=loose,
    )


# ============================================================
# Markdown
# ============================================================
def _ml(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\n", "  \n")


def _emit_images_md(lines, image_list, missing_hint="［图片丢失］"):
    for rel in image_list or []:
        uri = image_to_data_uri(rel)
        if uri:
            lines.append(f"![]({uri})")
            lines.append("")
        else:
            lines.append(f"_{missing_hint}_")
            lines.append("")


def export_student_markdown(view: StudentView, *, include_images: bool = True) -> str:
    lines = [f"# {view.title}", ""]

    meta = []
    if view.class_name:
        meta.append(f"班级：{view.class_name}")
    if view.grade:
        meta.append(f"年级：{view.grade}")
    if meta:
        lines.append("　".join(meta))
        lines.append("")
    if view.notes:
        lines.append(f"*备注：{view.notes}*")
        lines.append("")
    lines.append(f"共 {len(view.mistakes)} 道错题")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ---------- 错题 ----------
    lines.append("## 一、错题记录")
    lines.append("")
    if not view.mistakes:
        lines.append("_暂无错题。_")
        lines.append("")
    for m in view.mistakes:
        lines.append(f"### {m.number}. 题目 #{m.question_id}")
        created = m.created_at.strftime("%Y-%m-%d") if m.created_at else "—"
        lines.append(f"*掌握程度：{MASTERY_LABELS.get(m.mastery, '—')}　"
                     f"记录于 {created}*")
        lines.append("")

        lines.append("**题干**")
        lines.append("")
        lines.append(_ml(m.stem) or "_（无）_")
        lines.append("")

        if include_images and m.images:
            _emit_images_md(lines, m.images)

        if m.answer:
            lines.append("**参考答案**")
            lines.append("")
            lines.append(_ml(m.answer))
            lines.append("")

        if m.wrong_answer:
            lines.append("**学生错答**")
            lines.append("")
            lines.append("> " + _ml(m.wrong_answer))
            lines.append("")

        if m.error_reason:
            lines.append("**错因分析**")
            lines.append("")
            lines.append(_ml(m.error_reason))
            lines.append("")

        lines.append("---")
        lines.append("")

    # ---------- 学习图片 ----------
    if include_images and view.loose_images:
        lines.append("## 二、学习图片")
        lines.append("")
        for i, img in enumerate(view.loose_images, start=1):
            if img.caption:
                lines.append(f"**{i}. {img.caption}**")
                lines.append("")
            _emit_images_md(lines, [img.path])
        lines.append("")

    return "\n".join(lines)


# ============================================================
# HTML
# ============================================================
import html as _htmlmod

KATEX_VERSION = "0.16.9"
KATEX_CSS = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.css"
KATEX_JS = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.js"
KATEX_AUTO = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/contrib/auto-render.min.js"


def _esc(text: str) -> str:
    return _htmlmod.escape(text or "", quote=False)


def _render_images_html(image_list) -> str:
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


def export_student_html(view: StudentView, *, include_images: bool = True) -> str:
    body = [f'<h1 class="title">{_esc(view.title)}</h1>']

    meta = []
    if view.class_name:
        meta.append(f"班级：{view.class_name}")
    if view.grade:
        meta.append(f"年级：{view.grade}")
    if meta:
        body.append(f'<div class="meta">{"　".join(meta)}</div>')
    if view.notes:
        body.append(f'<div class="notes">备注：{_esc(view.notes)}</div>')
    body.append(f'<div class="meta">共 {len(view.mistakes)} 道错题</div>')

    # 错题
    body.append('<h2>一、错题记录</h2>')
    if not view.mistakes:
        body.append('<p><i>暂无错题。</i></p>')
    for m in view.mistakes:
        created = m.created_at.strftime("%Y-%m-%d") if m.created_at else "—"
        body.append('<div class="mistake">')
        body.append(
            f'<div class="m-head"><b>{m.number}. 题目 #{m.question_id}</b>'
            f'<span class="m-meta">掌握程度：{_esc(MASTERY_LABELS.get(m.mastery, "—"))}'
            f'　记录于 {created}</span></div>'
        )
        body.append('<div class="block"><div class="label">题干</div>'
                    f'<div class="stem">{_esc(m.stem) or "（无）"}</div></div>')
        if include_images and m.images:
            body.append(_render_images_html(m.images))
        if m.answer:
            body.append('<div class="block"><div class="label">参考答案</div>'
                        f'<div class="answer">{_esc(m.answer)}</div></div>')
        if m.wrong_answer:
            body.append('<div class="block wrong"><div class="label">学生错答</div>'
                        f'<div class="text">{_esc(m.wrong_answer)}</div></div>')
        if m.error_reason:
            body.append('<div class="block reason"><div class="label">错因分析</div>'
                        f'<div class="text">{_esc(m.error_reason)}</div></div>')
        body.append('</div>')

    # 学习图片
    if include_images and view.loose_images:
        body.append('<h2>二、学习图片</h2>')
        for i, img in enumerate(view.loose_images, start=1):
            if img.caption:
                body.append(f'<div class="caption"><b>{i}. {_esc(img.caption)}</b></div>')
            body.append(_render_images_html([img.path]))

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
    max-width: 820px;
    margin: 2em auto;
    line-height: 1.85;
    font-size: {Q_SIZE}pt;   /* 题目正文：宋体 五号 */
    color: #000;
    padding: 0 1em;
  }}
  h1.title {{ text-align:center; font-size: 22px; margin-bottom: 0.4em; }}
  .meta {{ text-align:center; color:#333; margin-bottom: 0.3em; }}
  .notes {{ text-align:center; color:#666; font-size: 13px; margin-bottom: 0.6em; }}
  h2 {{
    font-size: 17px;
    border-bottom: 1px solid #bbb;
    padding-bottom: 4px;
    margin-top: 2em;
    margin-bottom: 0.6em;
  }}
  .mistake {{
    margin: 1.6em 0;
    padding: 0.8em 1em;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    page-break-inside: avoid;
  }}
  .m-head {{ margin-bottom: 0.6em; }}
  .m-meta {{ color:#666; font-size: 12px; margin-left: 1em; }}
  .block {{ margin: 0.5em 0; }}
  .block .label {{ font-weight: bold; color: #444; font-size: inherit; }}
  .stem {{ white-space: pre-wrap; word-wrap: break-word; }}
  .answer {{ white-space: pre-wrap; word-wrap: break-word; color: #333; }}
  /* 学生错答 / 错因分析：同样保留原始换行 */
  .text {{ white-space: pre-wrap; word-wrap: break-word; }}
  .block.wrong {{
    padding: 0.5em 0.8em;
    background: #fff2f2;
    border-left: 3px solid #e55;
  }}
  .block.reason {{
    padding: 0.5em 0.8em;
    background: #f6f6ff;
    border-left: 3px solid #77a;
  }}
  .images {{ margin: 0.6em 0 0.6em 1em; }}
  .images img {{ max-width: 100%; height: auto; display: block; margin: 0.4em 0; }}
  .missing-image {{
    color: #999; font-size: 13px; font-style: italic;
    padding: 4px 8px; border: 1px dashed #ccc; display: inline-block;
  }}
  .caption {{ margin-top: 1em; color: #333; }}
  @media print {{
    body {{ max-width: 100%; margin: 0; padding: 0 15mm; font-size: {Q_SIZE}pt; }}
    .images img {{ max-width: 75%; }}
    .mistake {{ border-color: #ccc; }}
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


# ============================================================
# Word
# ============================================================
def export_student_word(view: StudentView, filepath: Path, *,
                        include_images: bool = True) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    def style_run(run, *, name=Q_FONT, size=Q_SIZE, bold=False, italic=False):
        run.bold = bold
        run.italic = italic
        run.font.name = name
        run.font.size = Pt(size)
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn("w:eastAsia"), name)

    def add_text(paragraph, text, *, name=Q_FONT, size=Q_SIZE, bold=False, italic=False):
        # 复用试卷导出的混排逻辑：$...$ 写成真正的 OMML 公式，而不是 LaTeX 原文
        li = paragraph.paragraph_format.left_indent
        emit_text(doc, text, name=name, size=size, bold=bold, italic=italic,
                  paragraph=paragraph, indent_cm=li.cm if li is not None else None)

    def add_images(image_list):
        for rel in image_list or []:
            p = resolve_image_path(rel)
            if p is None:
                para = doc.add_paragraph()
                para.paragraph_format.left_indent = Cm(1.0)
                r = para.add_run("［图片丢失］")
                style_run(r, name="宋体", size=10, italic=True)
                continue
            try:
                doc.add_picture(str(p), width=Cm(WORD_IMAGE_WIDTH_CM))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:
                para = doc.add_paragraph()
                r = para.add_run("［图片插入失败］")
                style_run(r, name="宋体", size=10, italic=True)

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(2.0)
        sec.bottom_margin = Cm(2.0)
        sec.left_margin = Cm(2.5)
        sec.right_margin = Cm(2.5)

    # 标题
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(p, view.title, name="黑体", size=16, bold=True)

    meta = []
    if view.class_name:
        meta.append(f"班级：{view.class_name}")
    if view.grade:
        meta.append(f"年级：{view.grade}")
    if meta:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_text(p, "　".join(meta), name="宋体", size=11)

    if view.notes:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_text(p, f"备注：{view.notes}", name="楷体", size=10, italic=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(p, f"共 {len(view.mistakes)} 道错题", name="宋体", size=11)

    # 错题
    p = doc.add_paragraph()
    add_text(p, "一、错题记录", name="黑体", size=13, bold=True)
    if not view.mistakes:
        p = doc.add_paragraph()
        add_text(p, "暂无错题。", name="宋体", size=11, italic=True)

    for m in view.mistakes:
        p = doc.add_paragraph()
        r = p.add_run(f"{m.number}. 题目 #{m.question_id}")
        style_run(r, name=Q_FONT, size=Q_SIZE, bold=True)

        created = m.created_at.strftime("%Y-%m-%d") if m.created_at else "—"
        p = doc.add_paragraph()
        add_text(p, f"掌握程度：{MASTERY_LABELS.get(m.mastery, '—')}　记录于 {created}",
                 name="楷体", size=10, italic=True)

        p = doc.add_paragraph()
        r = p.add_run("题干：")
        style_run(r, name=Q_FONT, size=Q_SIZE, bold=True)
        add_text(p, m.stem or "（无）", name=Q_FONT, size=Q_SIZE)

        if include_images and m.images:
            add_images(m.images)

        if m.answer:
            p = doc.add_paragraph()
            r = p.add_run("参考答案：")
            style_run(r, name=Q_FONT, size=Q_SIZE, bold=True)
            add_text(p, m.answer, name=Q_FONT, size=Q_SIZE)

        if m.wrong_answer:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            r = p.add_run("学生错答：")
            style_run(r, name=Q_FONT, size=Q_SIZE, bold=True)
            add_text(p, m.wrong_answer, name=Q_FONT, size=Q_SIZE)

        if m.error_reason:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            r = p.add_run("错因分析：")
            style_run(r, name=Q_FONT, size=Q_SIZE, bold=True)
            add_text(p, m.error_reason, name=Q_FONT, size=Q_SIZE)

    # 学习图片
    if include_images and view.loose_images:
        p = doc.add_paragraph()
        add_text(p, "二、学习图片", name="黑体", size=13, bold=True)
        for i, img in enumerate(view.loose_images, start=1):
            if img.caption:
                p = doc.add_paragraph()
                add_text(p, f"{i}. {img.caption}", name="宋体", size=11, bold=True)
            add_images([img.path])

    doc.save(str(filepath))