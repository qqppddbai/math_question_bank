# -*- coding: utf-8 -*-
"""自测用测试数据：在沙箱数据目录里建库并造 3 道带图的题目。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # 项目根目录（tools/verify/checks → 项目根）
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from src.config import DATA_DIR, IMAGES_DIR  # noqa: E402
from src.database import init_db  # noqa: E402
from src.services import question_service as qs  # noqa: E402
from src.utils import file_utils  # noqa: E402


def make_png(name: str, color) -> str:
    path = IMAGES_DIR / name
    Image.new("RGB", (60, 40), color).save(path)
    # 相对 data/ 的路径（和 file_utils.save_uploaded_image 的返回格式一致）
    return path.relative_to(DATA_DIR).as_posix()


def main():
    init_db()

    stem_img = make_png("stem_only.png", (200, 40, 40))
    analysis_img = make_png("analysis_only.png", (40, 120, 200))
    both_stem = make_png("both_stem.png", (30, 160, 60))
    both_analysis = make_png("both_analysis.png", (240, 180, 20))

    qs.create_question({
        "qtype": "解答题", "grade": "高一", "chapter": "函数", "difficulty": 3,
        "stem": "题干一：只有题干配图 $x^2$", "answer": "答案一", "analysis": "解析一",
        "knowledge": "函数", "tags": "测试", "source": "自测",
        "options_list": [], "image_list": [stem_img],
    })
    qs.create_question({
        "qtype": "解答题", "grade": "高二", "chapter": "导数", "difficulty": 2,
        "stem": "题干二：只有解析配图", "answer": "答案二", "analysis": "解析二",
        "knowledge": "导数", "tags": "测试", "source": "自测",
        "options_list": [], "image_list": [f"analysis:{analysis_img}"],
    })
    qs.create_question({
        "qtype": "解答题", "grade": "高三", "chapter": "解析几何", "difficulty": 4,
        "stem": "题干三：两组图都有", "answer": "答案三", "analysis": "解析三",
        "knowledge": "圆锥曲线", "tags": "测试", "source": "自测",
        "options_list": [], "image_list": [both_stem, f"analysis:{both_analysis}"],
    })

    rows = qs.list_questions()
    print("DB:", DATA_DIR)
    for q in rows:
        stem_imgs, ana_imgs = file_utils.split_images(q.image_list)
        print(f"  #{q.id} {q.stem}  stem_imgs={stem_imgs} analysis_imgs={ana_imgs}")
    print("ids in list order:", [q.id for q in rows])


if __name__ == "__main__":
    main()
