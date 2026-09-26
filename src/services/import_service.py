# -*- coding: utf-8 -*-
"""批量导入服务：解析 JSON 数组、校验字段、查重、入库。

导入格式（与需求一致）：
[
  {
    "grade": "高三",
    "chapter": "导数",
    "knowledge": "不等式证明,极值点,分类讨论",
    "qtype": "解答题",
    "difficulty": 5,
    "stem": "...",
    "options": "",                # 选择题："A. xxx\nB. yyy\nC. zzz\nD. www"
    "answer": "...",
    "analysis": "...",
    "source": "2023年新课标全国Ⅱ卷",
    "tags": "高考真题,新高考II卷"
  },
  ...
]

字段全部可选，只要求 stem 非空、qtype 在允许集合内、difficulty ∈ 1~5。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config import CHOICE_TYPES, QTYPES
from src.database import session_scope
from src.models import Question
from src.utils.options_parser import parse_options_text


# ------------------------------------------------------------
# 校验结果
# ------------------------------------------------------------
@dataclass
class RowReport:
    """每行的校验结果。"""
    index: int                       # 在原数组中的下标（从 0 开始）
    ok: bool                         # 是否可以入库
    errors: List[str] = field(default_factory=list)   # 错误信息（中文）
    warnings: List[str] = field(default_factory=list) # 提醒但可入库
    is_duplicate: bool = False       # 是否与库内已有题目重复
    duplicate_ids: List[int] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)  # 规范化后的数据


@dataclass
class ParseResult:
    """整体解析结果。"""
    rows: List[RowReport] = field(default_factory=list)
    fatal_error: str = ""            # 整体错误（JSON 不合法等）

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.rows if r.ok)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.rows if not r.ok)

    @property
    def dup_count(self) -> int:
        return sum(1 for r in self.rows if r.ok and r.is_duplicate)


# ------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------
def _norm_stem_hash(stem: str) -> str:
    s = "".join((stem or "").split())
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _to_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _to_int(v: Any, default: int = 3) -> Optional[int]:
    if v is None or v == "":
        return default
    try:
        return int(float(v))  # 兼容 "5" 和 5.0
    except (TypeError, ValueError):
        return None


def _normalize_knowledge_or_tags(v: Any) -> str:
    """支持字符串 'a,b' 或列表 ['a','b']，统一成 'a,b'。"""
    if v is None:
        return ""
    if isinstance(v, list):
        items = [_to_str(x) for x in v]
    else:
        items = [_to_str(x) for x in _to_str(v).split(",")]
    return ",".join([x for x in items if x])


def _parse_options_field(raw: Any) -> List[dict]:
    """options 字段兼容三种形式：
    1) 空串 -> []
    2) 纯文本 "A. xxx\\nB. yyy" -> parse_options_text
    3) 已经是 [{'key':'A','text':'...'}] 结构（导出回灌场景）
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        # 导出回灌：直接规范结构
        out = []
        for item in raw:
            if isinstance(item, dict):
                out.append({"key": _to_str(item.get("key")), "text": _to_str(item.get("text"))})
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append({"key": _to_str(item[0]), "text": _to_str(item[1])})
        return out
    text = _to_str(raw)
    if not text:
        return []
    # 若包含换行或 "A." 之类前缀，走解析器；否则当作单选项
    return parse_options_text(text)


# ------------------------------------------------------------
# 核心校验
# ------------------------------------------------------------
def _validate_row(idx: int, raw: dict) -> RowReport:
    report = RowReport(index=idx, ok=True)

    if not isinstance(raw, dict):
        report.ok = False
        report.errors.append("该条不是 JSON 对象")
        return report

    # 题干
    stem = _to_str(raw.get("stem"))
    if not stem:
        report.ok = False
        report.errors.append("题干为空")

    # 题型
    qtype = _to_str(raw.get("qtype")) or "解答题"
    if qtype not in QTYPES:
        report.ok = False
        report.errors.append(f"题型 “{qtype}” 不在允许范围：{' / '.join(QTYPES)}")

    # 难度
    diff = _to_int(raw.get("difficulty"), default=3)
    if diff is None:
        report.ok = False
        report.errors.append("难度必须是 1~5 的整数")
        diff = 3
    else:
        diff = min(5, max(1, diff))

    # 选项
    options_list = _parse_options_field(raw.get("options"))
    if qtype in CHOICE_TYPES:
        non_empty = [o for o in options_list if o.get("text")]
        if len(non_empty) < 2:
            report.warnings.append("选择题但选项少于 2 个，请确认是否漏填")

    # 年级 / 章节（非必填，但给个默认）
    grade = _to_str(raw.get("grade"))
    chapter = _to_str(raw.get("chapter"))

    # 组装规范化数据
    data = {
        "grade": grade,
        "chapter": chapter,
        "knowledge": _normalize_knowledge_or_tags(raw.get("knowledge")),
        "qtype": qtype,
        "difficulty": diff,
        "stem": stem,
        "options_list": options_list,
        "answer": _to_str(raw.get("answer")),
        "analysis": _to_str(raw.get("analysis")),
        "source": _to_str(raw.get("source")),
        "tags": _normalize_knowledge_or_tags(raw.get("tags")),
        "image_list": [],
    }
    report.data = data

    # 查重（题干完全一致即判重）
    if stem:
        with session_scope() as s:
            from sqlalchemy import select
            ids = s.scalars(
                select(Question.id).where(
                    Question.stem_hash == _norm_stem_hash(stem),
                    Question.is_deleted.is_(False),
                )
            ).all()
            if ids:
                report.is_duplicate = True
                report.duplicate_ids = list(ids)

    return report


# ------------------------------------------------------------
# 对外接口
# ------------------------------------------------------------
def parse_json_text(text: str) -> ParseResult:
    """解析 JSON 文本并逐条校验，返回结构化报告。"""
    result = ParseResult()

    if not text or not text.strip():
        result.fatal_error = "内容为空，请粘贴 JSON 数组。"
        return result

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        result.fatal_error = (
            f"JSON 格式错误（第 {e.lineno} 行第 {e.colno} 列）：{e.msg}\n"
            f"提示：字符串里的双引号、反斜杠都要转义；LaTeX 里的 \\ 要写成 \\\\。"
        )
        return result

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        result.fatal_error = "顶层结构必须是 JSON 数组（[] 包裹），或单个 JSON 对象。"
        return result

    if not payload:
        result.fatal_error = "数组为空，没有可导入的题目。"
        return result

    for i, item in enumerate(payload):
        result.rows.append(_validate_row(i, item))

    return result


def commit_import(rows: List[RowReport], skip_duplicates: bool = True) -> Dict[str, int]:
    """把校验通过的题目写入数据库。

    参数：
        rows            —— parse_json_text 得到的报告行
        skip_duplicates —— True: 跳过与库内重复的题目（默认）
                           False: 照单全收（库里会多一份重复题）

    返回：{"inserted": n, "skipped_dup": n, "skipped_err": n}
    """
    inserted = skipped_dup = skipped_err = 0
    with session_scope() as s:
        for r in rows:
            if not r.ok:
                skipped_err += 1
                continue
            if skip_duplicates and r.is_duplicate:
                skipped_dup += 1
                continue

            d = r.data
            q = Question(
                grade=d["grade"], chapter=d["chapter"], knowledge=d["knowledge"],
                qtype=d["qtype"], difficulty=d["difficulty"],
                stem=d["stem"], answer=d["answer"], analysis=d["analysis"],
                source=d["source"], tags=d["tags"],
                stem_hash=_norm_stem_hash(d["stem"]),
            )
            q.options_list = d["options_list"]
            q.image_list = []
            s.add(q)
            inserted += 1

    return {"inserted": inserted, "skipped_dup": skipped_dup, "skipped_err": skipped_err}


__all__ = [
    "RowReport", "ParseResult",
    "parse_json_text", "commit_import",
]