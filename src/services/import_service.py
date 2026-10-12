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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import CHOICE_TYPES, DATA_DIR, IMAGES_DIR, QTYPES
from src.database import session_scope
from src.models import Question
from src.services.question_service import apply_question_fields
from src.utils import latex_check
from src.utils.latex_check import LatexIssue
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
    # 公式能不能被 KaTeX 渲染（渲染不了的页面上就是一片红字），[(字段名, 问题)]
    latex_issues: List[Tuple[str, LatexIssue]] = field(default_factory=list)
    # 草稿编辑时加的配图（已经由 promote_staged_images 转成正式路径）。
    # 普通 JSON 导入永远是空列表 —— 那种情况下图片只能到「题目管理」里去补。
    staged_images: List[str] = field(default_factory=list)
    # 这一条是不是「草稿页确认过」的。草稿页的图片是老师看完预览后明确留下的，
    # 所以覆盖时以草稿为准（哪怕草稿里一张图都没有 = 老师就是要清空）；
    # 而 JSON 导入里根本没有图片字段，覆盖时必须保留原题已有的配图。
    draft_images: bool = False

    @property
    def has_latex_issue(self) -> bool:
        return bool(self.latex_issues)

    @property
    def latex_error_count(self) -> int:
        """肯定渲染成红字的公式处数。"""
        return sum(1 for _, i in self.latex_issues if i.is_error)

    @property
    def latex_fixable_count(self) -> int:
        """能用自动修复改好的处数。"""
        return sum(1 for _, i in self.latex_issues if i.fixable)

    @property
    def overwrite_id(self) -> Optional[int]:
        """覆盖导入时会改写的题目 id（同题多条时取编号最小的那条）。"""
        return min(self.duplicate_ids) if self.duplicate_ids else None


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

    @property
    def latex_count(self) -> int:
        """公式有问题的条数（含只是提醒、不一定会变红字的）。"""
        return sum(1 for r in self.rows if r.ok and r.has_latex_issue)

    @property
    def latex_error_count(self) -> int:
        """公式肯定渲染成红字的条数。"""
        return sum(1 for r in self.rows if r.ok and r.latex_error_count)


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


def _norm_diff(v: Any) -> int:
    """难度统一成 1~5 的整数（编辑草稿时用）。"""
    d = _to_int(v, default=3)
    return 3 if d is None else min(5, max(1, d))


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


def _check_latex(data: Dict[str, Any]) -> List[Tuple[str, LatexIssue]]:
    """检查题干 / 选项 / 答案 / 解析里的公式能不能被 KaTeX 渲染。

    返回 [(字段名, 问题)]。判断逻辑在 src/utils/latex_check.py。
    """
    fields: Dict[str, str] = {
        "题干": data.get("stem", ""),
        "答案": data.get("answer", ""),
        "解析": data.get("analysis", ""),
    }
    for i, opt in enumerate(data.get("options_list") or []):
        if (opt.get("text") or "").strip():
            fields[f"选项 {opt.get('key') or i + 1}"] = opt["text"]
    return latex_check.check_fields(fields)


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

    # 公式体检：KaTeX 渲染不了的公式在页面上是一片红字，入库前先提醒
    # （只提醒、不阻断；老师可以点「自动修复公式」后再导入）
    report.latex_issues = _check_latex(data)

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


# ------------------------------------------------------------
# 草稿编辑后的重校验
# ------------------------------------------------------------
def revalidate_row(report: RowReport) -> RowReport:
    """老师在草稿里改完某一条后，重新校验这一条。

    改的是**题干内容**，所以两件事必须跟着重算：

    1. **查重**：原判定是按原始 JSON 的题干算的。题干一改，原来那套
       「与 #12 重复」的判断就失效了 —— 改过的题干可能和库里另一道题重复，
       也可能从此不再重复。不重算的话，覆盖模式会去改一道其实已经不相干的题。
    2. **公式体检**：改完的公式要重新检查，否则新写坏的公式会静悄悄地进库。

    就地改写 report（并返回它），保持 RowReport 的字段语义不变。
    """
    data = report.data
    stem = _to_str(data.get("stem"))
    report.errors = [e for e in report.errors if not e.startswith("题干为空")]
    if not stem:
        report.ok = False
        if "题干为空" not in report.errors:
            report.errors.append("题干为空")
    else:
        data["stem"] = stem

    data["difficulty"] = _norm_diff(data.get("difficulty"))
    report.latex_issues = _check_latex(data)

    report.is_duplicate = False
    report.duplicate_ids = []
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


#: 遇到与库内题干相同的题目时的处理方式
DUPLICATE_MODES = ("skip", "overwrite", "insert")

DUPLICATE_MODE_LABELS = {
    "skip": "跳过重复（推荐）",
    "overwrite": "覆盖题库里的原题",
    "insert": "照样新增一份（会产生重复题）",
}


# ------------------------------------------------------------
# 草稿图片：先暂存，确认入库时才转正
# ------------------------------------------------------------
# 老师是在「还没决定要不要导入」的时候上传配图的，此时把文件直接写进
# data/images/ 会留下没人引用的垃圾文件。所以草稿阶段的图片先落在
# data/images/_import_staging/<草稿序号>/ 里，点「确认入库」时才复制到
# data/images/ 正式目录，取消 / 重新解析 / 刷新丢弃草稿时就把暂存目录删掉。
#
# 之所以要真的落盘（而不是只留在内存里）：Streamlit 的 file_uploader 在
# 切换编辑对象或重跑之后不一定还拿得到原来那个文件对象，图片会莫名其妙
# 丢掉；老师也会在编辑到一半时刷新页面。落盘 + 定时清理是唯一稳妥的做法。
STAGING_DIR_NAME = "_import_staging"


def staging_dir() -> Path:
    """草稿图片的暂存根目录。"""
    return IMAGES_DIR / STAGING_DIR_NAME


def staging_subdir(token: str) -> Path:
    """某一份草稿专属的暂存子目录（token 用它在草稿列表里的下标）。"""
    return staging_dir() / str(token)


def clear_staging() -> None:
    """删掉整个暂存目录（重新解析 / 导入完成 / 清空内容时调用）。"""
    import shutil
    shutil.rmtree(staging_dir(), ignore_errors=True)


def cleanup_stale_staging(max_age_hours: int = 24) -> int:
    """清理超过指定时长还没转正的暂存目录，返回删掉的目录数。

    正常情况下用不着它：取消、重新解析、导入完成都会主动删。它是兜底 ——
    老师直接把浏览器关掉、或者程序被强杀时，暂存目录就留下来了。
    """
    import shutil
    import time

    root = staging_dir()
    if not root.is_dir():
        return 0
    deadline = time.time() - max_age_hours * 3600
    removed = 0
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < deadline:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


def promote_staged_images(rel_paths: List[str]) -> List[str]:
    """把草稿里的图片从暂存目录转到正式图片目录，返回转正后的路径。

    已经在正式目录里的图（覆盖导入时保留的原题配图）原样返回，
    所以对同一个列表重复调用是安全的。
    """
    import shutil

    out: List[str] = []
    for rel in rel_paths or []:
        rel = (rel or "").strip()
        if not rel:
            continue
        # 兼容带 "analysis:" 归属前缀的写法
        prefix = ""
        raw = rel
        if ":" in raw:
            head, _, tail = raw.partition(":")
            if head == "analysis":
                prefix, raw = "analysis:", tail
        if STAGING_DIR_NAME not in raw:
            out.append(rel)
            continue

        src = DATA_DIR / raw
        dst_rel = f"images/{src.name}"
        dst = DATA_DIR / dst_rel
        try:
            if src.is_file():
                IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copy2(src, dst)
                out.append(prefix + dst_rel)
        except OSError:
            # 转正失败就丢掉这张图，绝不让一条坏路径进库
            continue
    return out


def commit_import(rows: List[RowReport], on_duplicate: str = "skip",
                  *, skip_duplicates: Optional[bool] = None) -> Dict[str, int]:
    """把校验通过的题目写入数据库。

    参数：
        rows         —— parse_json_text 得到的报告行
        on_duplicate —— 遇到与库内重复的题目怎么办：
                        "skip"      跳过（默认）
                        "overwrite" 用导入的内容改写库内那道原题
                        "insert"    不管重复，照单新增一份
        skip_duplicates —— 旧参数，等价于 on_duplicate="skip"/"insert"，
                           仅为了不改动老调用方，新代码请用 on_duplicate。

    返回：{"inserted", "updated", "skipped_dup", "skipped_err", "extra_dup"}
        extra_dup —— 覆盖时，同一道题在库里有多份、本次只改了编号最小那份，
                     剩下的份数记在这里（原来的重复题不会被自动删掉）。
    """
    if skip_duplicates is not None:
        on_duplicate = "skip" if skip_duplicates else "insert"
    if on_duplicate not in DUPLICATE_MODES:
        raise ValueError(f"on_duplicate 只能是 {DUPLICATE_MODES}，收到 {on_duplicate!r}")

    inserted = updated = skipped_dup = skipped_err = extra_dup = 0
    with session_scope() as s:
        for r in rows:
            if not r.ok:
                skipped_err += 1
                continue

            if r.is_duplicate and on_duplicate != "insert":
                target = r.overwrite_id if on_duplicate == "overwrite" else None
                q = s.get(Question, target) if target else None
                if q is not None and not q.is_deleted:
                    # 覆盖：原地改写，题目 id 不变，所以试卷里的引用、
                    # 学生错题关联都不会断。
                    payload = dict(r.data)
                    images = payload.pop("image_list", None)
                    # 选项也按导入解析出来的原样写，跟「新增」保持完全一致。
                    # （apply_question_fields 里的 normalize_options 是"编辑器保存"
                    #   的语义：会压成 A~D 四项，对导入来说会凭空多出空选项。）
                    payload.pop("options_list", None)
                    apply_question_fields(q, payload)
                    q.options_list = r.data["options_list"]
                    # 图片：JSON 导入里没有图片字段，别把原题已有的配图清掉；
                    # 草稿页确认过的（draft_images）才以草稿为准。
                    if r.draft_images and images is not None:
                        q.image_list = list(images)
                    q.updated_at = datetime.now()
                    updated += 1
                    extra_dup += max(0, len(r.duplicate_ids) - 1)
                else:
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
            # 带图导入（草稿页里加的配图）；普通 JSON 导入这里是空的
            q.image_list = list(r.staged_images or d.get("image_list") or [])
            s.add(q)
            inserted += 1

    # 导入是直接建对象的，绕过了 question_service 的写接口，这里手动清查询缓存，
    # 否则导入完马上回题目列表页，看到的还是缓存里的旧列表。
    from src.services import data_cache
    data_cache.bump()

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped_dup": skipped_dup,
        "skipped_err": skipped_err,
        "extra_dup": extra_dup,
    }


__all__ = [
    "RowReport", "ParseResult", "DUPLICATE_MODES", "DUPLICATE_MODE_LABELS",
    "parse_json_text", "revalidate_row", "commit_import",
    "staging_dir", "staging_subdir", "clear_staging", "cleanup_stale_staging",
    "promote_staged_images",
]