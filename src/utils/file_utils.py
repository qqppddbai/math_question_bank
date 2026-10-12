# -*- coding: utf-8 -*-
"""图片保存与路径处理。"""
import os
import subprocess
import sys
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


# ============================================================
# 题目配图的归属：题干图 / 解析图
# ------------------------------------------------------------
# 存储格式沿用 Question.image_list（一个字符串数组），约定：
#   - 普通路径            → 题干配图
#   - ANALYSIS_IMG_PREFIX 开头的路径 → 解析配图
# 之所以用前缀而不是改表结构，是为了让**旧数据零迁移**：
# 库里已有的图片没有任何前缀，读出来仍然算题干配图，显示效果和以前完全一样。
# 图片文件名是 uuid4 十六进制 + 扩展名（见 save_uploaded_image），不可能带冒号，
# 所以这个前缀不会和真实文件名冲突。
# ============================================================
ANALYSIS_IMG_PREFIX = "analysis:"


def split_images(image_list) -> tuple[list[str], list[str]]:
    """把一个图片数组拆成 (题干配图, 解析配图)。"""
    stem, analysis = [], []
    for rel in (image_list or []):
        rel = (rel or "").strip()
        if not rel:
            continue
        if rel.startswith(ANALYSIS_IMG_PREFIX):
            analysis.append(rel[len(ANALYSIS_IMG_PREFIX):])
        else:
            stem.append(rel)
    return stem, analysis


def join_images(stem_images, analysis_images) -> list[str]:
    """题干图 + 解析图 → 待入库的图片数组。"""
    out = [r for r in (stem_images or []) if r]
    out += [ANALYSIS_IMG_PREFIX + r for r in (analysis_images or []) if r]
    return out


def real_image_path(rel_path: str) -> str:
    """去掉归属前缀，得到真实的相对路径（给 abs_path 用）。"""
    if rel_path and rel_path.startswith(ANALYSIS_IMG_PREFIX):
        return rel_path[len(ANALYSIS_IMG_PREFIX):]
    return rel_path


def delete_file_silently(rel_path: str) -> None:
    """删除 data/ 下的文件；文件不存在或出错时静默忽略。"""
    try:
        p = abs_path(rel_path)
        if p.is_file():
            p.unlink()
    except OSError:
        pass


def clear_dir_silently(dir_path) -> None:
    """删掉一个目录（连同内容）；不存在或出错时静默忽略。

    用于清理「批量导入」草稿图片的暂存目录：那里面的文件还没被任何题目
    引用，取消导入时应当整个丢掉。
    """
    import shutil
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except OSError:
        pass


def upload_fingerprint(uploaded_file) -> str:
    """给上传的图片算一个内容指纹（用于去重）。

    同一张图重复写进暂存目录、进而在题目里被引用成两份，是很难看出来
    又很烦人的一类 bug。Streamlit 的上传组件在不同版本、不同重跑时机下
    是否把已处理的文件留在 state 里并不一致，所以这里不依赖任何时机假设：
    内容一样就认为是同一张图，重复处理天然安全。
    """
    import hashlib
    try:
        data = uploaded_file.getbuffer()
    except Exception:                       # noqa: BLE001 —— 拿不到内容就退化成按文件名 + 大小
        return f"name:{getattr(uploaded_file, 'name', '')}:{getattr(uploaded_file, 'size', '')}"
    return hashlib.md5(bytes(data)).hexdigest()


def open_file_location(path) -> bool:
    """在系统文件管理器里打开 `path` 所在目录，并选中该文件。

    只对本机运行有意义 —— 这个应用就是老师在自己电脑上跑的，
    所以「打开目录」打开的就是老师自己的文件夹。
    文件不存在、或系统不支持时返回 False，调用方负责提示。
    """
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return False
        target = target.resolve()
    except OSError:
        return False

    try:
        if os.name == "nt":
            # explorer 的 /select 语法：/select, 必须紧跟路径，中间不能有空格。
            # 另外 explorer 正常结束也会返回 1，所以不能拿 returncode 判断成败。
            subprocess.Popen(f'explorer /select,"{target}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent)])
        return True
    except Exception:
        pass

    # 兜底：退而求其次，直接打开父目录
    try:
        if os.name == "nt":
            os.startfile(str(target.parent))  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target.parent)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent)])
        return True
    except Exception:
        return False


__all__ = [
    "save_uploaded_image", "abs_path", "delete_file_silently",
    "clear_dir_silently", "upload_fingerprint",
    "open_file_location",
    "split_images", "join_images", "real_image_path", "ANALYSIS_IMG_PREFIX",
    "ALLOWED_IMAGE_EXTS", "MAX_IMAGE_MB", "STUDENT_FILES_DIR",
]