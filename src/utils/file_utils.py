# -*- coding: utf-8 -*-
"""图片保存与路径处理。"""
import uuid
from pathlib import Path

from src.config import DATA_DIR, IMAGES_DIR, STUDENT_FILES_DIR

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_IMAGE_MB = 5


def save_uploaded_image(uploaded_file, target_dir: Path = IMAGES_DIR) -> str:
    """保存 Streamlit 上传的图片，返回相对 DATA_DIR 的路径（posix 风格）。

    抛 ValueError 表示格式不支持或文件过大，调用方负责提示用户。
    """
    name = getattr(uploaded_file, "name", "image.png")
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError(f"不支持的图片格式：{ext}，请使用 png / jpg / webp / gif")

    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_IMAGE_MB * 1024 * 1024:
        raise ValueError(f"图片过大（>{MAX_IMAGE_MB}MB），请压缩后再上传")

    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    target = target_dir / filename
    with open(target, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return target.relative_to(DATA_DIR).as_posix()


def abs_path(rel_path: str) -> Path:
    """相对 data/ 的路径 → 绝对路径。"""
    return DATA_DIR / rel_path


def delete_file_silently(rel_path: str) -> None:
    """删除 data/ 下的文件；文件不存在或出错时静默忽略。"""
    try:
        p = abs_path(rel_path)
        if p.is_file():
            p.unlink()
    except OSError:
        pass


__all__ = [
    "save_uploaded_image", "abs_path", "delete_file_silently",
    "ALLOWED_IMAGE_EXTS", "MAX_IMAGE_MB", "STUDENT_FILES_DIR",
]