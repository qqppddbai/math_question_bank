# -*- coding: utf-8 -*-
"""查询结果缓存层。

目的：Streamlit 每次交互都会把当前页面从头跑一遍。像「题目管理」这种页面，
一次切换就要重新查列表、重新统计、重新取筛选下拉框的候选值，全部走一遍 SQLite。
题目多了以后，这些重复查询就是页面跳转卡顿的主要来源之一。

做法：
- 读接口用 st.cache_data 包一层，同一个查询在 TTL 内只真正打一次数据库；
- 写接口（新增/修改/删除/批量操作）执行完主动 bump()，立刻让读缓存失效，
  保证「改完马上就能看到新数据」，不会出现页面显示旧内容的情况。

两个踩过的坑，写在最前面，别再犯：
1. `st.cache_data(ttl=...)` 返回的是**装饰器**，不是缓存对象；要清缓存必须调用
   **被装饰后**那个函数的 `.clear()`。把装饰器当缓存对象存起来再调 `.clear()`
   会抛 AttributeError，缓存一个也清不掉。
2. 清缓存失败**绝不能用 try/except 吞掉**。吞掉的表现就是"界面一直显示旧数据，
   重启才好"，这种 bug 极难排查；宁可当场报错。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

import streamlit as st
from sqlalchemy import select

from src.database import session_scope
from src.models import Question
from src.services import question_service as qs

# 缓存有效期。写操作会主动失效，所以这里可以设得长一些；
# 留一个 TTL 只是为了兜底（比如直接在外部改了数据库文件）。
TTL_SECONDS = 300

# 高频查询的结果集不会太大（分页 / 去重后的候选值），给个上限防止内存无限增长。
MAX_ENTRIES = 64

# 所有"带缓存的读接口"都登记在这里，bump() 靠它统一清缓存。
_CACHED: List[Callable[..., Any]] = []


def _cached(fn: Callable[..., Any]) -> Callable[..., Any]:
    """给读接口套上缓存，并登记到 _CACHED。"""
    wrapped = st.cache_data(ttl=TTL_SECONDS, max_entries=MAX_ENTRIES,
                            show_spinner=False)(fn)
    _CACHED.append(wrapped)
    return wrapped


# ---------------- 读接口（带缓存） ----------------
# 函数名 / 参数 / 返回值都和 question_service 保持一致，
# 调用方把 qs.xxx 换成 dc.xxx 即可。
@_cached
def list_questions(*args, **kwargs):
    return qs.list_questions(*args, **kwargs)


@_cached
def count_questions(*args, **kwargs):
    return qs.count_questions(*args, **kwargs)


@_cached
def search_questions(*args, **kwargs):
    return qs.search_questions(*args, **kwargs)


@_cached
def count_search_questions(*args, **kwargs):
    return qs.count_search_questions(*args, **kwargs)


@_cached
def list_deleted_questions(*args, **kwargs):
    return qs.list_deleted_questions(*args, **kwargs)


@_cached
def count_deleted_questions(*args, **kwargs):
    return qs.count_deleted_questions(*args, **kwargs)


@_cached
def get_all_chapters(*args, **kwargs):
    return qs.get_all_chapters(*args, **kwargs)


@_cached
def get_all_sources(*args, **kwargs):
    return qs.get_all_sources(*args, **kwargs)


@_cached
def get_all_knowledge(*args, **kwargs):
    return qs.get_all_knowledge(*args, **kwargs)


@_cached
def get_all_tags(*args, **kwargs):
    return qs.get_all_tags(*args, **kwargs)


@_cached
def get_questions_by_ids(ids: tuple) -> Dict[int, Question]:
    """一次性批量取题目，返回 {id: Question}。

    组卷 / 导出时同一批 id 在一次 rerun 里会被问好几遍，
    所以也纳入缓存；题目一改动 bump() 会连它一起清掉。
    """
    clean = [int(i) for i in (ids or []) if i is not None]
    if not clean:
        return {}
    with session_scope() as s:
        rows = s.scalars(select(Question).where(Question.id.in_(clean))).all()
        result: Dict[int, Question] = {}
        for q in rows:
            s.expunge(q)
            result[q.id] = q
        return result


def bump() -> None:
    """清空查询缓存。任何写操作之后都必须调用。

    由 question_service 的写函数在提交成功后统一调用（见各写接口里的
    `_invalidate_cache()`），另外 import_service.commit_import 也会调，
    所以业务代码不需要关心缓存失效时机。
    """
    for wrapped in _CACHED:
        wrapped.clear()


__all__ = [
    "bump",
    "list_questions", "count_questions",
    "search_questions", "count_search_questions",
    "list_deleted_questions", "count_deleted_questions",
    "get_all_chapters", "get_all_sources", "get_all_knowledge", "get_all_tags",
    "get_questions_by_ids",
]
