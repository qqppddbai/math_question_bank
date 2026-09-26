# -*- coding: utf-8 -*-
"""首页：题库概览统计。"""
import streamlit as st
from sqlalchemy import func, select

from src.config import DIFFICULTY_LABELS
from src.database import session_scope
from src.models import Paper, Question, Student


def render():
    st.header("🏠 首页概览")
    st.caption("数据统计实时刷新；左侧选择功能模块开始使用。")

    try:
        with session_scope() as s:
            q_total = s.scalar(
                select(func.count()).select_from(Question).where(Question.is_deleted.is_(False))
            ) or 0
            q_trash = s.scalar(
                select(func.count()).select_from(Question).where(Question.is_deleted.is_(True))
            ) or 0
            p_total = s.scalar(
                select(func.count()).select_from(Paper).where(Paper.is_deleted.is_(False))
            ) or 0
            stu_total = s.scalar(
                select(func.count()).select_from(Student).where(Student.is_deleted.is_(False))
            ) or 0

            type_rows = s.execute(
                select(Question.qtype, func.count())
                .where(Question.is_deleted.is_(False))
                .group_by(Question.qtype)
            ).all()

            grade_rows = s.execute(
                select(Question.grade, func.count())
                .where(Question.is_deleted.is_(False))
                .group_by(Question.grade)
            ).all()

            diff_rows = s.execute(
                select(Question.difficulty, func.count())
                .where(Question.is_deleted.is_(False))
                .group_by(Question.difficulty)
            ).all()
    except Exception as e:  # 数据库异常不至于白屏
        st.error(f"读取数据库失败：{e}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("题库题目", f"{q_total} 道")
    c2.metric("试卷", f"{p_total} 份")
    c3.metric("学生", f"{stu_total} 人")
    c4.metric("回收站", f"{q_trash} 道")

    st.divider()

    if q_total == 0:
        st.info(
            "题库还是空的。建议先到 **📥 批量导入** 粘贴 JSON 数组导入，"
            "或到 **📚 题目管理** 手动新增第一道题。"
        )
        return

    left, right = st.columns(2)
    with left:
        st.subheader("题型分布")
        if type_rows:
            st.dataframe(
                [{"题型": t or "未填", "数量": n} for t, n in type_rows],
                width="stretch", hide_index=True,
            )
        st.subheader("难度分布")
        if diff_rows:
            st.dataframe(
                [{"难度": DIFFICULTY_LABELS.get(d, str(d)), "数量": n} for d, n in sorted(diff_rows)],
                width="stretch", hide_index=True,
            )
    with right:
        st.subheader("年级分布")
        if grade_rows:
            st.dataframe(
                [{"年级": g or "未填", "数量": n} for g, n in grade_rows],
                width="stretch", hide_index=True,
            )