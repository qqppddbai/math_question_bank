# -*- coding: utf-8 -*-
"""选项文本与 JSON 结构之间的转换。

数据库里 options 统一存 [{"key": "A", "text": "..."}, ...] 的 JSON 字符串。
老师手动输入时可以提供 "A. xxx\nB. yyy" 这种纯文本，这里负责解析。
"""
import re
from typing import Iterable, List, Optional

from src.config import OPTION_KEYS

# 匹配行首选项标签：A. / A、 / A） / (A) / A）  A1. 等
_LABEL_RE = re.compile(
    r"^\s*[（(]?\s*([A-Fa-f])\s*[)）.、:：]?\s*(.*)$"
)


def parse_options_text(text: str) -> List[dict]:
    """把多行文本解析成选项列表。

    支持：
        A. xxx
        A、xxx
        （A）xxx
        A) xxx
        A xxx     ← 兜底：行首字母后跟空格
    如果无法识别任何标签，且文本非空，则按行依次填 A/B/C/D。
    """
    if not text or not text.strip():
        return []

    lines = [ln for ln in text.splitlines() if ln.strip()]
    options: List[dict] = []
    for ln in lines:
        m = _LABEL_RE.match(ln)
        if m and m.group(1).upper() in OPTION_KEYS:
            options.append({"key": m.group(1).upper(), "text": m.group(2).strip()})
        else:
            # 无标签，按出现顺序补齐
            idx = len(options)
            key = OPTION_KEYS[idx] if idx < len(OPTION_KEYS) else f"X{idx}"
            options.append({"key": key, "text": ln.strip()})

    return options


def normalize_options(options: Optional[Iterable]) -> List[dict]:
    """把任意来源的选项统一成 A~D 四个（缺的补空）。"""
    result = {k: "" for k in OPTION_KEYS}
    if options:
        for item in options:
            if isinstance(item, dict):
                k = str(item.get("key", "")).upper()
                t = str(item.get("text", ""))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                k, t = str(item[0]).upper(), str(item[1])
            else:
                continue
            if k in result:
                result[k] = t
    return [{"key": k, "text": result[k]} for k in OPTION_KEYS]


def options_to_text(options: Optional[Iterable]) -> str:
    """把选项列表转回 'A. xxx\\nB. yyy' 文本，方便老师编辑。"""
    lines = []
    for item in normalize_options(options):
        lines.append(f"{item['key']}. {item['text']}")
    return "\n".join(lines)