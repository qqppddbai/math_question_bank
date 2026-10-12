# -*- coding: utf-8 -*-
"""题目正文里的配图定位标记。

背景：题干 / 解析的文本和配图原本是分开渲染的两块（文字一整块、图片堆在文字后面），
没法把图片插到文字中间。这里引入一个轻量约定，把"图片放哪儿"写进文字本身：

    ![[img:1]]          第 1 张配图
    ![[img:2|300]]      第 2 张配图，宽度 300px

约定：
- 序号是**该字段内的序号**：题干里的 ![[img:N]] 指题干配图的第 N 张，
  解析里的指解析配图的第 N 张。这样你在题干里写的编号永远对应你上传的题干图。
- 一个标记只引用一张图，同一张可以重复引用。
- **完全没有标记时，图片一律排在文字后面** —— 与改动前的行为一模一样，
  所以旧题目不需要任何迁移，打开后显示效果不变。
- 一旦出现标记，就只显示被标记引用的图片（这样"把图放哪儿"是可预期的）；
  没被安置的图片不会消失，编辑器里会提示你它们的序号。

本模块只做纯文本解析，不依赖 Streamlit，方便单独测。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# 标记语法：
#   ![[img]]            不写序号 = 第 1 张（只有一张图时最省事）
#   ![[img:2]]          第 2 张
#   ![[img:2|300]]      第 2 张，宽度 300px
#   ![[img|300]]        第 1 张，宽度 300px
# 序号和宽度都可以省略，所以正则里两段都是可选的。
MARKER_RE = re.compile(
    r"!\[\[\s*img\s*(?::\s*(\d+)\s*)?(?:\|\s*(\d+)\s*)?\]\]"
)

# 不写序号时默认引用第几张
DEFAULT_IMAGE_NUMBER = 1


def marker_syntax(number: int = DEFAULT_IMAGE_NUMBER,
                  width: Optional[int] = None,
                  *, compact: bool = False) -> str:
    """生成标记文本，供编辑器里展示 / 复制。

    compact=True 且是第 1 张时输出最短写法 ![[img]]（只有一张图时用）。
    """
    if compact and number == DEFAULT_IMAGE_NUMBER and not width:
        return "![[img]]"
    if width:
        return f"![[img:{number}|{int(width)}]]"
    return f"![[img:{number}]]"


def normalize_size(size) -> Optional[int]:
    """把宽度的各种写法归一成 int 或 None。"""
    if size is None or size == "":
        return None
    try:
        value = int(size)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def find_markers(text: str) -> List[Tuple[int, int, int, Optional[int]]]:
    """在文本里找出所有标记。

    返回 [(匹配起点, 匹配终点, 序号, 宽度), ...]，按出现先后排列。
    没写序号时按第 1 张算。
    """
    found = []
    for m in MARKER_RE.finditer(text or ""):
        number = int(m.group(1)) if m.group(1) else DEFAULT_IMAGE_NUMBER
        found.append((m.start(), m.end(), number,
                      normalize_size(m.group(2))))
    return found


def markdown_to_blocks(text: str, images: List[str]) -> List[Dict]:
    """把「文本 + 图片列表」切成有序的块序列。

    返回 [{"type": "text", "text": ...}, {"type": "image", "path": ...,
    "number": n, "size": w}, ...]

    没有任何标记时，等价于「一段文字 + 末尾一串图片」（旧行为）。
    """
    text = text or ""
    images = list(images or [])
    markers = find_markers(text)

    if not markers:
        blocks: List[Dict] = []
        if text.strip():
            blocks.append({"type": "text", "text": text})
        for i, path in enumerate(images):
            blocks.append({"type": "image", "path": path, "number": i + 1,
                           "size": None})
        return blocks

    blocks = []
    cursor = 0
    for start, end, number, size in markers:
        head = text[cursor:start]
        if head.strip():
            blocks.append({"type": "text", "text": head})
        blocks.append({
            "type": "image",
            "path": images[number - 1] if 1 <= number <= len(images) else None,
            "number": number,
            "size": size,
        })
        cursor = end

    tail = text[cursor:]
    if tail.strip():
        blocks.append({"type": "text", "text": tail})
    return blocks


def placement_report(text: str, images: List[str]) -> Dict:
    """给编辑器用：哪些图已经安置、哪些还没、有没有写了不存在的序号。

    返回 {"has_marker": bool, "placed": [序号...], "unplaced": [序号...],
          "bad": [序号...]}
    """
    images = list(images or [])
    markers = find_markers(text)
    placed = sorted({n for _, _, n, _ in markers})
    return {
        "has_marker": bool(markers),
        "placed": [n for n in placed if 1 <= n <= len(images)],
        "unplaced": [n for n in range(1, len(images) + 1) if n not in placed],
        "bad": [n for n in placed if not (1 <= n <= len(images))],
    }


__all__ = [
    "MARKER_RE", "DEFAULT_IMAGE_NUMBER", "marker_syntax", "normalize_size",
    "find_markers", "markdown_to_blocks", "placement_report",
]
