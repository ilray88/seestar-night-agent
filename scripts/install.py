# -*- coding: utf-8 -*-
"""一次性安装：为两个依赖环境创建 venv 并装好包。

为什么要两套环境
----------------
`seestar_alp` 和 `seestar-mcp` 的依赖互不兼容：
  * seestar_alp 需要较宽松的 numpy，且要 astropy 做坐标计算
  * seestar-mcp 锁定了较新的 numpy/scipy
强行合成一个环境会互相破坏，所以上游本身就是分开的两个项目。

本脚本在 vendor/ 下分别建 .venv，并生成 config/config.toml。

用法
----
    python scripts/install.py
    python scripts/install.py --alp-only
    python scripts/install.py --python C:\\Python312\\python.exe
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
CONFIG = ROOT / "config"


def run(cmd: list[str], cwd: Path) -> None:
    print("\n$ " + " ".join(str(c) for c in cmd) + f"   (cwd={cwd})")
    r = subprocess.run(cmd, cwd=str(cwd))
    if r.returncode != 0:
        raise SystemExit(f"命令失败，退出码 {r.returncode}")


def venv_python(project: Path) -> Path:
    if sys.platform == "win32":
        return project / ".venv" / "Scripts" / "python.exe"
    return project / ".venv" / "bin" / "python"


def make_venv(project: Path, python: str) -> Path:
    py = venv_python(project)
    if py.exists():
        print(f"[跳过] venv 已存在: {py}")
        return py
    run([python, "-m", "venv", str(project / ".venv")], cwd=project)
    return py


def pip_install(py: Path, project: Path, extra: str | None = None) -> None:
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        cwd=project)
    target = extra or "."
    run([str(py), "-m", "pip", "install", "-e", target], cwd=project)


def ensure_config() -> None:
    example = CONFIG / "config.example.toml"
    actual = CONFIG / "config.toml"
    if actual.exists():
        print(f"[跳过] 配置已存在: {actual}")
    elif example.exists():
        shutil.copy2(example, actual)
        print(f"[创建] {actual}（从 config.example.toml 复制）")
    else:
        print("[警告] 找不到 config.example.toml")

    # 代码从 seestar_alp/device/config.toml 读取，保持一份同步副本
    dst = VENDOR / "seestar_alp" / "device" / "config.toml"
    if actual.exists() and not dst.exists():
        shutil.copy2(actual, dst)
        print(f"[创建] {dst}")


def main() -> int:
    ap = argparse.ArgumentParser(description="安装 Seestar 无人值守环境")
    ap.add_argument("--python", default=sys.executable,
                    help="用于创建 venv 的 Python 解释器（建议 3.11/3.12）")
    ap.add_argument("--alp-only", action="store_true", help="只装 seestar_alp")
    ap.add_argument("--mcp-only", action="store_true", help="只装 seestar-mcp")
    args = ap.parse_args()

    if sys.version_info < (3, 11):
        print(f"[错误] 需要 Python >= 3.11，当前 {sys.version.split()[0]}")
        return 1

    ensure_config()

    alp = VENDOR / "seestar_alp"
    mcp = VENDOR / "seestar-mcp"

    if not args.mcp_only:
        if not alp.exists():
            print(f"[错误] 缺少 {alp}（vendor 目录应由仓库提供）")
            return 1
        py = make_venv(alp, args.python)
        pip_install(py, alp)

    if not args.alp_only:
        if not mcp.exists():
            print(f"[错误] 缺少 {mcp}")
            return 1
        py = make_venv(mcp, args.python)
        pip_install(py, mcp)

    print("\n安装完成。")
    print("下一步：")
    print("  1) 编辑 config/config.toml 里的 ip_address 指向你的望远镜")
    print("  2) 运行 1-启动Seestar后端.bat（或 python root_app.py）")
    print("  3) 运行 scripts/check.ps1 做体检")
    return 0


if __name__ == "__main__":
    sys.exit(main())
