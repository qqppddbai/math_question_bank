# -*- coding: utf-8 -*-
"""系统设置页面：备份 / 恢复 / 清理 / 关于。"""
from __future__ import annotations

import sys
from datetime import datetime

import streamlit as st

from src.config import BACKUP_DIR, DATA_DIR
from src.services import backup_service as bk

SS = "set_"


def _init_state():
    st.session_state.setdefault(SS + "orphans", None)
    st.session_state.setdefault(SS + "staged", None)


def _flash(msg: str, kind: str = "success"):
    st.session_state["_flash"] = (kind, msg)


def _show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind, st.info)(msg)


# ============================================================
# 备份
# ============================================================
def _render_backup():
    st.subheader("📦 备份 / 导出")

    c1, c2 = st.columns(2)

    # ---------- 题库 JSON ----------
    with c1:
        with st.container(border=True):
            st.markdown("**① 题库 JSON**")
            st.caption("只导出题目（不含试卷/学生/图片）。格式与「批量导入」完全兼容，"
                       "可用于**题库分享**或**迁移到其他电脑**。")
            if st.button("生成题库 JSON", key=SS + "gen_q_json",
                         use_container_width=True):
                try:
                    content = bk.export_questions_json()
                    st.session_state[SS + "q_json"] = content
                except Exception as e:
                    st.error(f"生成失败：{e}")
            content = st.session_state.get(SS + "q_json")
            if content:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    "⬇️ 下载 questions.json",
                    data=content.encode("utf-8"),
                    file_name=f"questions_{ts}.json",
                    mime="application/json",
                    use_container_width=True,
                    key=SS + "dl_q_json",
                )

    # ---------- 整库 ZIP ----------
    with c2:
        with st.container(border=True):
            st.markdown("**② 整库备份 ZIP**")
            st.caption("题目 + 试卷 + 学生 + 错题 + **全部图片文件**。"
                       "推荐定期备份。文件名带时间戳，不会覆盖。")
            if st.button("生成整库备份", key=SS + "gen_zip",
                         use_container_width=True, type="primary"):
                try:
                    path = bk.export_full_backup_zip()
                    st.session_state[SS + "zip_path"] = str(path)
                except Exception as e:
                    st.error(f"备份失败：{e}")
            zip_path = st.session_state.get(SS + "zip_path")
            if zip_path:
                from pathlib import Path
                p = Path(zip_path)
                if p.is_file():
                    size_mb = round(p.stat().st_size / 1024 / 1024, 2)
                    st.caption(f"已生成：`{p.name}`（{size_mb} MB）")
                    st.download_button(
                        "⬇️ 下载 ZIP",
                        data=p.read_bytes(),
                        file_name=p.name,
                        mime="application/zip",
                        use_container_width=True,
                        key=SS + "dl_zip",
                    )

    st.caption(f"备份文件也保存在：`{BACKUP_DIR}`")


# ============================================================
# 恢复
# ============================================================
def _render_restore():
    st.subheader("♻️ 从备份恢复")
    st.warning(
        "恢复是**破坏性**操作，会覆盖现有的全部数据。"
        "建议先做一次整库备份。"
    )

    uploaded = st.file_uploader(
        "上传备份 ZIP（之前从本页导出的 .zip）",
        type=["zip"],
        key=SS + "restore_upload",
    )

    if uploaded is not None:
        if st.button("校验并暂存", type="primary", key=SS + "stage_btn"):
            try:
                info = bk.stage_restore_from_zip(uploaded)
            except Exception as e:
                st.error(f"校验失败：{e}")
                st.session_state[SS + "staged"] = None
            else:
                st.session_state[SS + "staged"] = info

    info = st.session_state.get(SS + "staged")
    if info:
        st.success("✅ 压缩包已校验并暂存")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("题目", info["questions"])
        c2.metric("试卷", info["papers"])
        c3.metric("学生", info["students"])
        c4.metric("错题", info["mistakes"])
        st.caption(f"暂存目录：`{info['dir']}`")

        st.info(
            "**接下来的步骤**（因为运行中无法直接覆盖数据库，必须手工完成）：\n\n"
            "1. 在终端按 `Ctrl + C` **关闭 Streamlit**；\n"
            "2. 打开文件夹 `data/pending_restore/`，把里面的：\n"
            "   - `images/`、`student_files/` 覆盖到 `data/` 下的同名文件夹；\n"
            "   - **不要**用备份里的 `data.json` 替换 `mathbank.db`，它是纯文本备份；\n"
            "3. 删除 `data/mathbank.db`；\n"
            "4. 重新运行 `streamlit run app.py`，进入「批量导入」页，"
            "把 `data/pending_restore/` 里的题目用 JSON 方式导入；\n"
            "5. 学生和试卷数据**需要手工重建**（MVP 阶段不支持自动恢复 SQL 关系）。\n\n"
            "💡 更省事的做法：把备份 ZIP 解压到一份**全新的项目目录**，"
            "然后手工把 `data.json` 转成你想导入的格式。"
        )

        if st.button("清空暂存", key=SS + "clear_pending"):
            bk.clear_pending_restore()
            st.session_state[SS + "staged"] = None
            _flash("暂存目录已清空")
            st.rerun()


# ============================================================
# 图片清理
# ============================================================
def _render_cleanup():
    st.subheader("🧹 清理未引用图片")
    st.caption(
        "扫描 `data/images/` 下所有图片文件，找出没有被任何题目引用的孤儿文件。"
        "这些通常是题目被彻底删除或图片被替换后遗留的。"
    )

    if st.button("🔍 扫描", key=SS + "scan"):
        try:
            orphans = bk.find_orphan_images()
            st.session_state[SS + "orphans"] = orphans
        except Exception as e:
            st.error(f"扫描失败：{e}")

    orphans = st.session_state.get(SS + "orphans")
    if orphans is None:
        return
    if not orphans:
        st.success("✨ 没有发现孤儿图片，磁盘很干净。")
        return

    total_kb = sum(o["size_kb"] for o in orphans)
    st.warning(f"发现 **{len(orphans)}** 个孤儿文件，合计 **{total_kb:.1f} KB**")

    import pandas as pd
    df = pd.DataFrame([{
        "文件": o["rel_path"],
        "大小(KB)": o["size_kb"],
    } for o in orphans])
    st.dataframe(df, use_container_width=True, hide_index=True,
                 height=min(400, 60 + 36 * len(df)))

    b1, b2, _ = st.columns([1, 1, 4])
    with b1:
        if st.button(f"🗑️ 全部删除（{len(orphans)}）", type="primary",
                     use_container_width=True, key=SS + "del_orphans"):
            n = bk.delete_orphan_images([o["rel_path"] for o in orphans])
            st.session_state[SS + "orphans"] = None
            _flash(f"已删除 {n} 个孤儿文件")
            st.rerun()
    with b2:
        if st.button("取消", use_container_width=True, key=SS + "cancel_clean"):
            st.session_state[SS + "orphans"] = None
            st.rerun()


# ============================================================
# 关于
# ============================================================
def _render_about():
    st.subheader("ℹ️ 关于")
    st.markdown(f"""
- **应用版本**：v0.1 MVP
- **Python**：{sys.version.split()[0]}
- **数据目录**：`{DATA_DIR}`
- **备份目录**：`{BACKUP_DIR}`

**数据文件说明**
| 文件 | 说明 |
|---|---|
| `data/mathbank.db` | 主数据库（SQLite）。删除即等于清空全部数据 |
| `data/images/` | 题目图片 |
| `data/student_files/` | 学生错题/学习图片 |
| `data/exports/` | 试卷导出时留下的副本，可随时删 |
| `data/backups/` | 备份 ZIP，可随时删 |

**常见操作**

- **想清空所有数据重新开始**：关闭程序 → 删除 `data/mathbank.db` → 重启。
- **换电脑**：把整个 `data/` 目录拷过去即可。
- **数据没保存**：本系统所有修改都是即时写库的，除非看到红色报错，否则不会丢。
""")


# ============================================================
# 入口
# ============================================================
def render():
    _init_state()
    _show_flash()

    st.header("⚙️ 系统设置")
    st.caption("备份、恢复、清理与信息。谨慎操作会标红提示。")

    tab1, tab2, tab3, tab4 = st.tabs(["📦 备份 / 导出", "♻️ 恢复", "🧹 清理", "ℹ️ 关于"])
    with tab1:
        _render_backup()
    with tab2:
        _render_restore()
    with tab3:
        _render_cleanup()
    with tab4:
        _render_about()