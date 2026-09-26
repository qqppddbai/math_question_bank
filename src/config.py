# -*- coding: utf-8 -*-
"""全局配置：路径、常量字典。
老师若要改题型/年级，只改本文件即可，其它代码无需动。
"""
from pathlib import Path

# ---------- 路径 ----------
BASE_DIR = Path(__file__).resolve().parent.parent      # 项目根目录
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"                       # 题目图片
STUDENT_FILES_DIR = DATA_DIR / "student_files"         # 学生错题/学习图片
EXPORT_DIR = DATA_DIR / "exports"                      # 导出的试卷
BACKUP_DIR = DATA_DIR / "backups"                      # 数据库备份

# 目录不存在就自动创建，避免首次运行报错
for _d in (DATA_DIR, IMAGES_DIR, STUDENT_FILES_DIR, EXPORT_DIR, BACKUP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "mathbank.db"
DB_URL = f"sqlite:///{DB_PATH}"

# ---------- 业务常量 ----------
GRADES = ["初一", "初二", "初三", "高一", "高二", "高三"]

QTYPES = ["单选题", "多选题", "填空题", "解答题", "判断题", "作图题"]

DIFFICULTY_LABELS = {
    1: "★☆☆☆☆ 很易",
    2: "★★☆☆☆ 较易",
    3: "★★★☆☆ 中等",
    4: "★★★★☆ 较难",
    5: "★★★★★ 很难",
}

# 选择题固定 4 个选项
OPTION_KEYS = ["A", "B", "C", "D"]

# 题型分类（给组卷和导入做默认值用）
CHOICE_TYPES = {"单选题", "多选题"}
SUBJECTIVE_TYPES = {"填空题", "解答题", "判断题", "作图题"}

APP_TITLE = "数学题库管理系统"

# ---------- 题目显示字体（全项目统一在这里改） ----------
# 中文号数换算：六号 = 7.5pt，五号 = 10.5pt（1pt = 1/72 英寸，96dpi 下 7.5pt ≈ 10px）
QUESTION_FONT_NAME = "宋体"      # 题目正文统一字体
QUESTION_FONT_STACK = (          # 网页 CSS 用的字体回退栈（英文名兼容非中文系统）
    '"宋体", SimSun, "Songti SC", "STSong", "MS Song", serif'
)
UI_QUESTION_FONT_SIZE = "7.5pt"        # 网页界面题目显示：宋体 六号
EXPORT_QUESTION_FONT_PT = 10.5         # 导出文件题目显示：宋体 五号