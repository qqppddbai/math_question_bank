# -*- coding: utf-8 -*-
"""自测 B：编辑表单里「题干配图 / 解析配图」两组的独立管理。"""
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # 项目根目录（tools/verify/checks → 项目根）
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.services import question_service as qs  # noqa: E402
from src.utils import file_utils  # noqa: E402

APP = str(ROOT / "app.py")
PAGE = "📚  题目管理"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


class FakeUpload:
    def __init__(self, name, color):
        buf = BytesIO()
        Image.new("RGB", (50, 30), color).save(buf, format="PNG")
        self._data = buf.getvalue()
        self.name = name
        self.size = len(self._data)

    def getbuffer(self):
        return self._data

    def read(self):
        return self._data


def open_editor(qid):
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value(PAGE).run()
    at.button(key=f"edit_{qid}").click().run()
    assert not at.exception, at.exception
    return at


def count_images(at):
    """只数编辑器里的缩略图（st.image 元素）。

    正文/预览里的配图走 HTML <img>，由 _verify.py 那套断言覆盖，
    这里关心的是"图片管理区"里有没有把已有图片都列出来。
    """
    return sum(len(e.proto.imgs) for e in at.get("image"))


def click_save(at):
    [b for b in at.button if (b.label or "").startswith("💾")][0].click().run()
    assert not at.exception, at.exception


# ------------------------------------------------------------
# ① UI 段
# ------------------------------------------------------------
before = qs.get_question(1)
check("初始：#1 只有 1 张题干图",
      file_utils.split_images(before.image_list) == (["images/stem_only.png"], []),
      f"{before.image_list}")

at = open_editor(1)
stem_up = [u for u in at.get("file_uploader") if "题干配图" in u.label]
ana_up = [u for u in at.get("file_uploader") if "解析配图" in u.label]
check("编辑表单有两个互相独立的上传框（题干配图 / 解析配图）",
      len(stem_up) == 1 and len(ana_up) == 1 and stem_up[0].key != ana_up[0].key,
      f"keys={[u.key for u in stem_up + ana_up]}")

# 题目 #3 同时有题干图和解析图，图片管理区应把两张都列出来（各带一个标记代码块）。
# 注意：解析实时预览里的图现在走 HTML <img>，不计入 st.image 数量。
at3 = open_editor(3)
check("#3 图片管理区列出 2 张缩略图（题干 1 + 解析 1）",
      count_images(at3) == 2, f"图片数={count_images(at3)}")
check("#3 两组各只有一张图，都用省略序号的短标记",
      [c.value for c in at3.code] == ["![[img]]", "![[img]]"],
      f"{[c.value for c in at3.code]}")
check("#3 图片下方没有「图 1」这类图注",
      "图 1<" not in "\n".join(m.value for m in at3.markdown))

# 勾选删除「解析第 1 张」，保存后解析组清空、题干组不受影响
at3.session_state["q_edit_analysis_del_0"] = True
click_save(at3)
stem_imgs, ana_imgs = file_utils.split_images(qs.get_question(3).image_list)
check("勾选删除解析图后：解析配图清空", len(ana_imgs) == 0, f"{ana_imgs}")
check("勾选删除解析图后：题干配图不受影响", len(stem_imgs) == 1, f"{stem_imgs}")

# ------------------------------------------------------------
# ② 数据段：上传落盘 + 分组拼装
# ------------------------------------------------------------
new_a = file_utils.save_uploaded_image(FakeUpload("a.png", (1, 2, 3)))
new_b = file_utils.save_uploaded_image(FakeUpload("b.png", (4, 5, 6)))
check("上传的图片落盘并返回 data/ 下的相对路径",
      new_a.startswith("images/") and file_utils.abs_path(new_a).is_file()
      and file_utils.abs_path(new_b).is_file(),
      f"{new_a}, {new_b}")

joined = file_utils.join_images(["images/stem_only.png", new_a], [new_b])
check("题干图在前、解析图带前缀在后",
      joined == ["images/stem_only.png", new_a, f"analysis:{new_b}"], f"{joined}")
check("拼装结果能原样拆回两组",
      file_utils.split_images(joined) == (["images/stem_only.png", new_a], [new_b]))

# 走一遍真正的写库路径，确认解析图能存进去再读出来
qs.update_question(1, {"image_list": joined})
reloaded = qs.get_question(1)
check("解析配图能写库并原样读回",
      file_utils.split_images(reloaded.image_list)
      == (["images/stem_only.png", new_a], [new_b]),
      f"{reloaded.image_list}")

# ------------------------------------------------------------
print("\n================ 汇总 ================")
bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
print(f"\n{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
