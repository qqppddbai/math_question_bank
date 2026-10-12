# -*- coding: utf-8 -*-
"""自测 A：列表顺序 / 题干图与解析图的渲染位置 / 折叠面板惰性加载 / 旧数据兼容。"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # 项目根目录（tools/verify/checks → 项目根）
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(ROOT / "app.py")
PAGE = "📚  题目管理"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


def count_images(at):
    """页面上渲染出来的配图张数。

    正文里的配图现在走 HTML <img>（这样才能控制宽度和居中），
    所以既数 st.image 元素，也数 markdown 里的 <img alt="配图 N">。
    编辑器里的缩略图仍然是 st.image。
    """
    st_image = sum(len(e.proto.imgs) for e in at.get("image"))
    html_image = len(re.findall(r'alt="配图 \d+"',
                                "\n".join(m.value for m in at.markdown)))
    return st_image + html_image


def container_path(at, node):
    """返回某个元素在元素树里的容器路径（用于确认它被放在哪个容器里）。"""
    def walk(n, path=()):
        kids = list(n.children.values()) if getattr(n, "children", None) else []
        for k in kids:
            if k is node:
                return path + (k.type,)
            r = walk(k, path + (k.type,))
            if r:
                return r
        return None
    return walk(at._tree)

def all_markdown(at):
    return "\n".join(m.value for m in at.markdown)


def open_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def goto_question_page(at):
    at.sidebar.radio[0].set_value(PAGE).run()
    assert not at.exception, at.exception
    return at


# ------------------------------------------------------------
# A. 列表页 + 图片位置
# ------------------------------------------------------------
at = open_app()
check("应用正常启动", True)
goto_question_page(at)

md = all_markdown(at)
positions = [md.find(f"题干{i}") for i in ("一", "二", "三")]
check("列表按题库编号升序渲染（题干一 → 二 → 三）",
      all(p >= 0 for p in positions) and positions == sorted(positions),
      f"positions={positions}")

# 编辑 / 删除按钮应该竖排在卡片右侧的独立列里，而不是压在卡片下方
edit_path = container_path(at, at.button(key="edit_1"))
del_path = container_path(at, at.button(key="del_1"))
check("「✏️ 编辑」按钮在卡片右侧的列里",
      edit_path is not None and "column" in edit_path, f"path={edit_path}")
check("「🗑️ 删除」按钮和编辑按钮在同一列",
      del_path == edit_path, f"{del_path} vs {edit_path}")

# 两步删除：点删除 → 出现确认，确认按钮与删除按钮同列
at.button(key="del_1").click().run()
assert not at.exception, at.exception
check("点「删除」后出现「⚠️ 确认」按钮",
      any(b.key == "confirm_del_1" and b.label == "⚠️ 确认" for b in at.button))
check("确认按钮也在右侧同一列",
      container_path(at, at.button(key="confirm_del_1")) == edit_path)
check("提供「取消」按钮",
      any(b.key == "cancel_del_1" for b in at.button))

at.button(key="cancel_del_1").click().run()
assert not at.exception, at.exception
check("取消后回到普通「删除」按钮", any(b.key == "del_1" for b in at.button))

img_all = count_images(at)
check("题干图（#1、#3 各 1 张）都在题面渲染",
      img_all >= 2, f"图片数={img_all}")

check("解析文字随卡片一起渲染（面板不触发重跑，代价就是提前渲染）",
      "解析一" in md and "解析三" in md)

# ------------------------------------------------------------
# B. 解析文字 / 解析图 渲染正确（确定性验证，不模拟点击）
# ------------------------------------------------------------
ans_exps = [e for e in at.expander if "查看答案与解析" in e.label]
check("卡片下方各有 1 个「查看答案与解析」面板", len(ans_exps) == 3,
      f"count={len(ans_exps)}")
check("面板不跟踪状态（没加 on_change=rerun，展开收起不惊动服务器）",
      all(not e.proto.id for e in ans_exps))

# 用一个"最小应用"验证：展开与收起都要正确渲染答案/解析/解析配图
# （探测脚本写在沙箱数据目录旁边，跑完就删，不往项目里丢临时文件）
_probe_dir = Path(os.environ.get("MATHBANK_DATA_DIR") or ROOT)
SRC = _probe_dir / "_probe_card.py"
SRC.write_text(
    "import sys\n"
    f"sys.path.insert(0, r'{ROOT}')\n"
    "import streamlit as st\n"
    "from src.services import question_service as qs\n"
    "from src.ui import question_card as qc\n"
    "q = qs.get_question(2)          # 只有解析配图的题目\n"
    "qc.render_answer_expander(q, key='closed')\n",
    encoding="utf-8",
)
probe = AppTest.from_file(str(SRC), default_timeout=30)
probe.run()
assert not probe.exception, probe.exception
probe_md = all_markdown(probe)
check("收起的解析面板里解析文字已渲染（浏览器本地展开，零延迟）",
      probe_md.count("解析二") == 1, f"出现次数={probe_md.count('解析二')}")
check("收起的解析面板里解析配图已渲染",
      count_images(probe) == 1, f"图片数={count_images(probe)}")
SRC.unlink(missing_ok=True)

# ------------------------------------------------------------
# C. 编辑保存后顺序不变
# ------------------------------------------------------------
from src.services import data_cache as dc          # noqa: E402
from src.services import question_service as qs    # noqa: E402

dc.bump()
before = [q.id for q in dc.list_questions()]
check("初始列表顺序 = 题库编号升序", before == [1, 2, 3], f"{before}")

at = open_app()
goto_question_page(at)
at.button(key="edit_1").click().run()
assert not at.exception, at.exception
check("点「编辑」进入编辑表单",
      any("编辑题目 #1" in s.value for s in at.subheader))

[s for s in at.selectbox if s.key == "q_edit_difficulty"][0].set_value(5)
save = [b for b in at.button if (b.label or "").startswith("💾")]
check("找到保存按钮", len(save) == 1, f"count={len(save)}")
save[0].click().run()
assert not at.exception, at.exception
check("保存后回到列表页", any("题目管理" in s.value for s in at.subheader))

dc.bump()
after = [q.id for q in dc.list_questions()]
check("保存后列表顺序不变（1,2,3）", after == [1, 2, 3], f"{after}")

q1 = qs.get_question(1)
check("被编辑的题目内容确实更新了（难度 3→5）",
      q1 is not None and q1.difficulty == 5,
      f"difficulty={getattr(q1, 'difficulty', None)}")

check("分页场景顺序也稳定",
      [q.id for q in dc.list_questions(limit=2, offset=0)] == [1, 2]
      and [q.id for q in dc.list_questions(limit=2, offset=2)] == [3])

check("旧式无前缀图片仍归题干组",
      q1.image_list == ["images/stem_only.png"], f"image_list={q1.image_list}")

# ------------------------------------------------------------
# E. 保存 / 取消后回到列表，位置不能丢
#    列表顺序、页码、每张卡片的位置都要和进去之前一模一样，
#    只是多了一段「滚回刚编辑的那道题」的脚本 + 一圈绿边锚点。
# ------------------------------------------------------------
def focus_scripts(at_page):
    """页面里所有「滚回刚编辑题目」的脚本内容。"""
    return [e.proto.srcdoc for e in at_page.get("iframe")
            if "scrollIntoView" in (e.proto.srcdoc or "")]


check("保存后列表里每张卡片都还在原位（没有谁被搬走）",
      all(any((b.key or "") == f"edit_{i}" for b in at.button) for i in (1, 2, 3)),
      str([b.key for b in at.button]))
check("保存后列表顺序不变", [b.key for b in at.button if (b.key or "").startswith("edit_")]
      == ["edit_1", "edit_2", "edit_3"],
      str([b.key for b in at.button]))
check("刚保存的题目被套上定位锚点（q_focus_1）",
      any("st-key-q_focus_1" in s for s in focus_scripts(at)),
      str(focus_scripts(at))[:120])
check("定位脚本是滚到那道题并让它居中",
      any("scrollIntoView" in s and "'center'" in s for s in focus_scripts(at)))
check("定位只做一次：q_focus_id 用完就清掉",
      at.session_state["q_focus_id"] is None,
      str(at.session_state["q_focus_id"]))

# 再重跑一次（等价于用户随后点了任意一下），不应该又冒出定位脚本
at.run()
assert not at.exception, at.exception
check("之后正常浏览不会再被拽回去", focus_scripts(at) == [],
      str(focus_scripts(at))[:80])

# 点「编辑」→「取消」也要回到原来那道题，不能退回顶部
at.button(key="edit_2").click().run()
assert not at.exception, at.exception
check("能进入 #2 的编辑表单", any("编辑题目 #2" in s.value for s in at.subheader))
[c for c in at.button if (c.label or "") == "取消"][0].click().run()
assert not at.exception, at.exception
check("取消编辑后也记住了刚才在改哪一道",
      at.session_state["q_focus_id"] is None
      and any("st-key-q_focus_2" in s for s in focus_scripts(at)),
      str(focus_scripts(at))[:120])

# 新增的题目排在最后一页，同样要能定位
at = open_app()
goto_question_page(at)
[n for n in at.button if "新增题目" in (n.label or "")][0].click().run()
assert not at.exception, at.exception
at.text_area(key="q_edit_stem").set_value("新增的定位测试题 $x^2$")
[s for s in at.button if (s.label or "").startswith("💾")][0].click().run()
assert not at.exception, at.exception
check("新增的题目保存后也会定位到它",
      any("st-key-q_focus_" in s for s in focus_scripts(at)),
      str(focus_scripts(at))[:120])
check("新增题确实入库了",
      "新增的定位测试题" in all_markdown(at)
      and "新增成功" in " ".join(s.value for s in at.success),
      str([s.value for s in at.success])[:80])

# ------------------------------------------------------------
# D. 解析配图能通过编辑表单保存（围绕 UI 的写路径）
# ------------------------------------------------------------
dc.bump()
q2 = qs.get_question(2)
check("#2 的解析图存的是 analysis: 前缀",
      q2.image_list == ["analysis:images/analysis_only.png"],
      f"{q2.image_list}")

# ------------------------------------------------------------
# F. 分页场景：新增的题排在最后一页，保存后要自动翻过去
# ------------------------------------------------------------
from src.ui.question_page import PAGE_SIZE  # noqa: E402

dc.bump()
for i in range(PAGE_SIZE + 3):
    qs.create_question({
        "qtype": "解答题", "grade": "高一", "chapter": "分页测试", "difficulty": 3,
        "stem": f"分页测试题 {i}：$x^{{{i}}}$", "answer": "", "analysis": "",
        "source": "自测", "tags": "", "options_list": [], "image_list": [],
    })
total_now = dc.count_questions()
check("题库已超过一页（造够了分页数据）", total_now > PAGE_SIZE,
      f"共 {total_now} 道，每页 {PAGE_SIZE}")

at = open_app()
goto_question_page(at)
at.session_state["q_page"] = 1
at.run()
[n for n in at.button if "新增题目" in (n.label or "")][0].click().run()
assert not at.exception, at.exception
at.text_area(key="q_edit_stem").set_value("分页新增的最后一道题 $y$")
[s for s in at.button if (s.label or "").startswith("💾")][0].click().run()
assert not at.exception, at.exception

new_id = max(q.id for q in dc.list_questions())
expected_page = (dc.count_questions() - 1) // PAGE_SIZE + 1
check("新增的题落在最后一页（分页前提成立）", expected_page > 1,
      f"新题 #{new_id} 应在第 {expected_page} 页")
check("保存后自动翻到新题所在的那一页",
      at.session_state["q_page"] == expected_page,
      f"q_page={at.session_state['q_page']} 期望 {expected_page}")
check("翻页之后仍然定位到了这道新题",
      any(f"st-key-q_focus_{new_id}" in s for s in focus_scripts(at)),
      str(focus_scripts(at))[:120])

print("\n================ 汇总 ================")
bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
print(f"\n{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
