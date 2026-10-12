# -*- coding: utf-8 -*-
"""自测 D：所有写操作完成后，读接口必须立刻返回新数据。

这是踩过的坑：缓存清不掉时，界面会一直显示旧数据、重启才好。
所以这里逐个写操作验证一遍：
  - 数据层：写完立刻用 data_cache 的读接口查，必须看到新值；
  - 界面层：改题干、删除、回收站、批量加标签，都必须当次操作就在页面上生效。

新增写操作时，请照着这里补一条。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # 项目根目录（tools/verify/checks → 项目根）
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.services import data_cache as dc  # noqa: E402
from src.services import question_service as qs  # noqa: E402

APP = str(ROOT / "app.py")
PAGE = "📚  题目管理"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


def stems(**kw):
    return [q.stem for q in dc.list_questions(**kw)]


def tags_of(qid):
    return qs.get_question(qid).tag_list


def md_all(at):
    return "\n".join(m.value for m in at.markdown)


# ============================================================
# 一、数据层：每个写操作之后，读缓存必须已经失效
# ============================================================
# 1) 修改
dc.list_questions(limit=10)                       # 先把缓存填上
qs.update_question(1, {"stem": "改过的题干-1"})
check("update_question 后 list_questions 立刻返回新题干",
      "改过的题干-1" in stems(), f"{stems()[:2]}")

# 2) 软删除
qs.soft_delete_question(2)
check("soft_delete_question 后列表里不再有 #2",
      2 not in [q.id for q in dc.list_questions()])
check("soft_delete_question 后回收站计数 +1",
      dc.count_deleted_questions() >= 1,
      f"count={dc.count_deleted_questions()}")

# 3) 还原
qs.restore_question(2)
check("restore_question 后 #2 回到列表",
      2 in [q.id for q in dc.list_questions()])

# 4) 新增
new_id = qs.create_question({"stem": "新增的题干-9", "qtype": "解答题",
                             "difficulty": 3, "options_list": [],
                             "image_list": []})
check("create_question 后新题立刻出现在列表",
      any(q.id == new_id for q in dc.list_questions()),
      f"new_id={new_id}")

# 5) 批量加标签
dc.list_questions(limit=10)
qs.batch_add_tags([1, 3], ["缓存检验标签"])
check("batch_add_tags 后标签立刻生效",
      "缓存检验标签" in tags_of(1) and "缓存检验标签" in tags_of(3),
      f"{tags_of(1)}")
check("batch_add_tags 后筛选候选值也刷新",
      "缓存检验标签" in dc.get_all_tags(), f"{dc.get_all_tags()}")

# 6) 批量移除标签
qs.batch_remove_tags([1, 3], ["缓存检验标签"])
check("batch_remove_tags 后标签立刻消失",
      "缓存检验标签" not in tags_of(1) and "缓存检验标签" not in tags_of(3))

# 7) 批量软删除
qs.batch_soft_delete([new_id])
check("batch_soft_delete 后题目立刻从列表消失",
      new_id not in [q.id for q in dc.list_questions()])

# 8) 彻底删除
qs.batch_hard_delete_questions([new_id])
check("batch_hard_delete 后回收站里也没有了",
      new_id not in [q.id for q in dc.list_deleted_questions()])

# 9) 组卷用的批量取题（也必须跟着失效）
from src.services import paper_service as ps  # noqa: E402

qs.update_question(3, {"stem": "改过的题干-3"})
got = ps.get_questions_by_ids([3])
check("get_questions_by_ids 拿到的也是新题干",
      got.get(3) is not None and got[3].stem == "改过的题干-3",
      f"{getattr(got.get(3), 'stem', None)}")

# ============================================================
# 二、界面层：操作完当次就在页面上看到结果，不用重启
# ============================================================
dc.bump()
at = AppTest.from_file(APP, default_timeout=30)
at.run()
at.sidebar.radio[0].set_value(PAGE).run()
check("列表页能看到改过的题干", "改过的题干-3" in md_all(at))

# 改题干 → 立刻可见
at.button(key="edit_3").click().run()
at.session_state["q_edit_stem"] = "界面上改的题干-3"
[b for b in at.button if (b.label or "").startswith("💾")][0].click().run()
assert not at.exception, at.exception
check("编辑保存后立刻在列表看到新题干",
      "界面上改的题干-3" in md_all(at),
      "还是旧的" if "界面上改的题干-3" not in md_all(at) else "")

# 删除 → 立刻少一条
n_before = len([b for b in at.button if (b.key or "").startswith("del_")])
at.button(key="del_1").click().run()
at.button(key="confirm_del_1").click().run()
n_after = len([b for b in at.button if (b.key or "").startswith("del_")])
check("删除后列表立刻少一条", n_after == n_before - 1, f"{n_before} → {n_after}")

# 回收站 → 立刻可见
at.sidebar.radio[0].set_value("🗑️  回收站").run()
check("回收站里立刻出现刚删的题",
      at.metric[0].value != "0 道" and len(at.dataframe) >= 1,
      f"已删除题目={at.metric[0].value} 表格数={len(at.dataframe)}")

# 批量加标签 → 立刻有反馈
at.sidebar.radio[0].set_value("🔍  搜索筛选").run()
at.button(key="search_tog_2").click().run()
at.text_input(key="search_add_tag_input").set_value("界面加的标签")
at.button(key="search_btn_add_tag").click().run()
check("批量加标签后页面上立刻出现成功提示",
      any("追加标签" in s.value for s in at.success),
      f"{[s.value for s in at.success][:2]}")

at.sidebar.radio[0].set_value("📚  题目管理").run()
check("加完标签立刻在列表里看到", "界面加的标签" in md_all(at))

# ------------------------------------------------------------
print("\n================ 汇总 ================")
bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
print(f"\n{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
