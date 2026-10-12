# -*- coding: utf-8 -*-
"""临时：追踪 is_duplicate 在「停止编辑」前后是否保持。跑完即删。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.services import data_cache as dc  # noqa: E402
from src.services import question_service as qs  # noqa: E402

APP = str(ROOT / "app.py")
PAGE = "📥  批量导入"


def show(tag, at):
    ds = at.session_state.get("import_drafts") or []
    info = [(d.report.is_duplicate, d.report.duplicate_ids,
             d.data.get("stem", "")[:14]) for d in ds]
    print(f"[{tag}] edit_idx={at.session_state.get('import_edit_idx')} "
          f"stem_widget={at.session_state.get('import_d_stem')!r} {info}", flush=True)


def main() -> int:
    qid = qs.create_question({
        "qtype": "解答题", "grade": "高三", "chapter": "查重", "difficulty": 3,
        "stem": "与库里重复的题干", "answer": "", "analysis": "",
    })
    dc.bump()
    print("seeded qid =", qid, flush=True)

    body = json.dumps([
        {"stem": "草稿冒烟第一题", "qtype": "解答题", "difficulty": 4},
        {"stem": "草稿冒烟第二题", "qtype": "解答题", "difficulty": 4},
    ], ensure_ascii=False)

    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value(PAGE).run()
    at.text_area(key="import_textarea").set_value(body)
    at.button(key="import_btn_parse").click().run()
    show("解析后", at)

    at.button(key="import_btn_edit_0").click().run()
    show("进入编辑", at)

    at.text_area(key="import_d_stem").set_value("与库里重复的题干").run()
    show("改成重复题干后", at)

    at.button(key="import_btn_stop_edit").click().run()
    show("停止编辑后", at)

    import src.ui.import_page as ip  # noqa: E402
    _orig = ip._promote_drafts

    def spy_promote(drafts, rows):
        print("   >> promote 前:", [(d.report.is_duplicate, d.report.duplicate_ids)
                                    for d in drafts], flush=True)
        out = _orig(drafts, rows)
        print("   >> promote 后:", [(r.is_duplicate, r.duplicate_ids) for r in rows],
              flush=True)
        return out

    ip._promote_drafts = spy_promote
    at.button(key="import_btn_commit").click().run()
    print("提交后 exception:", at.exception, flush=True)

    idx = at.session_state.get("import_edit_idx")
    print("提交后 edit_idx:", idx, flush=True)

    qs.hard_delete_question(qid)
    dc.bump()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
