# -*- coding: utf-8 -*-
"""临时冒烟：草稿编辑 + 配图暂存 + 入库。跑完即删。"""
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.config import IMAGES_DIR  # noqa: E402
from src.services import data_cache as dc  # noqa: E402
from src.services import import_service as imp  # noqa: E402
from src.services import question_service as qs  # noqa: E402

APP = str(ROOT / "app.py")
PAGE = "📥  批量导入"

def png(n: int) -> bytes:
    """造一张内容不同的小 png（内容不同才能验去重逻辑）。"""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (n, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def p(*a):
    print(*a, flush=True)


def main() -> int:
    p("DATA_DIR =", os.environ.get("MATHBANK_DATA_DIR"))
    body = json.dumps([
        {"grade": "高三", "chapter": "函数", "qtype": "解答题", "difficulty": 4,
         "stem": "草稿冒烟第一题 $x^2$", "answer": "A1", "analysis": "解析一",
         "knowledge": "函数", "tags": "冒烟"},
        {"grade": "高一", "chapter": "集合", "qtype": "单选题", "difficulty": 2,
         "stem": "草稿冒烟第二题", "options": "A. 甲\nB. 乙\nC. 丙\nD. 丁",
         "answer": "B", "analysis": "解析二"},
    ], ensure_ascii=False)

    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value(PAGE).run()
    p("打开导入页 exception:", at.exception)

    at.text_area(key="import_textarea").set_value(body)
    at.button(key="import_btn_parse").click().run()
    p("解析后 exception:", at.exception)
    p("草稿数:", len(at.session_state.get("import_drafts") or []))

    # 进入第 1 条编辑
    at.button(key="import_btn_edit_0").click().run()
    p("进入编辑 exception:", at.exception)
    p("edit_idx:", at.session_state.get("import_edit_idx"))
    p("编辑框 keys:", [k for k in at.session_state if str(k).startswith("import_d_")][:12])
    for u in at.file_uploader:
        p("uploader key:", u.key)

    # 上传一张题干配图
    at.file_uploader(key="import_d_stem_uploader").set_value(
        ("a.png", png(1), "image/png")).run()
    p("上传后 exception:", at.exception)
    dr = at.session_state["import_drafts"][0]
    p("草稿图片:", dr.images, "指纹数:", [len(v) for v in dr.staging.values()])
    staged_dir = imp.staging_dir()
    p("暂存目录:", [str(x.relative_to(IMAGES_DIR)) for x in staged_dir.rglob("*") if x.is_file()])

    # 再跑一次（模拟"上传框可能还留着文件"），应当不会变成两张
    at.run()
    dr = at.session_state["import_drafts"][0]
    p("重跑后草稿图片数:", dr.image_count, "（应为 1）")

    # 编辑题干 + 把图片标记写进正文
    at.text_area(key="import_d_stem").set_value("改过的题干 $x^3$ ![[img]]").run()
    p("编辑后 exception:", at.exception)
    p("widget 值:", repr(at.session_state.get("import_d_stem")))
    p("草稿 data 值:", repr(at.session_state["import_drafts"][0].data["stem"]))
    p("input 元素值:", [t.value for t in at.text_area if t.key == "import_d_stem"])
    dr = at.session_state["import_drafts"][0]
    p("草稿 latex 问题:", [(a, b.message) for a, b in dr.report.latex_issues])

    # 改成一个与库里已有题目重复的题干，验证"改完重新查重"
    with db_seed() as qid:
        at.text_area(key="import_d_stem").set_value("与库里重复的题干").run()
        dr = at.session_state["import_drafts"][0]
        p("重新查重 -> is_duplicate:", dr.report.is_duplicate,
          "ids:", dr.report.duplicate_ids, "（应含", qid, "）")
        p("   DB 里还有这道题吗:", qs.get_question(qid) is not None,
          " 按题干查重:", qs.find_duplicates_by_stem("与库里重复的题干"))

    # 入库前：正式图片目录里不该出现这张图
    before = {x.name for x in IMAGES_DIR.rglob("*.png")}
    p("正式目录里已有 png:", sorted(before)[:6])
    from src.config import DATA_DIR as _DD
    p("[主线程] DATA_DIR:", _DD,
      "按题干查重:", qs.find_duplicates_by_stem("与库里重复的题干"),
      "全部id:", [q.id for q in dc.list_questions()])

    at.button(key="import_btn_stop_edit").click().run()
    p("[主线程 停止编辑后] 按题干查重:",
      qs.find_duplicates_by_stem("与库里重复的题干"))
    p("停止编辑 exception:", at.exception)
    p("入库按钮:", [b.label for b in at.button
                    if (b.key or "").startswith("import_btn_commit")])
    p("报告仍在:", at.session_state.get("import_report") is not None,
      "草稿数:", len(at.session_state.get("import_drafts") or []))

    # 插桩：打印提交时每一行的状态与 promote 之后的结果
    from src.ui import import_page as ip
    _orig_commit = imp.commit_import

    def spy_commit(rows, *a, **kw):
        p(">> commit_import 收到", len(rows), "行")
        for i, r in enumerate(rows):
            p(f"   行{i}: ok={r.ok} dup={r.is_duplicate} draft_images={r.draft_images} "
              f"staged={r.staged_images} stem={r.data.get('stem')!r}")
        out = _orig_commit(rows, *a, **kw)
        p(">> commit_import 返回", out)
        return out

    imp.commit_import = spy_commit
    _orig_promote = ip._promote_drafts

    def spy_promote(drafts, rows):
        p(">> promote 前 drafts 数:", len(drafts))
        _orig_promote(drafts, rows)

    ip._promote_drafts = spy_promote

    cb = at.button(key="import_btn_commit")
    p("拿到提交按钮:", bool(cb), "key:", cb.key)
    cb.click()
    p("点击后 session 里的 report 还在:", "import_report" in at.session_state)
    at.run()
    p("入库 exception:", at.exception)
    p("页面 error:", [e.value for e in at.error])
    p("页面 warning:", [w.value for w in at.warning])
    p("flash:", at.session_state.get("_flash"))
    p("report:", at.session_state.get("import_report"))
    p("草稿:", len(at.session_state.get("import_drafts") or []))

    allq = dc.list_questions()
    p("库里题目数:", len(allq))
    for q in allq:
        p(f"  #{q.id} stem={q.stem[:24]!r} images={q.image_list}")
    stray = [str(x.relative_to(IMAGES_DIR)) for x in staged_dir.rglob("*") if x.is_file()]
    p("入库后暂存目录残留:", stray)
    after = {x.name for x in IMAGES_DIR.glob("*.png")}
    p("转正到正式目录的新文件:", sorted(after - before))
    return 0


class db_seed:
    """临时造一道题，用来验证"改完题干后重新查重"。"""
    def __enter__(self):
        self.qid = qs.create_question({
            "qtype": "解答题", "grade": "高三", "chapter": "查重", "difficulty": 3,
            "stem": "与库里重复的题干", "answer": "", "analysis": "",
        })
        dc.bump()
        return self.qid

    def __exit__(self, *a):
        qs.hard_delete_question(self.qid)
        dc.bump()
        return False


if __name__ == "__main__":
    raise SystemExit(main())
