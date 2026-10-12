# -*- coding: utf-8 -*-
"""题目管理系统 —— 自动化自测入口。

跑法（在项目根目录）：

    python tools/verify/run.py

它会做三件事：
 1. 把数据目录切到一个临时沙箱（环境变量 MATHBANK_DATA_DIR），
    **绝不会碰你真实的 data/ 题库**；
 2. 在沙箱里建库、造几道带图的测试题；
 3. 依次跑各页检查，打印 通过/失败。

任何一项失败，退出码为 1。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent   # 项目根目录
CHECKS_DIR = Path(__file__).resolve().parent / "checks"

CHECKS = [
    ("列表顺序 / 按钮位置 / 图片分组渲染", "_verify.py"),
    ("编辑器的题干配图与解析配图", "_verify_editor.py"),
    ("正文里的图片定位标记 ![[img:N]]", "_verify_inline_images.py"),
    ("改完立刻生效（缓存失效）", "_verify_freshness.py"),
    ("导出（HTML / Markdown / Word）与孤儿图片识别", "_verify_export.py"),
    ("导入的公式体检与重复题覆盖导入", "_verify_import.py"),
]


def run_script(script: Path | str, data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["MATHBANK_DATA_DIR"] = str(data_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(BASE_DIR)
    path = script if isinstance(script, Path) else (CHECKS_DIR / script)
    return subprocess.run(
        [sys.executable, str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(BASE_DIR),
    )


def run_one(script: str, data_dir: Path) -> tuple[bool, str]:
    # 先在这份沙箱数据目录里造测试数据，再跑检查
    seed = run_script(CHECKS_DIR / "_seed.py", data_dir)
    if seed.returncode != 0:
        return False, f"造数据失败：\n{seed.stdout}\n{seed.stderr}"

    proc = run_script(script, data_dir)
    out = proc.stdout or ""
    lines = [ln for ln in out.splitlines()
             if "PASS" in ln or "FAIL" in ln or "通过" in ln]
    if not lines:
        tail = "\n".join((out or proc.stderr or "").splitlines()[-25:])
        lines = [f"（没有拿到检查输出，末尾信息如下）\n{tail}"]
    return proc.returncode == 0, "\n".join(lines)


def main() -> int:
    # 沙箱数据目录放在项目内，跑完就删。
    # 注意：这个目录名不能以 "." 开头 —— 那样可能命中系统/安全软件的受限路径规则。
    sandbox_root = BASE_DIR / "selftest_tmp"
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sandbox = sandbox_root / f"run_{os.getpid()}"
    shutil.rmtree(sandbox, ignore_errors=True)
    sandbox.mkdir(parents=True, exist_ok=True)
    print(f"沙箱数据目录：{sandbox}")
    print("（你的真实 data/ 题库不会被改动）\n")
    if not Path(CHECKS_DIR).is_dir():
        print(f"找不到检查脚本目录：{CHECKS_DIR}")
        return 1

    failed = []
    try:
        for i, (title, script) in enumerate(CHECKS, start=1):
            # 每组检查用各自独立的数据目录，互不干扰。
            # 目录本身交给 src/config.py 在导入时创建（它会自动建 data/images 等）。
            data_dir = sandbox / f"case{i}"

            print(f"=== {title} ===")
            ok, out = run_one(script, data_dir)
            print(out or "（无输出）")
            if not ok:
                failed.append(title)
            print()

        print("=" * 48)
        if failed:
            print("结果：失败")
            for t in failed:
                print(f"  ✗ {t}")
            return 1
        print("结果：全部通过 ✓")
        return 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
        # 顺手把空的 .selftest_tmp 也收掉
        try:
            sandbox_root.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
