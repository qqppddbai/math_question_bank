# -*- coding: utf-8 -*-
"""公式可渲染性检查（KaTeX 兼容性体检）。

为什么需要它
------------
界面上的公式全部由 Streamlit 内置的 KaTeX 渲染（rehype-katex，`throwOnError: true`）。
KaTeX 解析失败的公式会被渲染成 ``<span class="katex-error">``，在页面上就是一片
**红字**，公式本身完全看不到。两个最典型的例子：

- 公式编辑器 / 转换工具导出的 ``\\begin{array}{*{35}{l}}`` —— KaTeX 不支持
  ``*{n}{列}`` 这种重复列写法，直接报 ``Unknown column alignment: *``；
- 表格单元格里又写了一个 ``$``（如 ``$/{\\rm m}$``）—— ``$$...$$`` 内部已经是
  数学模式，KaTeX 报 ``Can't use function '$' in math mode``。

导入时如果不检查，这类公式会静悄悄地进库，等老师翻到那道题才发现。
本模块在**入库前**把它们找出来，并用中文说清楚哪里错了、怎么改。

设计约定
--------
- **只提醒，不阻断**：公式坏了题目本身还能用，是否导入由老师决定；
- **宁可少报，不可误报**：判断不了的写法一律不报，免得天天弹无用警告；
  命令名是否合法直接查 :mod:`src.utils.katex_commands`（从 KaTeX 源码抽取并逐条核验过）。

公开接口
--------
- :func:`check_text`   —— 检查一段文本（题干 / 答案 / 解析都行），返回问题列表；
- :func:`check_fields` —— 一次检查多个字段，自动带上字段名；
- :func:`fix_text`     —— 自动修复能确定修好的部分（目前只有数组列格式）。
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from src.utils.katex_commands import is_known_command

# ============================================================
# 一、KaTeX 的能力边界
#    （下面两张表是拿真实 KaTeX 0.16.47 逐个 \begin{}\end{} 试出来的）
# ============================================================
#: 行内公式 $...$ 和行间公式 $$...$$ 里都能用的环境
ENVIRONMENTS_INLINE_OK = frozenset({
    "array", "darray", "matrix", "pmatrix", "bmatrix", "Bmatrix",
    "vmatrix", "Vmatrix", "smallmatrix",
    "matrix*", "pmatrix*", "bmatrix*", "Bmatrix*", "vmatrix*", "Vmatrix*",
    "cases", "dcases", "rcases", "subarray", "aligned", "alignedat", "gathered",
})

#: 只能写在 $$...$$ 里的环境（写在 $...$ 里 KaTeX 会报
#: “{align} can be used only in display mode”）
ENVIRONMENTS_DISPLAY_ONLY = frozenset({
    "split", "align", "align*", "alignat", "alignat*",
    "gather", "gather*", "equation", "equation*", "CD",
})

KATEX_ENVIRONMENTS = ENVIRONMENTS_INLINE_OK | ENVIRONMENTS_DISPLAY_ONLY

#: 这些环境名后面的第一个 {...} 是「列格式」，KaTeX 只认 l / c / r / | / :
_COLUMN_SPEC_ENVIRONMENTS = ("array", "darray", "subarray")
_COLUMN_SPEC_ALLOWED = set("lcr|:")

#: 列格式修复时，*{n}{x} 最多展开多少个 x（防止 n 写错成天文数字）
_MAX_COLUMN_REPEAT = 60

#: KaTeX 不认识、但很常见、且能一句话说清怎么改的命令
_COMMAND_HINTS = {
    "\\mbox": "用 \\text{...} 代替",
    "\\hbox": "用 \\text{...} 代替",
    "\\label": "题库里不需要交叉引用，直接删掉",
    "\\ref": "题库里不需要交叉引用，直接删掉",
    "\\eqref": "题库里不需要交叉引用，直接删掉",
    "\\nonumber": "直接删掉即可",
    "\\cline": "用 \\hline 代替",
    "\\multicolumn": "KaTeX 不支持，可把合并的单元格拆开写",
    "\\documentclass": "整段 LaTeX 文档外壳要删掉，只保留公式本体",
    "\\usepackage": "整段 LaTeX 文档外壳要删掉，只保留公式本体",
    "\\qty": "用 \\left( ... \\right) 代替",
    "\\dv": "用 \\frac{\\mathrm{d}}{\\mathrm{d}x} 代替",
    "\\pdv": "用 \\frac{\\partial}{\\partial x} 代替",
    "\\abs": "用 \\left| ... \\right| 代替",
    "\\ce": "化学式要用 \\text{...} 包起来",
}

#: 一段文本最多报几条，避免刷屏
_MAX_ISSUES = 6

# ------------------------------------------------------------
# 返回结构
# ------------------------------------------------------------
@dataclass(frozen=True)
class LatexIssue:
    """一条公式问题。"""

    level: str            # "error"：公式肯定渲染成红字；"warn"：不会报错，但多半不是想要的效果
    message: str          # 中文说明（可直接展示给老师）
    snippet: str = ""     # 出问题的片段（截断过）
    fixable: bool = False # 能否用 fix_text() 自动修好

    @property
    def is_error(self) -> bool:
        return self.level == "error"


# ============================================================
# 二、把文本切成「公式段」
#    Streamlit 用的 micromark-extension-math 规则：
#    - $...$      行内公式，内容可以跨行，但不能跨空行（空行会断段）
#    - $$...$$    行间公式，同样按 $ 串长度配对
#    - 开头的 $ 串和结尾的 $ 串「长度必须相同」才算配对
#    - \$ 是转义，不算分隔符
# ============================================================
_DOLLAR_RUN = re.compile(r"\$+")
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
_ESCAPED_FENCE = re.compile(r"(?<!\\)\\[\(\[]|(?<!\\)\\[\)\]]")


@dataclass(frozen=True)
class _Segment:
    start: int
    end: int
    delimiters: int       # 1 = 行内，>=2 = 行间

    @property
    def display(self) -> bool:
        return self.delimiters >= 2


def _is_escaped(text: str, idx: int) -> bool:
    """idx 处的字符前面是不是奇数个反斜杠（是的话就是转义，不是分隔符）。"""
    n = 0
    i = idx - 1
    while i >= 0 and text[i] == "\\":
        n += 1
        i -= 1
    return n % 2 == 1


def _split_math(text: str) -> Tuple[List[_Segment], List[int]]:
    """返回 (公式段列表, 没配对的 $ 位置列表)。"""
    runs = [(m.start(), m.end() - m.start())
            for m in _DOLLAR_RUN.finditer(text)
            if not _is_escaped(text, m.start())]
    if not runs:
        return [], []

    # 空行分段：行内公式不允许跨空行
    boundaries = [m.end() for m in _BLANK_LINE.finditer(text)]

    def para(pos: int) -> int:
        return bisect_right(boundaries, pos)

    segments: List[_Segment] = []
    unpaired: List[int] = []
    used = [False] * len(runs)

    for i, (pos, width) in enumerate(runs):
        if used[i]:
            continue
        home = para(pos)
        j = i + 1
        match = None
        while j < len(runs):
            jpos, jwidth = runs[j]
            if width == 1 and para(jpos) != home:
                break                      # 跨了空行，配不上（空行会截断段落）
            if jwidth == width:
                match = j
                break
            j += 1
        if match is not None:
            segments.append(_Segment(runs[i][0] + width, runs[match][0], width))
            for k in range(i, match + 1):
                used[k] = True
        else:
            unpaired.append(pos)

    return segments, unpaired


def _line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _clip(s: str, limit: int = 60) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= limit else s[:limit] + "…"


# ============================================================
# 三、数组列格式：找出问题并给出可用的改法
# ============================================================
def _read_group(text: str, idx: int):
    """text[idx] 必须是 '{'。返回 (组内容, 右括号之后的下标)，不匹配则 None。"""
    if idx >= len(text) or text[idx] != "{":
        return None
    depth = 0
    for i in range(idx, len(text)):
        ch = text[i]
        if ch == "\\":                  # \{ \} 不参与配对
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[idx + 1:i], i + 1
    return None


def _fix_column_spec(spec: str) -> Tuple[str, int]:
    """把 KaTeX 不认的列格式改写成它认的写法，返回 (新列格式, 改动处数)。

    改写规则（都是 LaTeX 里的等价写法，只是 KaTeX 不实现这些简写）：
    - ``*{n}{x}``  -> ``x`` 重复 n 次（这是标准 LaTeX 语义）
    - ``p{宽}`` / ``m{宽}`` / ``b{宽}`` -> ``l``（KaTeX 没有按宽度排的列）
    - ``@{...}`` / ``!{...}`` -> 去掉（KaTeX 不支持列间自定义间距）
    """
    out: List[str] = []
    changed = 0
    i = 0
    while i < len(spec):
        ch = spec[i]

        def group_after(k: int):
            while k < len(spec) and spec[k].isspace():
                k += 1
            got = _read_group(spec, k)
            return got

        if ch == "*":
            g1 = group_after(i + 1)
            g2 = group_after(g1[1]) if g1 else None
            if g1 and g2:
                try:
                    n = int(g1[0].strip())
                except ValueError:
                    n = 0
                out.append(g2[0] * max(0, min(n, _MAX_COLUMN_REPEAT)))
                changed += 1
                i = g2[1]
                continue
        elif ch in "pmb":
            g = group_after(i + 1)
            if g:
                out.append("l")
                changed += 1
                i = g[1]
                continue
        elif ch in "@!":
            g = group_after(i + 1)
            if g:
                changed += 1
                i = g[1]
                continue

        out.append(ch)
        i += 1

    return "".join(out), changed


def _begin_column_specs(text: str):
    """找出每个 array/darray/subarray 后面的列格式，返回 [(位置, 环境名, 列格式)]。"""
    found = []
    for m in re.finditer(r"\\begin\s*\{\s*([A-Za-z]+)\s*\}", text):
        env = m.group(1)
        if env not in _COLUMN_SPEC_ENVIRONMENTS:
            continue
        got = _read_group(text, m.end())
        if got is None:
            continue
        found.append((m.start(), env, got[0]))
    return found


# ============================================================
# 四、单段公式的检查
# ============================================================
_ENV_TOKEN = re.compile(r"\\(begin|end)\s*\{\s*([^{}]*?)\s*\}")
_CMD_TOKEN = re.compile(r"\\[A-Za-z]+")
_LEFT = re.compile(r"\\left(?![A-Za-z])")
_RIGHT = re.compile(r"\\right(?![A-Za-z])")
_SUBSUP = re.compile(r"(?<!\\)([\^_])")
_TAG = re.compile(r"\\tag(?![A-Za-z])")


def _check_environment(tokens: Sequence[Tuple[str, str]], display: bool,
                       issues: List[LatexIssue]) -> None:
    stack: List[str] = []
    for kind, name in tokens:
        if kind == "begin":
            if name not in KATEX_ENVIRONMENTS:
                hint = ""
                if name.endswith("*") and name[:-1] in KATEX_ENVIRONMENTS:
                    hint = f"（KaTeX 支持不带星号的 {name[:-1]}）"
                issues.append(LatexIssue(
                    "error",
                    f"KaTeX 不认识环境 “{name}”，公式会渲染成红字{hint}",
                    f"\\begin{{{name}}}",
                ))
            elif name in ENVIRONMENTS_DISPLAY_ONLY and not display:
                issues.append(LatexIssue(
                    "error",
                    f"环境 “{name}” 只能写在 $$...$$ 之间，"
                    f"写在 $...$ 里 KaTeX 会报错，公式会渲染成红字",
                    f"\\begin{{{name}}}",
                ))
            stack.append(name)
        else:
            if not stack:
                issues.append(LatexIssue(
                    "error", f"多了一个 \\end{{{name}}}，没有对应的 \\begin",
                    f"\\end{{{name}}}",
                ))
            elif stack[-1] != name:
                issues.append(LatexIssue(
                    "error",
                    f"\\begin{{{stack[-1]}}} 与 \\end{{{name}}} 不匹配，公式会渲染成红字",
                    f"\\end{{{name}}}",
                ))
                stack.pop()
            else:
                stack.pop()
    for name in stack:
        issues.append(LatexIssue(
            "error", f"\\begin{{{name}}} 没有对应的 \\end{{{name}}}，公式会渲染成红字",
            f"\\begin{{{name}}}",
        ))


def _check_column_specs(latex: str, issues: List[LatexIssue]) -> None:
    for pos, env, spec in _begin_column_specs(latex):
        fixed, changed = _fix_column_spec(spec)
        head = f"\\begin{{{env}}}{{{_clip(spec, 40)}}}"

        if changed:
            if "*" in spec:
                reason = "KaTeX 不支持 “*{个数}{列}” 这种重复列写法"
            elif any(c in spec for c in "pmb"):
                reason = "KaTeX 不支持 “p{宽度}” 这类按宽度排版的列"
            else:
                reason = "KaTeX 不支持列格式里的 @{...} / !{...} 间距写法"
            if len(fixed) <= 30:
                tail = f"。应改成 \\begin{{{env}}}{{{fixed}}}"
            else:
                tail = "。点下面的「🔧 自动修复公式」可以换成 KaTeX 认识的等价写法"
            issues.append(LatexIssue(
                "error",
                f"{reason}，公式会渲染成红字{tail}",
                head,
                fixable=True,
            ))
            continue

        bad = sorted({c for c in fixed if c not in _COLUMN_SPEC_ALLOWED and not c.isspace()})
        if bad:
            issues.append(LatexIssue(
                "error",
                f"列格式里出现了 KaTeX 不认识的字符 “{''.join(bad)}”"
                f"（只支持 l / c / r 和 | :），公式会渲染成红字",
                head,
            ))


def _check_commands(latex: str, issues: List[LatexIssue]) -> None:
    seen = set()
    for m in _CMD_TOKEN.finditer(latex):
        if m.start() > 0 and latex[m.start() - 1] == "\\":
            continue                      # 属于 \\ 换行的一部分
        name = m.group(0)
        if is_known_command(name) or name in seen:
            continue
        seen.add(name)
        hint = _COMMAND_HINTS.get(name, "")
        issues.append(LatexIssue(
            "error",
            f"KaTeX 不认识命令 “{name}”，公式会渲染成红字。"
            + (f"{hint}。" if hint else "可对照 KaTeX 支持列表换一个等价写法。"),
            name,
        ))


def _check_braces(latex: str, issues: List[LatexIssue]) -> None:
    depth = 0
    i = 0
    while i < len(latex):
        ch = latex[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                depth = 0
        i += 1
    if depth:
        issues.append(LatexIssue(
            "error",
            f"花括号不配对：多了 {depth} 个 “{{”，公式会渲染成红字",
        ))


def _check_left_right(latex: str, issues: List[LatexIssue]) -> None:
    n_left = len(_LEFT.findall(latex))
    n_right = len(_RIGHT.findall(latex))
    if n_left != n_right:
        issues.append(LatexIssue(
            "error",
            f"\\left 与 \\right 数量不一样（{n_left} 个 / {n_right} 个），公式会渲染成红字",
        ))


def _check_subsup(latex: str, issues: List[LatexIssue]) -> None:
    """^ 和 _ 后面必须跟一个 token。KaTeX 会跳过空格，所以 x^ 2 是合法的。"""
    for m in _SUBSUP.finditer(latex):
        rest = latex[m.end():]
        stripped = rest.lstrip()
        # 合法的后续：{、字母数字、(、-、\命令、* 等；
        # 不合法的后续：到底了、}、&、$、双反斜杠（换行）、另一个 ^ 或 _
        bad = (stripped[:1] in ("", "}", "&", "$")
               or stripped.startswith("\\\\")
               or stripped[:1] in ("^", "_"))
        if bad:
            ch = m.group(1)
            issues.append(LatexIssue(
                "error",
                f"“{ch}” 后面缺少内容（比如 x^2 写成了 x^），公式会渲染成红字",
            ))
            return


def _check_nested_dollar(latex: str, issues: List[LatexIssue]) -> None:
    """公式内部不能再出现 `$`。

    表格最常见的踩坑：单元格里又写了 ``$/{\\rm m}$``。``$$...$$`` / ``$...$``
    内部**已经是数学模式**，再写一个 `$` 会直接报
    ``Can't use function '$' in math mode``，整张表变红字。
    真要显示美元符号，写 ``\\$``。
    """
    for i, ch in enumerate(latex):
        if ch != "$":
            continue
        n_back = 0
        j = i - 1
        while j >= 0 and latex[j] == "\\":
            n_back += 1
            j -= 1
        if n_back % 2 == 0:          # 奇数个反斜杠 = \$ 转义，是合法的
            issues.append(LatexIssue(
                "error",
                "公式里不能再写 “$”：$...$ / $$...$$ 内部已经是数学模式，"
                "再写一个 $ 会报 “Can't use function '$' in math mode”，"
                "整段公式会渲染成红字。单元格里的单位、正负号直接写就行"
                "（如 /{\\rm m}、\\sim）；确实要显示美元符号请写 \\$。",
                "$",
            ))
            return


def _check_math(latex: str, display: bool) -> List[LatexIssue]:
    issues: List[LatexIssue] = []
    _check_environment(_ENV_TOKEN.findall(latex), display, issues)
    _check_nested_dollar(latex, issues)
    _check_column_specs(latex, issues)
    _check_commands(latex, issues)
    _check_braces(latex, issues)
    _check_left_right(latex, issues)
    _check_subsup(latex, issues)
    if not display and _TAG.search(latex):
        issues.append(LatexIssue(
            "error",
            "\\tag 只能用在 $$...$$ 的公式里，写在 $...$ 里 KaTeX 会报错",
            "\\tag",
        ))
    return issues


# ============================================================
# 五、对外接口
# ============================================================
def check_text(text: str) -> List[LatexIssue]:
    """检查一段文本里所有公式能不能被 KaTeX 渲染。

    返回问题列表；没问题就返回空列表。同一类问题只报一次，总数最多 6 条。
    """
    if not text or "$" not in text and not _ESCAPED_FENCE.search(text):
        return []

    raw = str(text)
    issues: List[LatexIssue] = []

    # 1) \( \) \[ \] 这种写法 Streamlit 不认
    for m in _ESCAPED_FENCE.finditer(raw):
        issues.append(LatexIssue(
            "error",
            f"“{m.group(0)}” 这种定界符 Streamlit 不认，不会被渲染成公式；"
            f"请改用 $...$（行内）或 $$...$$（独占一行）",
            m.group(0),
        ))
        break

    # 2) $ 配对
    segments, unpaired = _split_math(raw)
    for pos in unpaired[:2]:
        issues.append(LatexIssue(
            "warn",
            f"第 {_line_no(raw, pos)} 行的 “$” 没有找到配对的 “$”，"
            f"这段内容不会被当成公式；如果只是想显示美元符号，请写成 \\$",
        ))

    # 3) 逐段做 KaTeX 兼容性检查
    for seg in segments:
        issues.extend(_check_math(raw[seg.start:seg.end], seg.display))

    # 4) 去重 + 截断
    deduped: List[LatexIssue] = []
    seen = set()
    for it in issues:
        key = (it.level, it.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    if len(deduped) > _MAX_ISSUES:
        rest = len(deduped) - _MAX_ISSUES
        deduped = deduped[:_MAX_ISSUES] + [
            LatexIssue("warn", f"……另有 {rest} 处公式问题，建议整体检查一遍")
        ]
    return deduped


def check_fields(fields: Dict[str, str]) -> List[Tuple[str, LatexIssue]]:
    """一次检查多个字段，返回 [(字段名, 问题), ...]。"""
    out: List[Tuple[str, LatexIssue]] = []
    for label, value in fields.items():
        if not value:
            continue
        for issue in check_text(value):
            out.append((label, issue))
    return out


def fix_text(text: str) -> Tuple[str, int]:
    """自动修复能确定修好的部分，返回 (新文本, 修复处数)。

    目前只会修 ``\\begin{array}{*{35}{l}}`` 这类 KaTeX 不支持的列格式，
    改法是标准 LaTeX 的等价写法，不会动公式的其它内容。
    """
    if not text:
        return text or "", 0

    raw = str(text)
    pieces: List[str] = []
    cursor = 0
    total = 0

    for m in re.finditer(r"\\begin\s*\{\s*([A-Za-z]+)\s*\}", raw):
        env = m.group(1)
        if env not in _COLUMN_SPEC_ENVIRONMENTS:
            continue
        got = _read_group(raw, m.end())
        if got is None:
            continue
        spec, after = got
        fixed, changed = _fix_column_spec(spec)
        if not changed:
            continue
        pieces.append(raw[cursor:m.end()])
        pieces.append("{" + fixed + "}")
        cursor = after
        total += changed

    if not total:
        return raw, 0
    pieces.append(raw[cursor:])
    return "".join(pieces), total


__all__ = [
    "LatexIssue", "check_text", "check_fields", "fix_text",
    "KATEX_ENVIRONMENTS", "ENVIRONMENTS_DISPLAY_ONLY", "ENVIRONMENTS_INLINE_OK",
]
