# -*- coding: utf-8 -*-
"""备份与恢复服务。

备份：
- 题库 JSON：只含 questions 表，格式与第 4 步导入完全兼容
- 整库 ZIP：包含全部表 + 图片文件，用于灾难恢复

恢复：
- 上传 ZIP 后解压到 data/pending_restore/，由用户手动替换（避免覆盖运行时数据库）
- 提供 apply_restore.bat / apply_restore.sh 一键替换脚本
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select

from src.config import (BACKUP_DIR, DATA_DIR, IMAGES_DIR, STUDENT_FILES_DIR)
from src.database import session_scope
from src.models import (Paper, PaperItem, Question, Student, StudentFile,
                        StudentMistake)

PENDING_DIR = DATA_DIR / "pending_restore"


# ============================================================
# 导出：题库 JSON
# ============================================================
def export_questions_json() -> str:
    """导出所有题目为 JSON 字符串（格式与导入兼容）。"""
    with session_scope() as s:
        rows = s.scalars(
            select(Question).where(Question.is_deleted.is_(False))
            .order_by(Question.id.asc())
        ).all()
        payload = []
        for q in rows:
            # options 转回 "A. xxx\nB. yyy" 文本，方便再次导入
            opts_text = ""
            if q.options_list:
                lines = [f"{o.get('key','')}. {o.get('text','')}".strip()
                         for o in q.options_list if o.get("text")]
                opts_text = "\n".join(lines)
            payload.append({
                "grade": q.grade, "chapter": q.chapter,
                "knowledge": q.knowledge, "qtype": q.qtype,
                "difficulty": q.difficulty, "stem": q.stem,
                "options": opts_text, "answer": q.answer,
                "analysis": q.analysis, "source": q.source,
                "tags": q.tags,
            })
        return json.dumps(payload, ensure_ascii=False, indent=2)


# ============================================================
# 导出：整库 ZIP
# ============================================================
def _dump_all_tables() -> Dict[str, List[dict]]:
    with session_scope() as s:
        data = {}
        data["questions"] = [{
            "id": q.id, "grade": q.grade, "chapter": q.chapter,
            "knowledge": q.knowledge, "qtype": q.qtype, "difficulty": q.difficulty,
            "stem": q.stem, "options": q.options, "answer": q.answer,
            "analysis": q.analysis, "source": q.source, "tags": q.tags,
            "image_paths": q.image_paths, "stem_hash": q.stem_hash,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "updated_at": q.updated_at.isoformat() if q.updated_at else None,
            "is_deleted": q.is_deleted,
            "deleted_at": q.deleted_at.isoformat() if q.deleted_at else None,
        } for q in s.scalars(select(Question)).all()]

        data["papers"] = [{
            "id": p.id, "title": p.title, "subtitle": p.subtitle,
            "exam_minutes": p.exam_minutes, "total_score": p.total_score,
            "config": p.config,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "is_deleted": p.is_deleted,
            "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
        } for p in s.scalars(select(Paper)).all()]

        data["paper_items"] = [{
            "id": it.id, "paper_id": it.paper_id, "question_id": it.question_id,
            "section_title": it.section_title, "order_index": it.order_index,
            "score": it.score,
        } for it in s.scalars(select(PaperItem)).all()]

        data["students"] = [{
            "id": st.id, "name": st.name, "class_name": st.class_name,
            "grade": st.grade, "notes": st.notes,
            "created_at": st.created_at.isoformat() if st.created_at else None,
            "updated_at": st.updated_at.isoformat() if st.updated_at else None,
            "is_deleted": st.is_deleted,
            "deleted_at": st.deleted_at.isoformat() if st.deleted_at else None,
        } for st in s.scalars(select(Student)).all()]

        data["student_mistakes"] = [{
            "id": m.id, "student_id": m.student_id, "question_id": m.question_id,
            "snapshot_stem": m.snapshot_stem, "snapshot_answer": m.snapshot_answer,
            "wrong_answer": m.wrong_answer, "error_reason": m.error_reason,
            "mastery": m.mastery,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        } for m in s.scalars(select(StudentMistake)).all()]

        data["student_files"] = [{
            "id": f.id, "student_id": f.student_id, "mistake_id": f.mistake_id,
            "file_path": f.file_path, "file_type": f.file_type,
            "caption": f.caption,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        } for f in s.scalars(select(StudentFile)).all()]

    return data


def export_full_backup_zip() -> Path:
    """打包整库为 zip，返回文件路径。文件保存在 data/backups/。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"mathbank_backup_{timestamp}.zip"

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        # 数据表
        zf.writestr("data.json", json.dumps(_dump_all_tables(),
                                            ensure_ascii=False, indent=2))
        # 图片
        for d, prefix in [(IMAGES_DIR, "images"),
                          (STUDENT_FILES_DIR, "student_files")]:
            if not d.exists():
                continue
            for p in d.rglob("*"):
                if p.is_file():
                    arcname = f"{prefix}/{p.relative_to(d).as_posix()}"
                    zf.write(p, arcname)

        # 元信息
        zf.writestr("meta.json", json.dumps({
            "version": "0.1",
            "exported_at": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2))

    return target


# ============================================================
# 恢复
# ============================================================
def stage_restore_from_zip(uploaded_file) -> Dict:
    """把上传的 zip 解压到 data/pending_restore/，供用户手动替换。"""
    # 清空旧的 pending
    if PENDING_DIR.exists():
        for p in PENDING_DIR.rglob("*"):
            if p.is_file():
                p.unlink()
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    # 保存并解压
    tmp_zip = PENDING_DIR / "_upload.zip"
    tmp_zip.write_bytes(uploaded_file.getbuffer())

    # 安全检查：确保 zip 里没有路径穿越
    def _safe_extract(zf, dest: Path):
        dest = dest.resolve()
        for member in zf.namelist():
            target = (dest / member).resolve()
            if not str(target).startswith(str(dest)):
                raise ValueError(f"压缩包内含非法路径：{member}")
        zf.extractall(dest)

    with zipfile.ZipFile(tmp_zip) as zf:
        names = zf.namelist()
        if "data.json" not in names:
            raise ValueError("这不是有效的备份：缺少 data.json")
        _safe_extract(zf, PENDING_DIR)

    tmp_zip.unlink(missing_ok=True)

    # 统计
    with open(PENDING_DIR / "data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "dir": str(PENDING_DIR),
        "questions": len(data.get("questions", [])),
        "papers": len(data.get("papers", [])),
        "students": len(data.get("students", [])),
        "mistakes": len(data.get("student_mistakes", [])),
    }


def clear_pending_restore():
    if PENDING_DIR.exists():
        for p in PENDING_DIR.rglob("*"):
            if p.is_file():
                p.unlink()
        PENDING_DIR.rmdir()


# ============================================================
# 图片清理
# ============================================================
def find_orphan_images() -> List[Dict]:
    """扫描 data/images/ 找出未被任何题目引用的图片。"""
    with session_scope() as s:
        rows = s.scalars(select(Question.image_paths)).all()

    referenced = set()
    for raw in rows:
        if not raw:
            continue
        try:
            for rel in json.loads(raw):
                # 统一格式：images/xxxx.png
                if rel.startswith("images/"):
                    referenced.add(rel)
                elif "/" not in rel:
                    referenced.add(f"images/{rel}")
        except (ValueError, TypeError):
            pass

    orphans = []
    if IMAGES_DIR.exists():
        for p in IMAGES_DIR.rglob("*"):
            if not p.is_file():
                continue
            rel = f"images/{p.relative_to(IMAGES_DIR).as_posix()}"
            if rel not in referenced:
                orphans.append({
                    "rel_path": rel,
                    "abs_path": p,
                    "size_kb": round(p.stat().st_size / 1024, 1),
                })
    return orphans


def delete_orphan_images(paths: List[str]) -> int:
    """按相对路径列表删除孤儿图片。返回删除成功数量。"""
    deleted = 0
    for rel in paths:
        if not rel.startswith("images/"):
            continue
        p = IMAGES_DIR / rel[len("images/"):]
        try:
            if p.is_file():
                p.unlink()
                deleted += 1
        except OSError:
            pass
    return deleted