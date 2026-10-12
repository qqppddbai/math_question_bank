# -*- coding: utf-8 -*-
"""自测 E：把配图用 ![[img:N]] 标记插到题干 / 解析的文字之间。

覆盖：
  1. 纯解析层（不依赖 Streamlit）：标记解析、分段、越界、重复引用、宽度、旧数据兼容；
  2. 渲染层：题干里的图插在标记处（不再堆到末尾）；没有标记时行为与改动前一致；
  3. 解析配图同样支持标记；
  4. 编辑器的实时预览也按标记排图；
  5. 编辑器里给出带复制按钮的标记文本、未安置提示。
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # 项目根目录（tools/verify/checks → 项目根）
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.services import question_service as qs  # noqa: E402
from src.utils.rich_text import (markdown_to_blocks,  # noqa: E402
                                marker_syntax, placement_report)

APP = str(ROOT / "app.py")
PAGE = "📚  题目管理"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


def run_probe(src: str, name: str):
    """写一个最小应用跑一遍，返回 AppTest。"""
    probe_dir = Path(os.environ.get("MATHBANK_DATA_DIR") or ROOT)
    path = probe_dir / name
    # 用 repr(ROOT) 而不是 r'{ROOT}'：Windows 路径里的 \U、\t 等会被当成转义序列
    src = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n" + src
    path.write_text(src, encoding="utf-8")
    at = AppTest.from_file(str(path), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    path.unlink(missing_ok=True)
    return at


def md_all(at):
    return "\n".join(m.value for m in at.markdown)


def img_markers(at):
    """页面上渲染出来的图片（我们用 HTML <img data:...> 输出）的出现顺序。"""
    return [m for m in re.finditer(r'alt="配图 (\d+)"', md_all(at))]


# ============================================================
# 一、纯解析层
# ============================================================
text = "第一段。\n\n![[img:1]]\n\n第二段。"
blocks = markdown_to_blocks(text, ["a.png", "b.png"])
check("标记把文字切成 文字-图片-文字 三块",
      [b["type"] for b in blocks] == ["text", "image", "text"],
      f"{[b['type'] for b in blocks]}")

check("图片块指向正确的图片",
      blocks[1]["path"] == "a.png" and blocks[1]["number"] == 1)

check("文字块保留原有内容",
      blocks[0]["text"].strip() == "第一段。" and blocks[2]["text"].strip() == "第二段。")

# 旧数据：没有标记 → 文字 + 末尾全部图片
legacy = markdown_to_blocks("只有文字", ["a.png", "b.png"])
check("没有标记时：一段文字 + 末尾两张图（与改动前一致）",
      [b["type"] for b in legacy] == ["text", "image", "image"],
      f"{[b['type'] for b in legacy]}")

# 宽度
wide = markdown_to_blocks("前 ![[img:1|300]] 后", ["a.png"])
check("支持指定宽度 ![[img:1|300]]", wide[1]["size"] == 300, f"{wide[1]}")

# 省略序号：只有一张图时不用写数字
bare = markdown_to_blocks("前 ![[img]] 后", ["a.png"])
check("省略序号 ![[img]] 默认引用第 1 张",
      bare[1]["type"] == "image" and bare[1]["path"] == "a.png"
      and bare[1]["number"] == 1,
      f"{bare[1]}")

bare_wide = markdown_to_blocks("前 ![[img|260]] 后", ["a.png"])
check("省略序号也能带宽度 ![[img|260]]",
      bare_wide[1]["size"] == 260 and bare_wide[1]["path"] == "a.png",
      f"{bare_wide[1]}")

many = markdown_to_blocks("![[img]] 和 ![[img:2]]", ["a.png", "b.png"])
check("省略序号与显式序号可以混用",
      [b.get("path") for b in many if b["type"] == "image"] == ["a.png", "b.png"])

check("只有一张图时编辑器里给出的标记是短写法",
      marker_syntax(1, compact=True) == "![[img]]"
      and marker_syntax(2, compact=True) == "![[img:2]]"
      and marker_syntax(1, compact=False) == "![[img:1]]")

# 正文图片默认宽度：统一在 config.py 里配置
from src.config import DEFAULT_IMAGE_WIDTH_PX  # noqa: E402
from src.ui import question_card as qc  # noqa: E402

check("正文图片默认宽度取自 config.DEFAULT_IMAGE_WIDTH_PX",
      qc.BLOCK_IMAGE_WIDTH == DEFAULT_IMAGE_WIDTH_PX,
      f"{qc.BLOCK_IMAGE_WIDTH}px")
check("默认宽度就是设置里的 100 像素",
      DEFAULT_IMAGE_WIDTH_PX == 100, f"{DEFAULT_IMAGE_WIDTH_PX}px")

# 同一张图重复引用
twice = markdown_to_blocks("![[img:1]] 中间 ![[img:1]]", ["a.png"])
check("同一张图可以重复引用",
      [b.get("number") for b in twice if b["type"] == "image"] == [1, 1])

# 序号越界
bad = markdown_to_blocks("前 ![[img:9]] 后", ["a.png"])
check("序号越界时图片块 path 为空（渲染层会提示）",
      bad[1]["path"] is None and bad[1]["number"] == 9)

# 空格容错
loose = markdown_to_blocks("前 ![[ img : 1 ]] 后", ["a.png"])
check("标记里多写空格也能认出来",
      any(b["type"] == "image" and b["number"] == 1 for b in loose))

# 安置情况汇报
rep = placement_report("![[img:2]] 和 ![[img:7]]", ["a.png", "b.png"])
check("安置汇报：已安置 / 未安置 / 不存在的序号",
      rep == {"has_marker": True, "placed": [2], "unplaced": [1], "bad": [7]},
      f"{rep}")

check("标记文本生成正确",
      marker_syntax(2) == "![[img:2]]" and marker_syntax(2, 300) == "![[img:2|300]]")

# ============================================================
# 二、渲染层：题干
# ============================================================
qs.update_question(1, {
    "stem": "第一段文字。\n\n![[img:1]]\n\n第二段文字。",
    "image_list": ["images/stem_only.png"],
})
probe = run_probe(
    "import streamlit as st\n"
    "from src.services import question_service as qs\n"
    "from src.ui import question_card as qc\n"
    "qc.render_body(qs.get_question(1), key='t')\n",
    "_probe_rt1.py",
)
md = md_all(probe)
pos_head = md.find("第一段文字。")
pos_img = md.find('alt="配图 1"')
pos_tail = md.find("第二段文字。")
check("题干：图片渲染在标记位置（第一段之后、第二段之前）",
      -1 < pos_head < pos_img < pos_tail,
      f"head={pos_head} img={pos_img} tail={pos_tail}")
check("题干：图片用的是 data: 内嵌的 HTML <img>",
      "data:image" in md)
check("题干：没写宽度时按 config 里的默认值渲染",
      f'width:{DEFAULT_IMAGE_WIDTH_PX}px' in md,
      f"期望 width:{DEFAULT_IMAGE_WIDTH_PX}px")
check("图片下方不再显示「图 1」这类图注",
      ">图 1<" not in md and "图 1</span>" not in md,
      "还残留图注" if "图 1</span>" in md else "")

# 没有标记 → 图片仍然在文字之后
qs.update_question(1, {
    "stem": "只有一段文字。",
    "image_list": ["images/stem_only.png"],
})
probe2 = run_probe(
    "import streamlit as st\n"
    "from src.services import question_service as qs\n"
    "from src.ui import question_card as qc\n"
    "qc.render_body(qs.get_question(1), key='t2')\n",
    "_probe_rt2.py",
)
md2 = md_all(probe2)
check("旧数据（无标记）：图片仍在文字之后",
      -1 < md2.find("只有一段文字。") < md2.find('alt="配图 1"'))

# 越界提示
qs.update_question(1, {
    "stem": "引用了不存在的图 ![[img:5]]",
    "image_list": ["images/stem_only.png"],
})
probe3 = run_probe(
    "import streamlit as st\n"
    "from src.services import question_service as qs\n"
    "from src.ui import question_card as qc\n"
    "qc.render_body(qs.get_question(1), key='t3')\n",
    "_probe_rt3.py",
)
check("序号写错时给出一行提示，不会整块消失",
      "不存在" in md_all(probe3), md_all(probe3)[-80:])

# ============================================================
# 三、解析配图也支持标记
# ============================================================
qs.update_question(2, {
    "analysis": "解析第一句。\n\n![[img:1]]\n\n解析第二句。",
    "image_list": ["analysis:images/analysis_only.png"],
})
probe4 = run_probe(
    "import streamlit as st\n"
    "from src.services import question_service as qs\n"
    "from src.ui import question_card as qc\n"
    "qc.render_answer_expander(qs.get_question(2), key='a', expanded=True)\n",
    "_probe_rt4.py",
)
md4 = md_all(probe4)
check("解析：解析图插在解析文字之间",
      -1 < md4.find("解析第一句。") < md4.find('alt="配图 1"')
      < md4.find("解析第二句。"),
      f"head={md4.find('解析第一句。')} img={md4.find('alt=\"配图 1\"')} "
      f"tail={md4.find('解析第二句。')}")
check("解析：题干图不会被误当成解析图", "图片已丢失" not in md4)

# ============================================================
# 四、编辑器
# ============================================================
qs.update_question(1, {
    "stem": "第一段。\n\n![[img:1]]\n\n第二段。",
    "image_list": ["images/stem_only.png"],
})
at = AppTest.from_file(APP, default_timeout=30)
at.run()
at.sidebar.radio[0].set_value(PAGE).run()
at.button(key="edit_1").click().run()
assert not at.exception, at.exception

codes = [c.value for c in at.code]
check("只有一张图时编辑器给的是省略序号的短标记",
      codes == ["![[img]]"], f"代码块={codes}")

body = md_all(at)
check("编辑器实时预览里图片也插在标记位置",
      -1 < body.find("第一段。") < body.find('alt="配图 1"')
      < body.find("第二段。"))

check("编辑器提示了标记用法",
      any("![[img:1]]" in c.value for c in at.caption),
      f"caption 数={len(at.caption)}")
check("编辑器有两个独立的上传框",
      len([u for u in at.get("file_uploader")
           if "题干配图" in u.label or "解析配图" in u.label]) == 2)

# 多图的未安置提示
qs.update_question(3, {
    "stem": "只安置了第一张 ![[img:1]]",
    "image_list": ["images/both_stem.png", "images/stem_only.png"],
})
at2 = AppTest.from_file(APP, default_timeout=30)
at2.run()
at2.sidebar.radio[0].set_value(PAGE).run()
at2.button(key="edit_3").click().run()
assert not at2.exception, at2.exception
caps = [c.value for c in at2.caption]
check("有图片没用标记安置时会明确提示",
      any("还没安置" in c for c in caps),
      [c for c in caps if "安置" in c][:2])
check("提供了「不想手抄标记」的插入工具",
      any("不想手抄标记" in e.label for e in at2.expander))
check("两张图各自给出可复制的标记",
      [c.value for c in at2.code] == ["![[img:1]]", "![[img:2]]"],
      f"{[c.value for c in at2.code]}")

# ------------------------------------------------------------
print("\n================ 汇总 ================")
bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
print(f"\n{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
