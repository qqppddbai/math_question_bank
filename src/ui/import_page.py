# -*- coding: utf-8 -*-
"""批量导入页面：粘贴 JSON / 上传文件 → 校验预览 → **逐条预览与修改** → 一键入库。

关键约定：
- text_area 的唯一数据源是 st.session_state["import_textarea"]；
- 所有对它的写入都在 on_click / on_change 回调里做（回调早于 widget 渲染）；
- 主流程只读取，不再赋值，避免 Streamlit 抛 "widget already instantiated"。

关于「④ 逐条预览与修改」（草稿层）：
- 解析成功后，每条题目都会复制一份可编辑的**草稿**，与原始 JSON 脱钩；
  在草稿里改内容、加配图**不会**回写上面那个 JSON 文本框（免得两边互相打架）。
  想改 JSON 就得重新解析，那会重建草稿。
- 草稿图片先落在 data/images/_import_staging/<n>/ 暂存，点「确认入库」时才
  复制进正式图片目录；取消 / 重新解析 / 丢弃草稿都会把暂存目录删掉。
- 只渲染当前正在编辑的那一条（题目卡片含 KaTeX 和图片，一次渲染几十条会很卡）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from src.config import CHOICE_TYPES, DIFFICULTY_LABELS, GRADES, OPTION_KEYS, QTYPES
from src.services import backup_service
from src.services import import_service as imp
from src.ui import question_card as qc
from src.utils import file_utils
from src.utils import latex_check
from src.utils.latex import strip_latex_for_preview
from src.utils.rich_text import marker_syntax, placement_report

SS = "import_"
TEXT_KEY = SS + "textarea"     # text_area 的 key，也是唯一数据源

# 草稿编辑区所有 widget key 的前缀。
# 刻意用 impd_ 而不是 q_edit_：那样即使老师同时开着题目管理页的编辑表单，
# 两边的 session_state 也不会互相踩。
DRAFT_PREFIX = SS + "d_"

SAMPLE_JSON = r'''[
  {
    "grade": "高三",
    "chapter": "函数与导数",
    "knowledge": "导数,单调性",
    "qtype": "解答题",
    "difficulty": 4,
    "stem": "已知函数 $f(x)=x^3-3x$。\n(1) 求 $f(x)$ 的单调区间；\n(2) 若方程 $f(x)=a$ 有三个不同的实根，求 $a$ 的取值范围。",
    "options": "",
    "answer": "(1) 在 $(-\\infty,-1)$ 和 $(1,+\\infty)$ 上单调递增，在 $(-1,1)$ 上单调递减；\n(2) $-2<a<2$",
    "analysis": "求导得 $f'(x)=3x^2-3=3(x-1)(x+1)$，列表判断导数符号即可。",
    "source": "2024年自编",
    "tags": "导数,单调性"
  },
  {
    "grade": "高一",
    "chapter": "函数",
    "knowledge": "函数单调性",
    "qtype": "单选题",
    "difficulty": 2,
    "stem": "下列函数中，在 $(0,+\\infty)$ 上单调递增的是（　　）",
    "options": "A. $y=-x$\nB. $y=x^2$\nC. $y=\\dfrac{1}{x}$\nD. $y=2^{-x}$",
    "answer": "B",
    "analysis": "$y=x^2$ 在 $(0,+\\infty)$ 上单调递增，其余三个都递减。",
    "source": "",
    "tags": ""
  }
]'''


# 表格在 JSON 里的写法示例。它既是文档的一部分，也会被自测拿去实际解析一遍，
# 确保里面 `\n` / `\\` / `\\\\` 的转义写对了（写错的话老师照抄就会踩坑）。
TABLE_JSON_EXAMPLE = (
    r'"stem": "$$\n\\begin{array}{|c|c|}\n\\hline\n\\text{甲} & 1\\\\\n'
    r'\\hline\n\\end{array}\n$$"'
)


# ============================================================
# 格式说明（这一栏就是导入格式的「规范」，与 import_service 的校验保持一致）
# 写的是代码里真实发生的行为，不是"应该怎样"；改校验逻辑时请一起改这里。
# ============================================================
_FORMAT_SPEC = r"""
### 一、整体结构

- 最外层是 **JSON 数组**：`[ {…}, {…} ]`。只导入一条时，也可以直接写单个对象 `{…}`。
- 数组里**每一条必须是一个 JSON 对象** `{ }`；写成字符串或数组的那一条会报「该条不是 JSON 对象」。
- 内容为空、数组为空、JSON 语法不合法 → **整体拒绝**，一条都不会入库。
- 字段名**区分大小写**（`stem` 不能写成 `Stem`）；表里没有的字段会被**忽略**（写了不报错）。

### 二、字段一览

| 字段 | 类型 | 必填 | 不填时按 | 说明 |
|---|---|---|---|---|
| `stem` | 字符串 | **必填** | — | 题干。空、或只有空白字符 → **该条被拒绝** |
| `qtype` | 字符串 | 选填 | `解答题` | 只能是：单选题 / 多选题 / 填空题 / 解答题 / 判断题 / 作图题 |
| `difficulty` | 数字 | 选填 | `3` | 1~5，细则见下 |
| `options` | 字符串或数组 | 选择题建议填 | 空 | 两种写法见下 |
| `grade` | 字符串 | 选填 | 空 | 年级，如 `高三`、`初一` |
| `chapter` | 字符串 | 选填 | 空 | 章节，如 `导数` |
| `knowledge` | 字符串或数组 | 选填 | 空 | 知识点，如 `"函数,导数"` |
| `tags` | 字符串或数组 | 选填 | 空 | 标签，如 `"高考真题,新高考II卷"` |
| `answer` | 字符串 | 选填 | 空 | 答案，支持 LaTeX |
| `analysis` | 字符串 | 选填 | 空 | 解析，支持 LaTeX |
| `source` | 字符串 | 选填 | 空 | 来源，如 `2023年新课标全国Ⅱ卷` |

**只有以下三种情况会让某一条被拒绝**（其余一律放行，最多给个提醒）：
`stem` 为空 · `qtype` 不在上面 6 个之内 · `difficulty` 完全读不成数字。

### 三、逐字段细则

**`difficulty`（难度）**

- 可以写数字 `4`、字符串 `"4"`、小数 `4.7`（向下取整成 `4`）。
- 不填、写 `null`、写 `""` → 按 `3` 处理。
- 超出 1~5 **不报错，会被夹到边界**：`0`、`-3` → `1`；`9` → `5`。
- 完全读不成数字的（如 `"abc"`）→ **该条被拒绝**。

**`options`（选项）** —— 两种写法二选一：

1. **多行文本**（推荐）：`"A. 甲\nB. 乙\nC. 丙\nD. 丁"`
   - 标签写法很宽松，`A.` / `A、` / `（A）` / `A)` / `A：` 都能识别；
   - 一行都不带标签时，按出现顺序自动补成 A、B、C、D。
2. **对象数组**：`[{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}]`

注意：

- **只认 A~D 四个字母**（和编辑器里的四个空位一致）。写到第 5 行 `E. 戊` 不会被当成选项，
  会连着字母原样保留成一段文字 —— **五个选项的题请先压成 4 个再导入**。
- `["A. 甲", "B. 乙"]` 这种**字符串数组不支持**，会解析成空选项；选择题因此会得到
  「选项少于 2 个」的提醒。
- 单选题 / 多选题的选项少于 2 个 → **只提醒，不拒绝**。

**`knowledge` / `tags`**

- 逗号分隔的字符串 `"函数,导数"`，或字符串数组 `["函数", "导数"]`，两种等价，都会存成 `函数,导数`。
- **只认英文半角逗号**；中文逗号 `，` 不会被当成分隔符。

**其它**

- 所有字段都按字符串处理：`grade` 写数字 `5` 会变成文本 `"5"`。请按表里的类型填。
- 导入格式里**没有图片字段**：写了 `image_list`、`images` 之类也会被忽略。
  配图在解析后的「③ 逐条预览与修改」里加，详见第六节。

### 四、查重规则

- 判定依据是**题干**：把所有空白字符（空格、换行、制表符）去掉后完全相同，就算重复。
  所以「同一道题」和「同 一 道 题」会被判为重复。
- **只跟题库里已有的题目比较**。同一批 JSON 里出现两条相同题干，**不会互相判重**，
  两条都会入库 —— 导入前请先去重。
- 遇到重复时在页面上选处理方式：

| 处理方式 | 行为 |
|---|---|
| **跳过重复**（默认） | 题库里已有的不动，只导入新题 |
| **覆盖题库里的原题** | 原地改写那道题，**题目编号不变**，试卷引用和学生错题关联都不会断 |
| **照样新增一份** | 不管重复，直接再建一条（题库里会出现重复题） |

- 覆盖**不会动原题已有的配图**；覆盖**不可撤销**（回收站里没有旧版本），所以覆盖模式下
  默认会先做一次整库备份。

### 五、LaTeX 与公式

- `stem` / `options` / `answer` / `analysis` 里的公式都用 LaTeX，写法与网页上完全一致：
  行内用单个 `$`（例：`$x^2$`），独立公式用 `$$`。
- **JSON 里的反斜杠要写两个**：LaTeX 的 `\sin` 在 JSON 文本里必须写成 `\\sin`。
- **换行写 `\n`**，不要在 JSON 字符串里直接按回车（JSON 不允许字符串跨行）。
- 导入前会自动做一次**公式体检**：KaTeX 渲染不了的写法（例如公式编辑器导出的
  `\begin{array}{*{35}{l}}`）在页面上会变成红字，校验结果会指出具体是哪一处、并能一键修复。
  公式问题**只提醒、不阻断**。

### 六、图片：在"逐条预览与修改"里加（不需要写进 JSON）

- 导入格式里**没有图片字段**：写了 `image_list`、`images` 之类也会被忽略。
- 配图在解析后的 **「③ 逐条预览与修改」** 里加：进入某一条 → 找到「配图」区 →
  分别上传**题干配图**和**解析配图** → 从缩略图下面复制定位标记 `![[img]]`、
  `![[img:2]]`（要指定宽度写 `![[img:2|300]]`）→ 粘到文字里想放图片的位置。
  **不写标记的图片会排在文字最后。**
- 序号是**该字段内的序号**：题干里的 `![[img:2]]` 指题干配图的第 2 张，
  解析里的指解析配图的第 2 张，两组互不干扰。
- 上传的图片在点「确认入库」之前只放在暂存目录里；**取消、重新解析、刷新页面
  都不会在 data/images/ 里留下垃圾文件**。

### 七、表格怎么写（`array` 环境）

公式表格用 LaTeX 的 `array` 环境，**两种包法都可以**：

**① 整张表独占一行（推荐）** —— 用 `$$` 包起来：

```
$$
\begin{array}{|c|c|c|}
\hline
\text{声源} & \text{与声源的距离}/{\rm m} & \text{声压级}/{\rm dB}\\
\hline
\text{燃油汽车} & 10 & 60 \sim 90\\
\hline
\text{电动汽车} & 10 & 40\\
\hline
\end{array}
$$
```

**② 表格跟在文字后面** —— 用单个 `$` 包起来，**整张表必须写在同一行**（不能有真换行）：

```
$\begin{array}{|c|c|} \hline \text{声源} & 10 \\ \hline \end{array}$
```

**⚠️ 最容易踩的一条：`$` 里面不能再出现 `$`**

`$$...$$` 和 `$...$` 内部**已经是数学模式**了，再写一个 `$` 会直接报错、整段变成红字：

| 单元格里的写法 | 结果 |
|---|---|
| `声源 & 距离$/{\rm m}$ & 声压级$/{\rm dB}$\\` | ❌ 红字：`Can't use function '$' in math mode` |
| `\text{声源} & \text{距离}/{\rm m} & \text{声压级}/{\rm dB}\\` | ✅ 正常 |

单位、正负号这些**直接写在单元格里**（`/{\rm m}`、`\sim`、`\pm`）—— 你本来就在数学模式里，
不需要再用 `$` 切一次。确实要显示美元符号时写 `\$`。

**其余规则**

- **换行写 `\\`**（两个反斜杠），也就是每一行数据末尾写 `\\`；在 JSON 里要写成 `\\\\`。
- **单元格之间用 `&` 分隔**。列格式 `{|c|c|c|}` 表示 3 列，行里就用 2 个 `&` 分开 3 格。
  数量不一致 KaTeX 不会报错，但排版会不整齐。
- `\hline` 画横线、`|` 画竖线，都可以按需增删；最后一行后面不写 `\\` 也可以。
- **中文可以直接写在公式里**（能正常渲染），也可以用 `\text{...}` 包起来 —— 后者字距更规整，推荐。

**在 JSON 里长什么样**

上面 ① 那张表写进 `stem` 字段时是这样（`\n` 是 JSON 的换行符，`\\\\` 才是表格里的换行 `\\`）：

```json
""" + TABLE_JSON_EXAMPLE + r"""
```
"""


# ============================================================
# 状态初始化
# ============================================================
def _init_state():
    st.session_state.setdefault(TEXT_KEY, "")
    st.session_state.setdefault(SS + "report", None)
    st.session_state.setdefault(SS + "dup_mode", "skip")
    st.session_state.setdefault(SS + "backup_first", True)
    st.session_state.setdefault(SS + "drafts", [])
    # 正在编辑的草稿下标；None 表示「只做整体预览，不逐条编辑」
    st.session_state.setdefault(SS + "edit_idx", None)
    # 本次会话的暂存目录标识。
    # 每一次「解析」都换一个新的：否则上一批草稿留在
    # data/images/_import_staging/<下标>/ 里的图片，会被下一批同下标的草稿
    # 当成"自己的图"显示出来（路径一模一样，但内容已经不是那张图了）。
    if not st.session_state.get(SS + "stage_token"):
        import uuid
        st.session_state[SS + "stage_token"] = uuid.uuid4().hex[:8]
    # 防止「上一次的草稿图片暂存」在页面重启后一直留在磁盘上。
    # 如果上一次留下的暂存目录还在，第一次运行就顺手清掉。
    if not st.session_state.get(SS + "guard_done"):
        st.session_state[SS + "guard_done"] = True
        try:
            imp.clear_staging()
        except Exception:                       # noqa: BLE001 —— 清理失败不该拦住页面
            pass


# ============================================================
# 草稿：结构、插入与字段同步
# ============================================================
@dataclass
class Draft:
    """一条可编辑的导入草稿。

    字段语义与 src/services/import_service.py 里「规范化后的 data」完全一致，
    所以入库时不需要任何转换；这里额外挂上图片和暂存指纹。

    - report  ：这一条的校验结果（校验状态、公式问题、查重结果都在上面）
    - images  ：{组名: [图片相对路径]}，组名 stem / analysis
    - staging ：{组名: [已暂存图片的内容指纹]}，用来给上传去重
    """
    report: imp.RowReport
    images: dict = field(default_factory=lambda: {"stem": [], "analysis": []})
    staging: dict = field(default_factory=lambda: {"stem": [], "analysis": []})

    @property
    def data(self) -> dict:
        return self.report.data

    @property
    def image_count(self) -> int:
        """本条草稿有多少张配图（表格里用来提示"这条带图"）。"""
        return len(self.images["stem"]) + len(self.images["analysis"])

    def all_images(self) -> list:
        """题干图 + 解析图 → 待入库的图片数组（解析图带 analysis: 前缀）。"""
        return file_utils.join_images(self.images["stem"], self.images["analysis"])


def _clear_draft_widgets():
    """清掉草稿编辑区的 widget 状态（切换编辑对象时必须做）。

    否则在 A 条上填的内容会原样出现在 B 条的输入框里 —— Streamlit 的
    widget 值一旦建立就按 key 复用，不会因为渲染位置变了而自动重置。
    """
    for k in list(st.session_state.keys()):
        if k.startswith(DRAFT_PREFIX):
            del st.session_state[k]


def _clear_drafts():
    """丢弃所有草稿（重新解析 / 清空内容时调用），并清掉暂存图片。"""
    _clear_draft_widgets()
    st.session_state[SS + "drafts"] = []
    st.session_state[SS + "edit_idx"] = None
    try:
        imp.clear_staging()
    except Exception:                           # noqa: BLE001
        pass


def _sync_draft_fields(dr: Draft) -> None:
    """把编辑框里的值写回草稿数据。

    必须在 widget 渲染**之后**调用：这时 st.session_state 里已经是老师
    刚改过的值，直接取值即可，不需要绑定一堆 on_change 回调。
    """
    d = dr.data
    d["stem"] = st.session_state.get(DRAFT_PREFIX + "stem", d.get("stem", ""))
    d["answer"] = st.session_state.get(DRAFT_PREFIX + "answer", d.get("answer", ""))
    d["analysis"] = st.session_state.get(DRAFT_PREFIX + "analysis", d.get("analysis", ""))
    d["grade"] = st.session_state.get(DRAFT_PREFIX + "grade", d.get("grade", ""))
    d["chapter"] = st.session_state.get(DRAFT_PREFIX + "chapter", d.get("chapter", ""))
    d["difficulty"] = st.session_state.get(DRAFT_PREFIX + "difficulty", d.get("difficulty", 3))
    d["source"] = st.session_state.get(DRAFT_PREFIX + "source", d.get("source", ""))
    d["knowledge"] = st.session_state.get(DRAFT_PREFIX + "knowledge", d.get("knowledge", ""))
    d["tags"] = st.session_state.get(DRAFT_PREFIX + "tags", d.get("tags", ""))
    d["qtype"] = st.session_state.get(DRAFT_PREFIX + "qtype", d.get("qtype", "解答题"))

    if d["qtype"] in CHOICE_TYPES:
        d["options_list"] = [
            {"key": k, "text": st.session_state.get(DRAFT_PREFIX + f"opt_{k}", "")}
            for k in OPTION_KEYS
        ]
    else:
        d["options_list"] = []


# ============================================================
# 回调（必须放在 widget 渲染之前执行）
# ============================================================
def _cb_fill_sample():
    st.session_state[TEXT_KEY] = SAMPLE_JSON


def _cb_clear():
    _clear_drafts()
    st.session_state[TEXT_KEY] = ""
    st.session_state[SS + "report"] = None
    st.session_state.pop(SS + "notice", None)


def _cb_on_upload():
    """文件上传变化时，把内容读进 text_area。"""
    up = st.session_state.get(SS + "uploader")
    if up is None:
        return
    try:
        content = up.read().decode("utf-8")
        st.session_state[TEXT_KEY] = content
        st.session_state[SS + "upload_msg"] = ("success", f"已读取：{up.name}")
    except UnicodeDecodeError:
        st.session_state[SS + "upload_msg"] = ("error", "文件不是 UTF-8 编码，请另存为 UTF-8 后重试。")
    except Exception as e:
        st.session_state[SS + "upload_msg"] = ("error", f"读取失败：{e}")


def _cb_parse():
    """解析按钮回调：结果存进 session_state，并重建草稿。

    草稿的字段初值直接来自这次的解析结果，所以这里先清掉旧的草稿 widget
    状态，让下一次渲染重新灌入新值。
    """
    text = st.session_state.get(TEXT_KEY, "")
    report = imp.parse_json_text(text)
    _clear_drafts()                      # 同时清掉上一次的暂存图片
    st.session_state[SS + "report"] = report
    if report.fatal_error or not report.rows:
        return
    st.session_state[SS + "drafts"] = [Draft(report=r) for r in report.rows]
    # 有问题的先看：默认落在第一条「错误」或「公式红字」上，没有就停在整体预览
    st.session_state[SS + "edit_idx"] = None


def _cb_fix_latex():
    """自动修复公式回调：改写文本框内容并立刻重新校验。

    只动 KaTeX 渲染不了的那部分写法（比如 MathType 导出的
    \\begin{array}{*{35}{l}}），其余内容原样保留；改完必须由老师再看一眼
    校验结果、确认无误后才入库。
    """
    text = st.session_state.get(TEXT_KEY, "")
    fixed, n = latex_check.fix_text(text)
    if not n:
        st.session_state[SS + "notice"] = (
            "info", "没有能自动修复的公式问题：剩下的需要按提示手工改。"
        )
        return
    st.session_state[TEXT_KEY] = fixed
    report = imp.parse_json_text(fixed)
    _clear_drafts()
    st.session_state[SS + "report"] = report
    if not report.fatal_error and report.rows:
        st.session_state[SS + "drafts"] = [Draft(report=r) for r in report.rows]
    st.session_state[SS + "notice"] = (
        "success", f"已自动修复 {n} 处公式写法，并重新校验了一次；请再确认下面的结果。"
    )


def _cb_goto_edit(idx):
    """切到某一条草稿去编辑：先把上一条的改动收好，再清 widget 状态。"""
    _save_current_draft()
    _clear_draft_widgets()
    st.session_state[SS + "edit_idx"] = int(idx)


def _cb_stop_edit():
    _save_current_draft()
    _clear_draft_widgets()
    st.session_state[SS + "edit_idx"] = None


def _cb_fix_draft_latex():
    """草稿里的「自动修复公式」：改动当前这一条的字段并立刻重新校验。"""
    dr = _current_draft()
    if dr is None:
        return
    p = DRAFT_PREFIX
    total = 0
    for key in ("stem", "answer", "analysis"):
        fixed, n = latex_check.fix_text(st.session_state.get(p + key, "") or "")
        if n:
            st.session_state[p + key] = fixed
            total += n
    for k in OPTION_KEYS:
        key = p + f"opt_{k}"
        fixed, n = latex_check.fix_text(st.session_state.get(key, "") or "")
        if n:
            st.session_state[key] = fixed
            total += n
    if total:
        st.session_state[SS + "notice"] = (
            "success", f"这一条已自动修复 {total} 处公式写法，请看右侧预览确认。"
        )
    else:
        st.session_state[SS + "notice"] = (
            "info", "这一条没有能自动修复的公式问题，需要按提示手工改。"
        )


def _cb_next_draft(step):
    """上一条 / 下一条。"""
    idx = st.session_state.get(SS + "edit_idx")
    if idx is None:
        return
    _save_current_draft()
    _clear_draft_widgets()
    n = len(st.session_state.get(SS + "drafts") or [])
    st.session_state[SS + "edit_idx"] = max(0, min(n - 1, int(idx) + int(step)))


def _save_current_draft():
    """把当前编辑框里的内容收进草稿并重新校验（切走 / 停止编辑时调用）。

    回调里没法渲染控件，所以只同步数据 + 重算校验，界面提示交给页面。
    """
    dr = _current_draft()
    if dr is None:
        return
    _sync_draft_fields(dr)
    imp.revalidate_row(dr.report)


def _current_draft():
    drafts = st.session_state.get(SS + "drafts") or []
    idx = st.session_state.get(SS + "edit_idx")
    if idx is None or not (0 <= idx < len(drafts)):
        return None
    return drafts[idx]


# ============================================================
# 草稿图片：暂存、去重、删除
# ============================================================
def _staging_token(idx: int) -> str:
    """某一批草稿里第 idx 条专属的暂存目录名（会话唯一 + 下标）。"""
    sess = st.session_state.get(SS + "stage_token") or "0"
    return f"{sess}_{int(idx)}"


def _stage_uploads(dr: Draft, group: str, token: int) -> None:
    """把上传框里的新图片存进暂存目录（按内容指纹去重）。

    这里**不**依赖「Streamlit 重跑后上传框还在不在」这类不确定行为：
    内容一样的图只存一次，所以即使同一个文件被处理两遍也不会变成两张。
    """
    key = DRAFT_PREFIX + f"{group}_uploader"
    files = st.session_state.get(key) or []
    if not files:
        return
    target_dir = imp.staging_subdir(_staging_token(token))
    for f in files:
        try:
            fp = file_utils.upload_fingerprint(f)
        except Exception:                       # noqa: BLE001
            continue
        if fp in dr.staging[group]:
            continue
        try:
            rel = file_utils.save_uploaded_image(f, target_dir=target_dir)
        except ValueError as e:
            st.warning(f"第 {token + 1} 条的图片没存下：{e}")
            continue
        except Exception as e:                  # noqa: BLE001
            st.warning(f"第 {token + 1} 条的图片保存失败：{e}")
            continue
        dr.images[group].append(rel)
        dr.staging[group].append(fp)


def _drop_image(dr: Draft, group: str, i: int) -> None:
    """删掉某一张草稿图片，并在需要时清理磁盘文件。"""
    imgs = dr.images[group]
    if not (0 <= i < len(imgs)):
        return
    rel = imgs.pop(i)
    if _is_staged(rel):
        # 还没转正：这文件只属于这一条草稿，直接删掉
        file_utils.delete_file_silently(rel)
    # 覆盖导入时保留的原题配图：只从本条题目里移除，磁盘文件保留 ——
    # 原题（以及其它引用它的地方）还在用它。
    # （指纹留在 staging 里不清：那意味着"这张图这次不再重复存一遍"。
    #   如果老师随即又删又传，_clear_group_images 会重置指纹，不影响使用。）


def _is_staged(rel: str) -> bool:
    """这个路径是不是草稿暂存目录里的（即还没转正）。"""
    return ("images/" + imp.STAGING_DIR_NAME) in (rel or "")


def _clear_group_images(dr: Draft, group: str, token: int) -> None:
    """清空某一组的全部图片（暂存文件一并删掉，指纹也重置）。"""
    for rel in list(dr.images[group]):
        if _is_staged(rel):
            file_utils.delete_file_silently(rel)
    dr.images[group] = []
    # 指纹必须一起清掉，否则老师「清了再传同一张」会传不进来
    dr.staging[group] = []
    # 暂存子目录里剩下的文件（比如刚上传但已被清掉的那些）也一并清干净
    file_utils.clear_dir_silently(imp.staging_subdir(_staging_token(token)))


# ============================================================
# 输入区
# ============================================================
def _render_input():
    st.subheader("① 粘贴或上传 JSON")
    st.caption(
        "支持标准 JSON 数组。字段缺失会自动用默认值；"
        "只有 **题干为空、题型非法、难度非法** 才拒绝入库。"
        "另外会做一次**公式体检**：KaTeX 渲染不了的公式会提前提醒，不会静悄悄进库。"
    )

    tab_paste, tab_file, tab_sample = st.tabs(
        ["📋 粘贴文本", "📁 上传文件", "📖 格式说明 / 示例"]
    )

    with tab_paste:
        st.text_area(
            "JSON 文本",
            height=320,
            key=TEXT_KEY,                     # 唯一数据源，不再传 value
            label_visibility="collapsed",
            placeholder='[\n  { "grade": "高三", "qtype": "解答题", "difficulty": 5, "stem": "..." }\n]',
        )

    with tab_file:
        st.file_uploader(
            "选择 .json 文件（UTF-8 编码）",
            type=["json", "txt"],
            key=SS + "uploader",
            on_change=_cb_on_upload,
        )
        msg = st.session_state.pop(SS + "upload_msg", None)
        if msg:
            kind, text = msg
            getattr(st, kind, st.info)(text)

    with tab_sample:
        st.markdown(_FORMAT_SPEC)
        st.code(SAMPLE_JSON, language="json", wrap_lines=True)
        st.button("📥 把示例填入文本框", key=SS + "btn_sample", on_click=_cb_fill_sample)

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        st.button(
            "🔍 解析并预览",
            type="primary",
            use_container_width=True,
            key=SS + "btn_parse",
            on_click=_cb_parse,              # 关键：用回调，不在主流程里改状态
        )
    with c2:
        st.button(
            "🧹 清空内容",
            use_container_width=True,
            key=SS + "btn_clear",
            on_click=_cb_clear,
        )


# ============================================================
# 预览区
# ============================================================
def _drafts():
    return st.session_state.get(SS + "drafts") or []


def _report_rows(report):
    """取「当前有效」的校验行：优先用草稿里的（可能已被编辑过）。"""
    ds = _drafts()
    if ds and report and len(ds) == len(report.rows):
        return [d.report for d in ds]
    return list(report.rows)


def _row_status(r: imp.RowReport) -> str:
    if not r.ok:
        return "❌ 错误"
    if r.latex_error_count:
        return "🔴 公式红字"
    if r.is_duplicate:
        return "⚠️ 重复"
    if r.has_latex_issue or r.warnings:
        return "⚠️ 提醒"
    return "✅ 正常"


def _render_preview():
    report: imp.ParseResult = st.session_state.get(SS + "report")
    if report is None:
        return

    st.divider()
    st.subheader("② 校验结果")

    if report.fatal_error:
        st.error(report.fatal_error)
        if st.button("重新输入", key=SS + "btn_back"):
            st.session_state[SS + "report"] = None
            st.rerun()
        return

    rows = _report_rows(report)
    drafts = _drafts()
    ok_count = sum(1 for r in rows if r.ok)
    dup_count = sum(1 for r in rows if r.ok and r.is_duplicate)
    latex_count = sum(1 for r in rows if r.ok and r.has_latex_issue)
    latex_error_count = sum(1 for r in rows if r.ok and r.latex_error_count)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("总条数", len(rows))
    c2.metric("可入库", ok_count)
    c3.metric("有问题", sum(1 for r in rows if not r.ok))
    c4.metric("与库内重复", dup_count)
    c5.metric("公式有问题", latex_count,
              delta=f"{latex_error_count} 条会变红字" if latex_error_count else None,
              delta_color="inverse")

    if ok_count == 0:
        st.error("没有任何一条可通过校验，请根据下方提示修改后重新解析。")

    # ---- 公式问题（最容易被忽略，放在最显眼的位置）----
    latex_bad = [r for r in rows if r.ok and r.has_latex_issue]
    if latex_bad:
        _render_latex_panel(latex_bad, rows, fixable_label=ok_count > 0)

    table_rows = []
    for i, r in enumerate(rows):
        d = r.data or {}
        note_parts = list(r.errors)
        if r.latex_error_count:
            note_parts.append(f"{r.latex_error_count} 处公式渲染不了")
        elif r.has_latex_issue:
            note_parts.append("公式有提醒")
        if r.is_duplicate:
            note_parts.insert(0, f"与 #{',#'.join(map(str, r.duplicate_ids[:5]))} 重复")
        note_parts += r.warnings

        n_img = drafts[i].image_count if i < len(drafts) else 0
        table_rows.append({
            "#": i + 1,
            "状态": _row_status(r),
            "配图": f"🖼️ {n_img}" if n_img else "—",
            "题型": d.get("qtype", ""),
            "难度": DIFFICULTY_LABELS.get(d.get("difficulty", 3), ""),
            "年级": d.get("grade", ""),
            "章节": d.get("chapter", ""),
            "题干预览": strip_latex_for_preview(d.get("stem", ""), 60),
            "备注": "；".join(note_parts) if note_parts else "—",
        })

    st.dataframe(
        table_rows,
        use_container_width=True,
        hide_index=True,
        height=min(600, 60 + 36 * len(table_rows)),
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "状态": st.column_config.TextColumn(width="small"),
            "配图": st.column_config.TextColumn(width="small"),
            "题干预览": st.column_config.TextColumn(width="large"),
            "备注": st.column_config.TextColumn(width="large"),
        },
    )

    bad = [r for r in rows if not r.ok]
    if bad:
        with st.expander(f"❌ 查看 {len(bad)} 条错误详情", expanded=False):
            for r in bad:
                st.markdown(f"**第 {r.index + 1} 条**")
                for e in r.errors:
                    st.markdown(f"- {e}")
                if r.data.get("stem"):
                    st.caption("题干：" + strip_latex_for_preview(r.data["stem"], 120))
                st.divider()

    warn = [r for r in rows if r.ok and r.warnings]
    if warn:
        with st.expander(f"⚠️ 查看 {len(warn)} 条提醒", expanded=False):
            for r in warn:
                st.markdown(f"**第 {r.index + 1} 条**：" + "；".join(r.warnings))

    # ---- 逐条预览与修改 ----
    if drafts:
        st.divider()
        st.subheader("③ 逐条预览与修改")
        _render_draft_section(rows, drafts)

    if ok_count > 0:
        st.divider()
        st.subheader("④ 确认入库")
        _render_commit(report, rows)


def _render_latex_panel(latex_bad, rows, *, fixable_label: bool = True):
    """公式问题面板：说清楚哪条、哪一处、怎么改，并给出自动修复入口。"""
    n_err = sum(1 for r in latex_bad if r.latex_error_count)
    title = (f"🔴 {len(latex_bad)} 条题目的公式有问题"
             + (f"（其中 {n_err} 条会渲染成红字，点开看具体位置）" if n_err else ""))
    with st.expander(title, expanded=bool(n_err)):
        st.caption(
            "公式由 KaTeX 渲染。解析不了的公式在页面上会变成**红字**，"
            "学生看不到内容；下面这些写法 KaTeX 不支持，建议先改好再入库。"
        )
        for r in latex_bad:
            st.markdown(f"**第 {r.index + 1} 条**")
            for label, issue in r.latex_issues:
                mark = "🔴" if issue.is_error else "🟡"
                st.markdown(f"- {mark} **{label}**：{issue.message}")
                if issue.snippet:
                    st.caption("问题片段：" + issue.snippet)
            st.divider()

        fixable = sum(r.latex_fixable_count for r in latex_bad)
        if fixable and fixable_label:
            st.button(
                f"🔧 自动修复公式（可修 {fixable} 处）",
                type="primary",
                key=SS + "btn_fix_latex",
                on_click=_cb_fix_latex,
                help="只改写 KaTeX 不支持的列格式等写法，其余内容原样保留；"
                     "修完会立刻重新校验，确认无误再入库。",
            )
        elif not fixable:
            st.info("这些问题需要按上面的提示手工修改公式后重新解析。")


def _render_draft_section(rows, drafts):
    """③ 逐条预览与修改：选一条 → 左边改、右边实时渲染。

    只渲染当前这一条：题目卡片带 KaTeX 和图片，一次渲染几十条会明显卡顿。
    """
    n = len(drafts)
    bad_idx = [i for i, r in enumerate(rows) if not r.ok or r.latex_error_count]

    st.caption(
        "下面是**入库前**的最后一道关：逐条看渲染效果、当场改文字、加配图。"
        "这里改的内容**不会**回写上面的 JSON 文本框（想改 JSON 请改完重新点「解析并预览」，"
        "重解析会重建下面的草稿）。确认无误后再往下拉点「确认入库」。"
    )
    if bad_idx:
        st.warning(
            f"有 {len(bad_idx)} 条有问题（错误或公式红字），建议优先处理："
            + "、".join(f"第 {i + 1} 条" for i in bad_idx[:12])
            + ("…" if len(bad_idx) > 12 else "")
        )

    # ---- 选一条 ----
    idx = st.session_state.get(SS + "edit_idx")
    if idx is not None and not (0 <= idx < n):
        idx = None
        st.session_state[SS + "edit_idx"] = None

    sel_c1, sel_c2 = st.columns([1.2, 3])
    with sel_c1:
        picked = st.number_input(
            "跳到第几条", min_value=1, max_value=n,
            value=(idx + 1) if idx is not None else 1,
            step=1, key=SS + "pick_no",
        )
        if st.button("✏️ 编辑这一条", key=SS + "btn_pick", width="stretch"):
            _cb_goto_edit(int(picked) - 1)
            st.rerun()
    with sel_c2:
        st.caption("也可以直接点下面表格里的「✏️」进入某一条。")
        quick = [i + 1 for i in (bad_idx or list(range(n)))[:10]]
        if quick:
            qcols = st.columns(len(quick))
            for col, no in zip(qcols, quick):
                with col:
                    if st.button(f"✏️ {no}", key=f"{SS}btn_quick_{no}",
                                 help=f"编辑第 {no} 条"):
                        _cb_goto_edit(no - 1)
                        st.rerun()

    # ---- 全部条目的紧凑一览（带编辑入口）----
    with st.expander("📋 全部条目一览（点「✏️」进入编辑）", expanded=idx is None):
        head = st.columns([0.4, 0.6, 2.6, 1.0, 0.5, 1.6, 0.5])
        for col, title in zip(head, ["#", "状态", "题型 / 题干预览", "年级",
                                    "配图", "备注", "操作"]):
            col.markdown(f"**{title}**")
        for i, (r, dr) in enumerate(zip(rows, drafts)):
            d = dr.data
            cols = st.columns([0.4, 0.6, 2.6, 1.0, 0.5, 1.6, 0.5])
            mark = "👉 " if i == idx else ""
            cols[0].markdown(f"{mark}{i + 1}")
            cols[1].markdown(_row_status(r))
            cols[2].markdown(
                f"{d.get('qtype', '')} ｜ {strip_latex_for_preview(d.get('stem', ''), 42)}"
            )
            cols[3].markdown(d.get("grade", "") or "—")
            cols[4].markdown(f"🖼️{dr.image_count}" if dr.image_count else "—")
            notes = list(r.errors)
            if r.latex_error_count:
                notes.append(f"{r.latex_error_count} 处公式红字")
            elif r.has_latex_issue:
                notes.append("公式有提醒")
            if r.is_duplicate:
                notes.append("与库内重复")
            cols[5].caption("；".join(notes) if notes else "—")
            cols[6].button("✏️", key=f"{SS}btn_edit_{i}",
                           on_click=_cb_goto_edit, args=(i,),
                           help=f"编辑第 {i + 1} 条")

    if idx is None:
        return

    # ---- 编辑某一条 ----
    _render_draft_editor(idx, drafts[idx], rows)
    st.divider()
    nav = st.columns([1, 1, 1, 3])
    with nav[0]:
        st.button("⬅️ 上一条", key=SS + "btn_prev", width="stretch",
                  disabled=idx <= 0, on_click=_cb_next_draft, args=(-1,))
    with nav[1]:
        st.button("下一条 ➡️", key=SS + "btn_next", width="stretch",
                  disabled=idx >= n - 1, on_click=_cb_next_draft, args=(1,))
    with nav[2]:
        st.button("✅ 改好了", key=SS + "btn_stop_edit", width="stretch",
                  on_click=_cb_stop_edit,
                  help="收起编辑区，回到整体预览（改动自动保留）")


def _seed_draft_widgets(dr: Draft) -> None:
    """把草稿的当前值灌进编辑框（只在切换编辑对象后做一次）。"""
    d = dr.data
    p = DRAFT_PREFIX
    def setdef(key, value):
        if key not in st.session_state:
            st.session_state[key] = value

    setdef(p + "stem", d.get("stem", ""))
    setdef(p + "answer", d.get("answer", ""))
    setdef(p + "analysis", d.get("analysis", ""))
    setdef(p + "qtype", d.get("qtype", "解答题"))
    setdef(p + "grade", d.get("grade", ""))
    setdef(p + "chapter", d.get("chapter", ""))
    setdef(p + "difficulty", d.get("difficulty", 3))
    setdef(p + "source", d.get("source", ""))
    setdef(p + "knowledge", d.get("knowledge", ""))
    setdef(p + "tags", d.get("tags", ""))

    opts = {o.get("key"): o.get("text", "") for o in (d.get("options_list") or [])}
    for k in OPTION_KEYS:
        setdef(p + f"opt_{k}", opts.get(k, ""))


def _render_draft_editor(idx: int, dr: Draft, rows):
    """单条草稿：左编辑 + 右实时渲染。"""
    token = idx
    _seed_draft_widgets(dr)
    p = DRAFT_PREFIX

    # ---- 先把图片上传处理掉，这样右侧预览立刻能看到刚传的图 ----
    for group in ("stem", "analysis"):
        _stage_uploads(dr, group, token)

    # ---- 先把标记的图片删掉（缩略图 → 复选框 → 按钮，状态明确）----
    marked = _newly_marked_images(idx, token)

    with st.container(border=True):
        head_l, head_r = st.columns([3, 2])
        with head_l:
            st.markdown(f"#### 第 {idx + 1} 条 ｜ 编辑 + 实时预览")
        with head_r:
            r = dr.report
            bits = [_row_status(r)]
            if r.duplicate_ids:
                bits.append("与 #" + "、#".join(map(str, r.duplicate_ids[:5])) + " 重复")
            if dr.image_count:
                bits.append(f"配图 {dr.image_count} 张")
            st.markdown("　".join(bits))

        left, right = st.columns(2)

        # ================= 左：编辑 =================
        with left:
            st.markdown("**题干**")
            st.text_area("题干", key=p + "stem", height=200,
                         label_visibility="collapsed",
                         placeholder="支持 LaTeX：行内 $x^2$，独立公式 $$...$$")

            qtype = st.session_state.get(p + "qtype", "解答题")
            if qtype in CHOICE_TYPES:
                st.markdown("**选项**（A~D）")
                ocols = st.columns(4)
                for i, k in enumerate(OPTION_KEYS):
                    with ocols[i]:
                        st.text_input(f"{k}．", key=p + f"opt_{k}",
                                      label_visibility="visible")

            st.markdown("**答案**")
            st.text_area("答案", key=p + "answer", height=90,
                         label_visibility="collapsed")

            st.markdown("**解析**")
            st.text_area("解析", key=p + "analysis", height=180,
                         label_visibility="collapsed")

            with st.expander("🏷️ 分类信息（题型 / 年级 / 难度 / 来源 …）", expanded=False):
                cc1, cc2, cc3 = st.columns(3)
                with cc1:
                    st.selectbox("题型", QTYPES, key=p + "qtype")
                with cc2:
                    st.selectbox("年级", [""] + GRADES, key=p + "grade")
                with cc3:
                    st.selectbox("难度", [1, 2, 3, 4, 5],
                                 format_func=lambda x: DIFFICULTY_LABELS[x],
                                 key=p + "difficulty")
                mm1, mm2, mm3 = st.columns(3)
                with mm1:
                    st.text_input("章节", key=p + "chapter")
                with mm2:
                    st.text_input("来源", key=p + "source")
                with mm3:
                    st.text_input("知识点（逗号分隔）", key=p + "knowledge")
                st.text_input("标签（逗号分隔）", key=p + "tags")

            st.caption("❗ 想改题型请展开上面的「分类信息」；选择题的选项框也随之出现。")

        # ================= 右：实时渲染 =================
        with right:
            st.caption("实时预览（与入库后的显示一致）")
            with st.container(border=True):
                _render_draft_preview(dr)

    # ---- 图片管理 ----
    st.markdown("**配图**")
    st.caption(
        "两组图片分开管理：**题干配图**显示在题干里，**解析配图**显示在答案解析里。"
        "上传后缩略图下方会给出可复制的定位标记 `![[img:N]]`（多张时用 `![[img:N|300]]` "
        "指定宽度），把它粘到文字里想插图的位置即可；**不写标记的图片会排在文字最后**。"
        "所有图片都还没进题库，点「确认入库」时才真正写入。"
    )
    icol1, icol2 = st.columns(2)
    with icol1:
        _render_draft_image_group(dr, idx, "stem", "题干配图")
    with icol2:
        _render_draft_image_group(dr, idx, "analysis", "解析配图")

    # ---- 同步 + 重校验 ----
    _sync_draft_fields(dr)
    imp.revalidate_row(dr.report)

    # ---- 公式提示 + 一键修复 ----
    issues = list(dr.report.latex_issues)
    fc1, fc2 = st.columns([3, 1])
    with fc1:
        if issues:
            first = issues[0][1]
            st.caption(("🔴 " if first.is_error else "🟡 ")
                       + f"**{issues[0][0]}**：{first.message}")
            if len(issues) > 1:
                st.caption(f"（另有 {len(issues) - 1} 处公式问题）")
        else:
            st.caption("✅ 这一条的公式都能正常渲染")
        if not dr.report.ok:
            for e in dr.report.errors:
                st.error(e)
    with fc2:
        if issues and any(i.fixable for _, i in issues):
            st.button("🔧 修复本条的公式", key=SS + "btn_fix_draft",
                      width="stretch", on_click=_cb_fix_draft_latex,
                      help="只改写 KaTeX 不支持的写法，改完请看右侧预览确认。")

    if marked:
        st.button(f"🗑️ 删除标记的 {len(marked)} 张图片",
                  key=SS + "btn_drop_imgs",
                  on_click=_cb_apply_image_deletes, args=(token,),
                  help="缩略图下面的「删」勾上以后，点这里才会真正移除。")


def _newly_marked_images(idx: int, token: int) -> list:
    """建立每张图的「删」复选框状态，并返回已勾选删除的下标 [(组名, 下标)]。"""
    marked = []
    dr = _current_edit_draft(idx)
    if dr is None:
        return marked
    for group in ("stem", "analysis"):
        for i in range(len(dr.images[group])):
            key = DRAFT_PREFIX + f"{group}_del_{i}"
            st.session_state.setdefault(key, False)
            if st.session_state[key]:
                marked.append((group, i))
    return marked


def _current_edit_draft(idx: int):
    drafts = _drafts()
    return drafts[idx] if 0 <= idx < len(drafts) else None


def _cb_apply_image_deletes(token):
    """回调：把勾了「删」的图片真正移除（倒序删，避免下标错位）。"""
    dr = _current_edit_draft(token)
    if dr is None:
        return
    # 先把编辑框里的文字收好，免得随后的 rerun 读到旧值
    _sync_draft_fields(dr)
    for group in ("stem", "analysis"):
        for i in sorted(range(len(dr.images[group])), reverse=True):
            if st.session_state.get(DRAFT_PREFIX + f"{group}_del_{i}"):
                _drop_image(dr, group, i)
        # 清掉这一轮的复选框状态，让下一轮按新的下标重建
        for k in list(st.session_state.keys()):
            if k.startswith(DRAFT_PREFIX + f"{group}_del_"):
                del st.session_state[k]
    imp.revalidate_row(dr.report)


def _render_draft_image_group(dr: Draft, token: int, group: str, label: str) -> None:
    """一组草稿图片：缩略图 + 复制用的标记 + 上传框 + 安置提示。"""
    p = DRAFT_PREFIX
    imgs = dr.images[group]

    st.markdown(f"**{label}**")
    if imgs:
        single = len(imgs) == 1
        cols = st.columns(min(3, len(imgs)))
        for i, rel in enumerate(imgs):
            with cols[i % len(cols)]:
                _show_image(rel, width=140)
                st.code(_marker_for(rel, i + 1, single), language=None)
                st.checkbox("删", key=p + f"{group}_del_{i}")

    up_key = p + f"{group}_uploader"
    st.file_uploader(
        f"上传{label}（png / jpg / webp / gif，≤5MB，可多选）",
        type=["png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=True, key=up_key,
        label_visibility="collapsed",
    )

    field = "analysis" if group == "analysis" else "stem"
    text = st.session_state.get(p + field, "") or ""
    report = placement_report(text, imgs)
    if imgs:
        if report["unplaced"]:
            nums = "、".join(f"第 {n} 张" for n in report["unplaced"])
            st.caption(f"⚠️ 还没安置：{nums}（不写标记时会排在文字最后）")
        elif report["placed"]:
            st.caption("✅ 图片都已用标记安置好")
    if report["bad"]:
        st.caption("❗ 文字里引用了不存在的序号："
                   + "、".join(str(n) for n in report["bad"]))
    if imgs:
        st.button(f"🧹 清空{label}", key=p + f"{group}_clear",
                  on_click=_cb_clear_group_images, args=(token, group))


def _cb_clear_group_images(token, group):
    dr = _current_edit_draft(token)
    if dr is None:
        return
    _sync_draft_fields(dr)
    _clear_group_images(dr, group, token)
    for k in list(st.session_state.keys()):
        if k.startswith(DRAFT_PREFIX + f"{group}_del_"):
            del st.session_state[k]
    imp.revalidate_row(dr.report)


def _marker_for(rel: str, number: int, single: bool) -> str:
    """该张图片建议写进正文的定位标记。"""
    return marker_syntax(number, compact=single)


def _show_image(rel: str, width: int = 140) -> None:
    """草稿里显示一张图片（暂存目录和正式目录都能显示）。"""
    p = file_utils.abs_path(file_utils.real_image_path(rel))
    if p.is_file():
        st.image(str(p), width=width)
    else:
        st.caption("图片已丢失")


# ------------------------------------------------------------
# 预览用的轻量对象：把草稿数据喂给 question_card 的公共渲染
# ------------------------------------------------------------
@dataclass
class _PreviewQuestion:
    # question_card 的渲染层用 q.id 拼容器 key，这里给一个「第几条」的编号即可
    id: int = 0
    grade: str = ""
    chapter: str = ""
    knowledge: str = ""
    qtype: str = "解答题"
    difficulty: int = 3
    stem: str = ""
    answer: str = ""
    analysis: str = ""
    source: str = ""
    tags: str = ""
    options_list: list = field(default_factory=list)
    image_list: list = field(default_factory=list)

    @property
    def knowledge_list(self):
        return [x.strip() for x in (self.knowledge or "").split(",") if x.strip()]

    @property
    def tag_list(self):
        return [x.strip() for x in (self.tags or "").split(",") if x.strip()]


def _render_draft_preview(dr: Draft) -> None:
    """完全复用题目卡片的渲染层，保证预览与入库后的显示一致。"""
    d = dr.data
    idx = st.session_state.get(SS + "edit_idx") or 0
    q = _PreviewQuestion(
        id=int(idx) + 1,
        grade=d.get("grade", ""), chapter=d.get("chapter", ""),
        knowledge=d.get("knowledge", ""), qtype=d.get("qtype", "解答题"),
        difficulty=int(d.get("difficulty") or 3), stem=d.get("stem", ""),
        answer=d.get("answer", ""), analysis=d.get("analysis", ""),
        source=d.get("source", ""), tags=d.get("tags", ""),
        options_list=d.get("options_list") or [],
        image_list=dr.all_images(),
    )
    key = f"draft{idx}"
    qc.render_body(q, key=key, thumb_prefix=f"draft_{key}")
    qc.render_answer_expander(q, key=key)


def _render_commit(report, rows):
    """④ 确认入库：选重复处理方式 → 备份（可选）→ 入库。

    rows 是「当前有效」的校验行（草稿改过就用改过的），所以这里的统计、
    提示、以及真正入库的内容，跟老师在③里看到的最后一眼完全一致。
    """
    drafts = _drafts()
    n_img = sum(d.image_count for d in drafts)
    dup_n = sum(1 for r in rows if r.ok and r.is_duplicate)
    ok_n = sum(1 for r in rows if r.ok)

    st.caption(
        "入库前请再确认一次上面的预览。"
        + (f"本次有 {n_img} 张配图会随题目一起入库。" if n_img else
           "本次没有配图（想插图就回到上面③里上传）。")
    )

    mode = st.radio(
        "遇到与题库里**题干相同**的题目时：",
        options=list(imp.DUPLICATE_MODES),
        format_func=lambda m: imp.DUPLICATE_MODE_LABELS[m],
        key=SS + "dup_mode",
        horizontal=True,
        disabled=dup_n == 0,
        help="按题干内容判定重复（忽略所有空格）。注意：在③里改过题干的话，"
             "这里是按**改过之后**的题干重新查重的结果。",
    )
    if dup_n == 0:
        st.caption("本次导入没有与题库重复的题目，这一项不起作用。")

    if mode == "overwrite" and dup_n:
        st.warning(
            "覆盖会**直接改写题库里的原题**（题目编号不变，试卷引用不受影响），"
            "改写后无法用「回收站」还原。"
        )
        st.checkbox(
            "覆盖前先做一次整库备份（推荐）",
            key=SS + "backup_first",
            help="备份文件放在 data/backups/ 目录，可在「系统设置」里查看。",
        )
        ids = sorted({r.overwrite_id for r in rows if r.ok and r.is_duplicate and r.overwrite_id})
        st.caption("将被改写的题目编号：" + "、".join(f"#{i}" for i in ids[:20])
                   + ("…" if len(ids) > 20 else ""))

    will_insert = ok_n - (dup_n if mode in ("skip", "overwrite") else 0)
    if dup_n == 0:
        summary = f"✅ 导入 {ok_n} 道题"
    elif mode == "skip":
        summary = f"✅ 导入 {will_insert} 道题（跳过重复 {dup_n} 道）"
    elif mode == "overwrite":
        summary = f"✅ 导入 {will_insert} 道，并覆盖 {dup_n} 道重复题"
    else:
        summary = f"✅ 导入 {ok_n} 道题（重复的也新增一份）"

    b1, b2, _ = st.columns([1, 1, 4])
    with b1:
        if st.button(summary, type="primary",
                     use_container_width=True, key=SS + "btn_commit"):
            backup_path = None
            if mode == "overwrite" and dup_n and st.session_state.get(SS + "backup_first", True):
                try:
                    with st.spinner("正在整库备份…"):
                        backup_path = backup_service.export_full_backup_zip()
                except Exception as e:
                    st.error(f"备份失败，已取消覆盖导入：{e}")
                    return
            # 草稿里的图片此刻才从暂存目录转正到正式图片目录
            try:
                _promote_drafts(drafts, rows)
            except Exception as e:
                st.error(f"配图写入失败，已取消导入：{e}")
                return
            try:
                stats = imp.commit_import(rows, on_duplicate=mode)
            except Exception as e:
                st.error(f"入库失败：{e}")
                return
            # 入库成功：暂存目录（含已转正文件的原件）可以清掉了
            try:
                imp.clear_staging()
            except Exception:                   # noqa: BLE001
                pass
            parts = [f"新增 {stats['inserted']} 道"]
            if stats["updated"]:
                parts.append(f"覆盖 {stats['updated']} 道")
            if stats["skipped_dup"]:
                parts.append(f"跳过重复 {stats['skipped_dup']} 道")
            if stats["skipped_err"]:
                parts.append(f"跳过错误 {stats['skipped_err']} 道")
            tail = f"（备份：{backup_path.name}）" if backup_path else ""
            st.session_state["_flash"] = (
                "success", "导入完成：" + "，".join(parts) + "。" + tail
            )
            st.session_state[SS + "report"] = None
            _clear_drafts()
            st.session_state[SS + "clear_text_next_run"] = True   # 交给 render() 处理
            st.rerun()
    with b2:
        if st.button("取消", use_container_width=True, key=SS + "btn_cancel"):
            _clear_drafts()
            st.session_state[SS + "report"] = None
            st.rerun()


def _promote_drafts(drafts, rows) -> None:
    """把草稿里的图片从暂存目录转正，并写回每一行的校验结果。

    转正**只在这里**发生：点「确认入库」之后。在这之前取消、重新解析、
    直接关掉浏览器，暂存目录都会被清掉，不会在 data/images/ 里留垃圾。

    覆盖导入时还有一条要照顾的：原题可能已经有配图，而草稿里的模板是从
    JSON 来的、本来没有图。这时把原题已有的图**接在草稿图片前面**，
    既不丢原来的图，也不会让老师新写的 ![[img:1]] 指错对象
    （草稿里的序号始终从 1 数起，指的就是自己在预览里看到的那张）。
    """
    for i, r in enumerate(rows):
        if i >= len(drafts):
            break
        dr = drafts[i]
        # 该题在题库里已有的配图（只有覆盖模式才可能有）
        originals = []
        if r.is_duplicate and r.overwrite_id:
            from src.services import question_service as qs
            old = qs.get_question(r.overwrite_id)
            if old is not None:
                originals = list(old.image_list or [])

        promoted = imp.promote_staged_images(dr.all_images())
        if originals and not dr.image_count:
            # 老师这次没动配图：原样保留原题的图
            promoted = originals
        elif originals:
            old_stem, old_ana = file_utils.split_images(originals)
            merged = file_utils.join_images(
                list(old_stem) + list(dr.images["stem"]),
                list(old_ana) + list(dr.images["analysis"]),
            )
            promoted = imp.promote_staged_images(merged)

        r.staged_images = promoted
        r.data["image_list"] = promoted
        # 草稿页确认过的条目：覆盖时以这里的图片为准（可能是老师主动清空了配图）
        r.draft_images = True


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()

    # 上一轮导入成功后置的标记：在下一次 rerun 的 widget 渲染之前清空文本框
    if st.session_state.pop(SS + "clear_text_next_run", False):
        st.session_state[TEXT_KEY] = ""

    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)

    notice = st.session_state.pop(SS + "notice", None)
    if notice:
        kind, msg = notice
        getattr(st, kind, st.info)(msg)

    st.header("📥 批量导入")

    _render_input()
    _render_preview()