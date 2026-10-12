# -*- coding: utf-8 -*-
"""自测 F：批量导入的「公式体检」与「重复题覆盖导入」。

两组功能各测三层：
  1. 纯函数层：latex_check 对一批真实公式的判断（含正例，防止误报回归）；
  2. 数据层：parse_json_text / commit_import 的三种重复处理方式；
  3. 界面层：导入页真的把公式问题显示出来，并且「自动修复」按钮能改写文本框；
             题目编辑器里也做了同样的提醒与修复。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # 项目根目录（tools/verify/checks → 项目根）
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.services import data_cache as dc  # noqa: E402
from src.services import import_service as imp  # noqa: E402
from src.services import question_service as qs  # noqa: E402
from src.utils import latex_check as lc  # noqa: E402

APP = str(ROOT / "app.py")
PAGE = "📥  批量导入"

# 老师实际遇到的那段（公式编辑器导出的 *{35}{l} 写法，KaTeX 渲染成红字）
BAD_STEM = (
    r"由题意可得$f\left( x \right)=\left\{ \begin{array}{*{35}{l}} "
    r"\text{ln}x,x>1 \\ -\text{ln}x,0<x<1 \\ \end{array} \right.$，"
    r"故$a<b<c$."
)
# 同一道题修好之后的样子
GOOD_STEM = (
    r"由题意可得$f\left( x \right)=\left\{ \begin{array}{l} "
    r"\text{ln}x,x>1 \\ -\text{ln}x,0<x<1 \\ \end{array} \right.$，"
    r"故$a<b<c$."
)
# 一批正常公式：一条都不该报，防止检查器误报
OK_SNIPPETS = [
    r"设 $f(x)=x^2-2x+3$，则 $f'(x)=2x-2$。",
    r"$\lim_{n\to\infty}\left(1+\frac{1}{n}\right)^n=e$，$\int_0^1 x^2\,dx=\frac13$。",
    r"$f(x)=\begin{cases} x, & x\ge 0 \\ -x, & x<0 \end{cases}$",
    r"$\begin{pmatrix} a & b \\ c & d \end{pmatrix}$，$\left|\overrightarrow{AB}\right|=\sqrt{2}$",
    r"$$\begin{aligned} a &= b+c \\ &= d \end{aligned}$$",
    r"$x^{2}+y_{1}+a_{i}^{2}+x^\circ+x^*$",
    r"$\begin{array}{l} a \\ b \end{array}$，$\begin{array}{|l|c|} \hline a & b \\ \hline \end{array}$",
    r"$\alpha\leqslant\beta$，$\mathbb{R}$，$\varnothing$，$\therefore$，$\text{ln}x$",
    r"这件商品 \$5，那件 \$10。",
    "这是一段没有公式的中文题干。",
]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


def md_all(at):
    return "\n".join(m.value for m in at.markdown)


# ============================================================
# 一、公式体检：纯函数层
# ============================================================
issues = lc.check_text(BAD_STEM)
check("坏公式被检查出来（且是会渲染成红字的 error）",
      len(issues) == 1 and issues[0].is_error,
      f"{[i.message for i in issues]}")
check("坏公式的问题描述指出了 *{n}{列} 这个原因",
      issues and "*{个数}{列}" in issues[0].message, issues[0].message if issues else "")
check("坏公式被标成「可自动修复」", issues and issues[0].fixable)

fixed, n_fixed = lc.fix_text(BAD_STEM)
check("fix_text 确实改动了内容", n_fixed == 1 and fixed != BAD_STEM, f"改了 {n_fixed} 处")
check("修好之后不再报公式问题", lc.check_text(fixed) == [],
      f"{[i.message for i in lc.check_text(fixed)]}")
check("修好之后列格式里不含 KaTeX 不支持的 *", "*{35}" not in fixed)

bad_reports = []
for s in OK_SNIPPETS:
    got = lc.check_text(s)
    if got:
        bad_reports.append((s, [i.message for i in got]))
check(f"{len(OK_SNIPPETS)} 条正常公式一条都不误报", not bad_reports, str(bad_reports[:2]))

check(r"\( \) 写法会被指出（Streamlit 只认 $...$）",
      any("定界符" in i.message for i in lc.check_text(r"\(\frac{1}{2}\)")))
check("$ 没配对会被指出",
      any("没有找到配对" in i.message for i in lc.check_text("已知 $x>0 求最小值")))
check("KaTeX 不认识的命令会被指出（并给出替代写法）",
      any("mbox" in i.message and "text" in i.message for i in lc.check_text(r"$a \mbox{ cm}$")))
check("行内公式里用 display 环境会被指出",
      any("只能写在 $$" in i.message for i in lc.check_text(r"$\begin{align} a &= b \end{align}$")))
check("不支持的数组列格式 p{} 会被指出",
      any("p{宽度}" in i.message for i in lc.check_text(r"$\begin{array}{p{2cm}} a \end{array}$")))

# 空行会截断段落，行内公式不能跨空行配对——别把两段里的 $ 硬凑成一段
CROSS = "已知 $x>0。\n\n求 $y=1$ 的值。"
segs_cross, unpaired_cross = lc._split_math(CROSS)
check("跨空行的 $ 不会被硬凑成一段公式",
      len(segs_cross) == 1 and CROSS[segs_cross[0].start:segs_cross[0].end] == "y=1"
      and len(unpaired_cross) == 1,
      f"段数={len(segs_cross)} 未配对={len(unpaired_cross)}")
check("跨空行时不会把正常的 $y=1$ 误报成公式错误",
      not any(i.is_error for i in lc.check_text(CROSS)),
      str([i.message for i in lc.check_text(CROSS)]))
check("跨空行里那个孤立的 $ 仍然会提醒",
      any("没有找到配对" in i.message for i in lc.check_text(CROSS)))

# 表格：$$...$$ 内部再写 $ 是硬错误（老师实际踩过的坑）
TABLE_BAD = ("$$\n"
             "\\begin{array}{|c|c|c|}\n"
             "\\hline\n"
             "声源 & 与声源的距离$/{\\rm m}$ & 声压级$/{\\rm dB}$\\\\\n"
             "\\hline\n"
             "\\end{array}\n"
             "$$")
TABLE_OK_RAW = ("$$\n"
                "\\begin{array}{|c|c|c|}\n"
                "\\hline\n"
                "声源 & 与声源的距离/{\\rm m} & 声压级/{\\rm dB}\\\\\n"
                "\\hline\n"
                "\\end{array}\n"
                "$$")
TABLE_OK_TEXT = ("$$\n"
                 "\\begin{array}{|c|c|c|}\n"
                 "\\hline\n"
                 "\\text{声源} & \\text{距离}/{\\rm m} & \\text{声压级}/{\\rm dB}\\\\\n"
                 "\\hline\n"
                 "\\end{array}\n"
                 "$$")

check("表格单元格里又写 $ 会被抓出来（会渲染成红字）",
      any("不能再写" in i.message for i in lc.check_text(TABLE_BAD)),
      str([i.message for i in lc.check_text(TABLE_BAD)])[:90])
check("把单元格里的 $ 去掉（中文直接写）就不报问题了",
      lc.check_text(TABLE_OK_RAW) == [],
      str([i.message for i in lc.check_text(TABLE_OK_RAW)])[:90])
check("中文用 \\text{} 包起来也不报问题",
      lc.check_text(TABLE_OK_TEXT) == [],
      str([i.message for i in lc.check_text(TABLE_OK_TEXT)])[:90])
check("公式里合法的 \\$ 不会被误报",
      lc.check_text(r"$\text{价格} \$5$") == [],
      str([i.message for i in lc.check_text(r"$\text{价格} \$5$")])[:90])
check("单个 $ 包起来的行内表格不报问题",
      lc.check_text(r"$\begin{array}{|c|c|} \hline \text{声源} & 10 \\ \hline \end{array}$") == [])

# 格式说明里给出的「JSON 里的表格示例」必须真的能解析、真的能渲染
from src.ui.import_page import TABLE_JSON_EXAMPLE  # noqa: E402

try:
    decoded = json.loads("{" + TABLE_JSON_EXAMPLE + "}")["stem"]
    dec_ok, dec_err = True, ""
except Exception as e:  # noqa: BLE001
    decoded, dec_ok, dec_err = "", False, f"{type(e).__name__}: {e}"
check("格式说明里的 JSON 表格示例是合法 JSON", dec_ok, dec_err)
if dec_ok:
    check("示例解码后就是一张能渲染的表格（\\n 变真换行、\\\\ 是表格换行）",
          decoded.startswith("$$") and "\\begin{array}" in decoded
          and decoded.count("\n") == 6 and "\\\\" in decoded
          and lc.check_text(decoded) == [],
          repr(decoded)[:80])

# ============================================================
# 一·补：导入页「格式说明 / 示例」里的示例必须真的能用
#        （文档和校验逻辑脱节是最容易发生的事，所以拿代码验一遍）
# ============================================================
from src.ui.import_page import SAMPLE_JSON  # noqa: E402

try:
    json.loads(SAMPLE_JSON)
    json_ok, json_err = True, ""
except Exception as e:  # noqa: BLE001
    json_ok, json_err = False, f"{type(e).__name__}: {e}"
check("格式说明里的示例是合法 JSON", json_ok, json_err)

rpt_sample = imp.parse_json_text(SAMPLE_JSON)
check("示例能直接通过校验：0 错误、0 提醒、0 重复、0 公式问题",
      rpt_sample.fatal_error == "" and rpt_sample.error_count == 0
      and all(not r.warnings for r in rpt_sample.rows)
      and rpt_sample.dup_count == 0 and rpt_sample.latex_count == 0,
      f"fatal={rpt_sample.fatal_error!r} 错误={rpt_sample.error_count} "
      f"提醒={[r.warnings for r in rpt_sample.rows]} 公式={rpt_sample.latex_count}")
check("示例里的反斜杠转义正确（解析出来是真 LaTeX，而不是双反斜杠）",
      "\\infty" in rpt_sample.rows[0].data["answer"]
      and "\\\\" not in rpt_sample.rows[0].data["answer"],
      repr(rpt_sample.rows[0].data["answer"])[:70])
check("示例里的 \\n 解析成了真正的换行",
      rpt_sample.rows[0].data["stem"].count("\n") == 2,
      repr(rpt_sample.rows[0].data["stem"])[:60])
check("示例里的选项解析正确",
      [o["text"] for o in rpt_sample.rows[1].data["options_list"]]
      == ["$y=-x$", "$y=x^2$", "$y=\\dfrac{1}{x}$", "$y=2^{-x}$"],
      str(rpt_sample.rows[1].data["options_list"]))
check("示例的字段都落到了该落的地方",
      rpt_sample.rows[0].data["qtype"] == "解答题"
      and rpt_sample.rows[0].data["difficulty"] == 4
      and rpt_sample.rows[0].data["knowledge"] == "导数,单调性"
      and rpt_sample.rows[1].data["qtype"] == "单选题"
      and rpt_sample.rows[1].data["difficulty"] == 2,
      f"{rpt_sample.rows[0].data['qtype']}/{rpt_sample.rows[0].data['knowledge']}")

# ============================================================
# 二、导入服务：数据层
# ============================================================
def payload(stem, **kw):
    row = {"grade": "高三", "chapter": "函数", "qtype": "解答题", "difficulty": 3,
           "stem": stem, "answer": "原答案", "analysis": "原解析",
           "source": "自测", "tags": "导入自测"}
    row.update(kw)
    return json.dumps([row], ensure_ascii=False)


# 2.1 坏公式：能入库，但报告里带着公式问题
rpt = imp.parse_json_text(payload(BAD_STEM))
check("坏公式的题目仍可通过字段校验（公式问题只提醒不阻断）", rpt.ok_count == 1)
check("RowReport 带上了 latex_issues",
      rpt.rows[0].has_latex_issue and rpt.rows[0].latex_error_count == 1,
      str(rpt.rows[0].latex_issues))
check("ParseResult 统计出公式有问题的条数", rpt.latex_count == 1 and rpt.latex_error_count == 1)

rpt_ok = imp.parse_json_text(payload(GOOD_STEM))
check("修好的公式不产生公式问题", not rpt_ok.rows[0].has_latex_issue)

# 2.2 先造一道带配图的题，待会儿用它测覆盖
with_image = qs.create_question({
    "qtype": "解答题", "grade": "高三", "chapter": "函数", "difficulty": 2,
    "stem": GOOD_STEM, "answer": "旧答案", "analysis": "旧解析",
    "source": "自测", "tags": "旧标签",
    "options_list": [], "image_list": ["images/stem_only.png"],
})
check("造题成功且带配图", qs.get_question(with_image).image_list == ["images/stem_only.png"])

new_payload = payload(GOOD_STEM, answer="新答案", analysis="新解析",
                      difficulty=5, tags="新标签", source="新来源")

# 2.3 skip：跳过重复
rpt_dup = imp.parse_json_text(new_payload)
check("同题干会被判重", rpt_dup.rows[0].is_duplicate
      and with_image in rpt_dup.rows[0].duplicate_ids,
      str(rpt_dup.rows[0].duplicate_ids))
stats = imp.commit_import(rpt_dup.rows, on_duplicate="skip")
q = qs.get_question(with_image)
check("skip 模式：一条都没新增、也没改动原题",
      stats["inserted"] == 0 and stats["skipped_dup"] == 1 and stats["updated"] == 0
      and q.answer == "旧答案", str(stats))

# 2.4 insert：照样新增一份
rpt_dup2 = imp.parse_json_text(new_payload)
stats = imp.commit_import(rpt_dup2.rows, on_duplicate="insert")
same = [x for x in dc.list_questions() if x.stem == GOOD_STEM]
check("insert 模式：库里出现两条同题干（老行为不变）",
      stats["inserted"] == 1 and len(same) == 2, f"{stats} 同题干 {len(same)} 条")
for x in same:
    if x.id != with_image:
        qs.hard_delete_question(x.id)

# 2.5 overwrite：原地覆盖，id 不变、配图保留、内容更新
rpt_dup3 = imp.parse_json_text(new_payload)
stats = imp.commit_import(rpt_dup3.rows, on_duplicate="overwrite")
q = qs.get_question(with_image)
check("overwrite 模式：统计里是覆盖 1 条，不是新增",
      stats["updated"] == 1 and stats["inserted"] == 0, str(stats))
check("overwrite 模式：题目编号没变", q is not None and q.id == with_image)
check("overwrite 模式：答案/解析/难度/标签都换成了导入的内容",
      q.answer == "新答案" and q.analysis == "新解析"
      and q.difficulty == 5 and q.tag_list == ["新标签"] and q.source == "新来源",
      f"{q.answer}/{q.analysis}/{q.difficulty}/{q.tags}/{q.source}")
check("overwrite 模式：原题配图没有被清掉（导入 JSON 里没有图片信息）",
      q.image_list == ["images/stem_only.png"], str(q.image_list))

# 2.5b 选项形状：新增和覆盖必须完全一致（导入语义，不是编辑器语义）
opts_payload = json.dumps([{
    "stem": "选项形状一致性测试题", "qtype": "多选题", "difficulty": 3,
    "options": "A. 甲\nB. 乙\nC. 丙\nD. 丁",
}], ensure_ascii=False)
imp.commit_import(imp.parse_json_text(opts_payload).rows, on_duplicate="insert")
opts_row = [x for x in dc.list_questions() if x.stem == "选项形状一致性测试题"]
check("解析出的选项就是 JSON 里写的那几个",
      [o["text"] for o in opts_row[0].options_list] == ["甲", "乙", "丙", "丁"],
      str(opts_row[0].options_list))
imp.commit_import(imp.parse_json_text(opts_payload).rows, on_duplicate="overwrite")
after_opts = qs.get_question(opts_row[0].id).options_list
check("覆盖导入写进去的选项和新增导入一模一样（不会凭空多出空选项）",
      after_opts == opts_row[0].options_list, str(after_opts))
for x in opts_row:
    qs.hard_delete_question(x.id)

# 2.6 覆盖后缓存立刻失效（列表页要马上看到新内容，不能等重启）
dc.list_questions(limit=50)
rpt_dup4 = imp.parse_json_text(payload(GOOD_STEM, answer="覆盖后的答案"))
imp.commit_import(rpt_dup4.rows, on_duplicate="overwrite")
check("覆盖后 list_questions 立刻返回新答案",
      any(x.id == with_image and x.answer == "覆盖后的答案" for x in dc.list_questions()))

# 2.7 旧参数兼容（老代码用 skip_duplicates 的地方不能坏）
rpt_dup5 = imp.parse_json_text(payload(GOOD_STEM))
stats = imp.commit_import(rpt_dup5.rows, skip_duplicates=True)
check("旧的 skip_duplicates=True 仍然等价于跳过重复",
      stats["skipped_dup"] == 1 and stats["inserted"] == 0, str(stats))
stats = imp.commit_import(rpt_dup5.rows, skip_duplicates=False)
check("旧的 skip_duplicates=False 仍然等价于照样新增",
      stats["inserted"] == 1, str(stats))
for x in [x for x in dc.list_questions() if x.stem == GOOD_STEM and x.id != with_image]:
    qs.hard_delete_question(x.id)

# ============================================================
# 三、界面层：导入页
# ============================================================
dc.bump()
at = AppTest.from_file(APP, default_timeout=30)
at.run()
at.sidebar.radio[0].set_value(PAGE).run()
check("导入页能打开", not at.exception, str(at.exception))

# 「格式说明 / 示例」这一栏就是导入格式的规范，内容不能少
spec_md = md_all(at)
for must in ("整体结构", "字段一览", "逐字段细则", "查重规则", "LaTeX 与公式"):
    check(f"格式说明里有「{must}」一节", must in spec_md)
check("格式说明写清了必填项与默认值",
      "必填" in spec_md and "解答题" in spec_md and "选填" in spec_md)
check("格式说明写清了只支持 A~D 四个选项",
      "只认 A~D 四个字母" in spec_md)
check("格式说明写清了反斜杠要写两个、换行写 \\n",
      "反斜杠要写两个" in spec_md and "换行写" in spec_md)
check("格式说明写清了同批重复不会互相判重",
      "不会互相判重" in spec_md)
check("格式说明有「表格怎么写」一节", "表格怎么写" in spec_md)
check("格式说明写清了 $ 里面不能再写 $",
      "里面不能再出现" in spec_md and "Can't use function" in spec_md)
check("格式说明给了两种表格包法和 JSON 写法示例",
      "整张表独占一行" in spec_md and "跟在文字后面" in spec_md
      and "在 JSON 里长什么样" in spec_md)

bad_json = json.dumps([{
    "grade": "高三", "qtype": "解答题", "difficulty": 4,
    "stem": BAD_STEM, "answer": "答案", "analysis": "解析",
}], ensure_ascii=False)

at.text_area(key="import_textarea").set_value(bad_json)
at.button(key="import_btn_parse").click().run()
check("界面解析后不报错", not at.exception, str(at.exception))

page_md = md_all(at)
check("页面上出现了公式问题的提示（会说会变成红字）",
      "红字" in page_md or "公式" in page_md, page_md[:80])
check("页面上出现了「自动修复公式」按钮",
      any((b.key or "") == "import_btn_fix_latex" for b in at.button),
      str([b.key for b in at.button]))
check("指标区显示了「公式有问题」", any(m.label == "公式有问题" for m in at.metric),
      str([m.label for m in at.metric]))
check("表格状态列标出了 🔴 公式红字",
      "🔴 公式红字" in at.dataframe[0].value.to_string(),
      at.dataframe[0].value.to_string()[:120])
check("本次没有重复题时，重复处理单选是禁用的",
      at.radio(key="import_dup_mode").disabled)

# 点自动修复 → 文本框内容真的被改写
at.button(key="import_btn_fix_latex").click().run()
check("点自动修复后不报错", not at.exception, str(at.exception))
text_now = at.session_state["import_textarea"]
check("自动修复改写了文本框里的公式",
      "*{35}" not in text_now and r"\begin{array}{ll" in text_now,
      text_now[text_now.find("begin{array"):][:40])
check("修复后重新校验，页面不再报公式红字",
      not any((b.key or "") == "import_btn_fix_latex" for b in at.button),
      str([b.key for b in at.button]))

# ---- 重复题：处理方式可选，覆盖模式有二次提醒 ----
dup_json = json.dumps([{
    "grade": "高三", "qtype": "解答题", "difficulty": 4,
    "stem": GOOD_STEM, "answer": "界面用的答案", "analysis": "界面用的解析",
}], ensure_ascii=False)
at.text_area(key="import_textarea").set_value(dup_json)
at.button(key="import_btn_parse").click().run()
check("重复题会被判重并显示在页面上", int(at.metric[3].value) >= 1,
      f"与库内重复={at.metric[3].value}")
mode_radio = at.radio(key="import_dup_mode")
check("重复题出现「处理方式」单选，三个选项都在",
      set(mode_radio.options) == set(imp.DUPLICATE_MODE_LABELS.values()),
      str(mode_radio.options))
check("处理方式默认是「跳过重复」", mode_radio.value == "skip", str(mode_radio.value))

at.radio(key="import_dup_mode").set_value("overwrite").run()
check("切到「覆盖」模式后页面不报错", not at.exception, str(at.exception))
check("覆盖模式给出了不可还原的提醒",
      any("覆盖" in w.value for w in at.warning), str([w.value for w in at.warning])[:1])
check("覆盖模式默认先整库备份", at.checkbox(key="import_backup_first").value is True)
check("入库按钮文案说明了会覆盖",
      any("覆盖" in (b.label or "") for b in at.button),
      str([b.label for b in at.button]))

# ============================================================
# 四、界面层：题目编辑器里也提醒公式问题
# ============================================================
at2 = AppTest.from_file(APP, default_timeout=30)
at2.run()
at2.sidebar.radio[0].set_value("📚  题目管理").run()
at2.button(key="edit_1").click().run()
check("能进入题目编辑表单", not at2.exception, str(at2.exception))

at2.text_area(key="q_edit_stem").set_value(BAD_STEM).run()
check("编辑器实时提醒「公式会渲染成红字」",
      any("红字" in (c.value or "") for c in at2.caption),
      str([c.value for c in at2.caption if "公式" in (c.value or "")])[:120])
check("编辑器给出「自动修复公式」按钮",
      any((b.key or "") == "q_edit_latex_stem" for b in at2.button),
      str([b.key for b in at2.button]))

at2.button(key="q_edit_latex_stem").click().run()
check("编辑器里自动修复改写了题干",
      "*{35}" not in at2.session_state["q_edit_stem"], )
check("修复后编辑器不再提示公式问题",
      not any((b.key or "") == "q_edit_latex_stem" for b in at2.button),
      str([b.key for b in at2.button]))

# ============================================================
# 五、逐条预览与修改（草稿层）＋ 配图随导入入库
# ============================================================
from src.config import IMAGES_DIR  # noqa: E402
from src.services import import_service as imp2  # noqa: E402
from src.utils import file_utils as fu  # noqa: E402


def probe_png(color=(10, 20, 30)) -> bytes:
    """造一张真的能被 PIL 打开的 png（上传通道会校验图片格式）。"""
    import io as _io
    from PIL import Image
    buf = _io.BytesIO()
    Image.new("RGB", (24, 16), color).save(buf, format="PNG")
    return buf.getvalue()


def drafts_of(at):
    return at.session_state.get("import_drafts") or []


def rows_of(at):
    return [d.report for d in drafts_of(at)]


def staged_files():
    root = imp2.staging_dir()
    return [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else []


# 先造一道"库里已有"的题，用来验证「在草稿里改完题干后会按新题干重新查重」。
# 注意：删除它必须等到"停止编辑"之后 —— 这道题得一直活着，
# 否则重新查重查的是一道已经不在库里的题，测出来的结果是假的。
DUP_STEM = "草稿重查重用的题干（自测）"
dup_qid = qs.create_question({
    "qtype": "解答题", "grade": "高三", "chapter": "自测", "difficulty": 3,
    "stem": DUP_STEM, "answer": "旧", "analysis": "旧",
})
dc.bump()

at3 = AppTest.from_file(APP, default_timeout=60)
at3.run()
at3.sidebar.radio[0].set_value(PAGE).run()

draft_json = json.dumps([
    {"grade": "高二", "chapter": "草稿自测", "qtype": "解答题", "difficulty": 3,
     "stem": "草稿页自测第一题 $a^2+b^2$", "answer": "答案一", "analysis": "解析一",
     "knowledge": "自测", "tags": "草稿"},
    {"grade": "高二", "chapter": "草稿自测", "qtype": "填空题", "difficulty": 2,
     "stem": "草稿页自测第二题", "answer": "答案二", "analysis": "解析二"},
], ensure_ascii=False)

at3.text_area(key="import_textarea").set_value(draft_json)
at3.button(key="import_btn_parse").click().run()
check("解析后为每一条建立了草稿", len(drafts_of(at3)) == 2, str(len(drafts_of(at3))))
check("页面上出现了「逐条预览与修改」这一栏",
      "逐条预览与修改" in md_all(at3), md_all(at3)[:80])

# ---- 预览：核实真的渲染了，而不只是"没报错" ----
at3.button(key="import_btn_edit_0").click().run()
check("能进入草稿编辑", not at3.exception, str(at3.exception))
preview_md = "\n".join(m.value for m in at3.markdown)
check("预览区把题干交给渲染层了（含 LaTeX）",
      "草稿页自测第一题" in preview_md and "$a^2+b^2$" in preview_md,
      preview_md[:120])
check("预览区有答案与解析的折叠面板",
      any("答案与解析" in (e.label or "") for e in at3.expander),
      str([e.label for e in at3.expander])[:140])
check("预览用的是题目卡片那套容器（字号 / 字体跟题库统一）",
      any("qdisp_" in str(getattr(el, "key", "")) for el in at3.container),
      str([getattr(el, "key", None) for el in at3.container])[:140])

# ---- 编辑：改成与库里重复的题干，必须按新题干重新查重 ----
at3.text_area(key="import_d_stem").set_value(DUP_STEM).run()
check("草稿里改题干后按**新**题干重新查重",
      rows_of(at3)[0].is_duplicate and dup_qid in rows_of(at3)[0].duplicate_ids,
      f"dup={rows_of(at3)[0].is_duplicate} ids={rows_of(at3)[0].duplicate_ids}")
at3.run()      # 重跑一次：表格渲染的是上一轮的快照，重跑后才反映刚改过的题干
dup_table = at3.dataframe[0].value.to_string()
check("重新查重后列表里标出与库内重复（状态 / 备注列）",
      "⚠️ 重复" in dup_table or f"#{dup_qid} 重复" in dup_table,
      dup_table.replace("\n", " | ")[:200])

# ---- 编辑：写坏公式 → 当场体检 → 一键修复 ----
at3.text_area(key="import_d_stem").set_value(BAD_STEM).run()
check("草稿里写坏公式会被当场查出来（会渲染成红字）",
      rows_of(at3)[0].latex_error_count == 1,
      str([(a, b.message) for a, b in rows_of(at3)[0].latex_issues]))
check("草稿给出「修复本条的公式」按钮",
      any((b.key or "") == "import_btn_fix_draft" for b in at3.button),
      str([b.key for b in at3.button]))
at3.button(key="import_btn_fix_draft").click().run()
check("点修复后草稿里的公式被改写、且不再报公式问题",
      "*{35}" not in at3.session_state["import_d_stem"]
      and not rows_of(at3)[0].has_latex_issue,
      repr(at3.session_state.get("import_d_stem"))[:70])

# ---- 配图：上传后只进暂存目录，确认入库前不动正式目录 ----
before_images = {p.name for p in IMAGES_DIR.glob("*") if p.is_file()}
at3.file_uploader(key="import_d_stem_uploader").set_value(
    ("draft_img.png", probe_png(), "image/png")).run()
check("上传配图后不报错", not at3.exception, str(at3.exception))
check("草稿记下了这张配图", drafts_of(at3)[0].image_count == 1,
      str(drafts_of(at3)[0].images))
check("配图暂时只落在暂存目录里", len(staged_files()) == 1,
      str([p.name for p in staged_files()]))
check("确认入库前没有任何文件进入正式图片目录",
      {p.name for p in IMAGES_DIR.glob("*") if p.is_file()} == before_images,
      str(sorted({p.name for p in IMAGES_DIR.glob("*") if p.is_file()}))[:140])
check("缩略图下方给出了可复制的定位标记",
      "![[img]]" in "\n".join(c.value for c in at3.code),
      str([c.value for c in at3.code])[:80])

# ---- 同一张图重复上传不该变成两张（按内容指纹去重）----
at3.file_uploader(key="import_d_stem_uploader").set_value(
    ("draft_img.png", probe_png(), "image/png")).run()
check("同一张图重复上传仍然只有一张",
      drafts_of(at3)[0].image_count == 1, str(drafts_of(at3)[0].image_count))

# ---- 最后一次编辑：把标记插进正文（同时把修好的公式留在正文里）----
FINAL_STEM = "配图题：![[img]] 在文字中间\n\n" + GOOD_STEM
at3.text_area(key="import_d_stem").set_value(FINAL_STEM).run()
check("文字里写了标记后提示「已安置」",
      any("安置" in (c.value or "") for c in at3.caption),
      str([c.value for c in at3.caption if "安置" in (c.value or "")]))
check("最后改的正文确实进了草稿（不是只改了输入框）",
      rows_of(at3)[0].data["stem"] == FINAL_STEM,
      repr(rows_of(at3)[0].data["stem"])[:50])

# ---- 回到整体预览并入库 ----
at3.button(key="import_btn_stop_edit").click().run()
check("可以退出单条编辑回到整体预览", at3.session_state.get("import_edit_idx") is None)
check("停止编辑后草稿保留最后一次改过的正文",
      rows_of(at3)[0].data["stem"] == FINAL_STEM,
      repr(rows_of(at3)[0].data["stem"])[:50])
at3.button(key="import_btn_commit").click().run()
check("带草稿编辑的导入不报错", not at3.exception, str(at3.exception))
check("导入完成后暂存目录被清空（不留垃圾图片）", not staged_files(),
      str([p.name for p in staged_files()]))

imported = [q for q in dc.list_questions() if q.chapter == "草稿自测"]
check("两条草稿都入库了", len(imported) == 2,
      str([(q.id, q.stem[:12]) for q in imported]))
with_img = [q for q in imported if q.image_list]
check("配图跟着题目一起入库了", len(with_img) == 1,
      str([(q.id, q.image_list) for q in imported]))
if with_img:
    rel = fu.real_image_path(with_img[0].image_list[0])
    check("入库后图片落在正式图片目录里、文件真的存在",
          rel.startswith("images/") and "_import_staging" not in rel
          and fu.abs_path(rel).is_file(), rel)
    check("正文里的 ![[img]] 标记和入库的图片对得上",
          "![[img]]" in with_img[0].stem, with_img[0].stem)
    check("草稿里改过的正文（含修复后的公式）原样入库",
          with_img[0].stem == FINAL_STEM, repr(with_img[0].stem)[:50])

# 清理：删掉本次自测造出来的题（含刚入库的图片文件）
for q in imported:
    for rel in q.image_list:
        fu.delete_file_silently(fu.real_image_path(rel))
    qs.hard_delete_question(q.id)
qs.hard_delete_question(dup_qid)
dc.bump()

# ------------------------------------------------------------
# 六、兜底清理入口：直接关掉浏览器后遗留的草稿图片能一键清掉
# ------------------------------------------------------------
leftover = imp2.staging_subdir("selftest_leftover")
leftover.mkdir(parents=True, exist_ok=True)
(leftover / "leftover.png").write_bytes(b"x")
at4 = AppTest.from_file(APP, default_timeout=60)
at4.run()
at4.sidebar.radio[0].set_value("⚙️  系统设置").run()
check("设置页有清理导入草稿图片的入口",
      any((b.key or "") == "set_clear_staging" for b in at4.button),
      str([b.key for b in at4.button])[:160])
check("清理入口说明了有多少遗留文件",
      any("草稿图片文件" in (c.value or "") for c in at4.caption),
      str([c.value for c in at4.caption if "草稿" in (c.value or "")])[:120])
at4.button(key="set_clear_staging").click().run()
check("点清理后草稿图片真的被删掉", not staged_files(),
      str([p.name for p in staged_files()]))


# ------------------------------------------------------------
print("\n================ 汇总 ================")
bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
print(f"\n{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
