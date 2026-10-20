#!/usr/bin/env python3
"""extract_pem.py — 从你自有的 ZWO Seestar 安卓 APK 中提取 interop RSA 私钥。

用途（ interoperability, 17 U.S.C. §1201(f) ）：
  Seestar 固件 7.18+（含你的 9.75）对本地 JSON-RPC 接口（端口 4700）加了
  RSA 挑战-应答握手。第三方程序必须先证明"持有与官方 App 相同的私钥"，
  否则望远镜会静默忽略所有命令（表现就是"连上了但没有任何响应"）。

原理：官方 App 的 APK 里 lib/arm64-v8a/libopenssllib.so 以明文文本形式
  内嵌了这把私钥（-----BEGIN PRIVATE KEY----- 块）。本工具对 .so 做
  strings 式扫描，把找到的 PEM 块写出来。它是通用工具，不含任何 ZWO 代码，
  也不内置任何密钥。

用法：
  python extract_pem.py Seestar_v3.4.0.apk
  python extract_pem.py Seestar_v3.4.0.apk -o seestar_client_key.pem
  python extract_pem.py Seestar_v3.4.0.apk --stdout

无需第三方依赖，仅用标准库。
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
from pathlib import Path

BEGIN = "-----BEGIN PRIVATE KEY-----"
END = "-----END PRIVATE KEY-----"
# 也接受更老风格的 RSA PRIVATE KEY 块
PATTERNS = [
    re.compile(rb"-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----", re.DOTALL),
    re.compile(rb"-----BEGIN RSA PRIVATE KEY-----.*?-----END RSA PRIVATE KEY-----", re.DOTALL),
]
# APK 中可能承载密钥的原生库候选
SO_CANDIDATES = [
    "lib/arm64-v8a/libopenssllib.so",
    "lib/armeabi-v7a/libopenssllib.so",
    "lib/x86_64/libopenssllib.so",
    "lib/x86/libopenssllib.so",
]


def find_keys(data: bytes) -> list[bytes]:
    found: list[bytes] = []
    for pat in PATTERNS:
        for m in pat.finditer(data):
            block = m.group(0)
            if block not in found:
                found.append(block)
    return found


def _iter_zip_members(z: zipfile.ZipFile, prefix: str = ""):
    """遍历 zip 成员；若是 XAPK（内含 split apk），继续向下钻取。"""
    for name in z.namelist():
        if name.endswith(".apk"):
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(name)))
            except Exception:
                continue
            yield from _iter_zip_members(inner, prefix + name + "!")
            continue
        if name.endswith(".so"):
            yield prefix + name, z, name


def scan_apk(apk: Path) -> list[bytes]:
    keys: list[bytes] = []
    with zipfile.ZipFile(apk) as z:
        members = list(_iter_zip_members(z))
        # 先按已知库名找
        preferred = [m for m in members if m[0].split("!")[-1] in SO_CANDIDATES]
        others = [m for m in members if m not in preferred]
        for label, zf, name in preferred + others:
            try:
                data = zf.read(name)
            except Exception:
                continue
            keys.extend(find_keys(data))
            if keys:
                print(f"[+] 在 {label} 中找到 {len(keys)} 个密钥块", file=sys.stderr)
                break
    return keys


def main() -> int:
    ap = argparse.ArgumentParser(description="从 Seestar APK 提取 interop 私钥 (PEM)")
    ap.add_argument("apk", help="Seestar 安卓 APK 路径（你自己下载的官方包）")
    ap.add_argument("-o", "--out", default="seestar_client_key.pem",
                    help="输出 PEM 路径（默认 seestar_client_key.pem）")
    ap.add_argument("--stdout", action="store_true", help="打印到标准输出而不写文件")
    args = ap.parse_args()

    apk = Path(args.apk)
    if not apk.is_file():
        print(f"[x] 找不到 APK: {apk}", file=sys.stderr)
        return 2
    if not zipfile.is_zipfile(apk):
        print(f"[x] 不是有效的 APK/ZIP: {apk}", file=sys.stderr)
        return 2

    print(f"[*] 扫描 {apk.name} ...", file=sys.stderr)
    keys = scan_apk(apk)
    if not keys:
        print("[x] 没找到私钥块。确认这是官方 Seestar APK，且未被重新打包。",
              file=sys.stderr)
        return 1

    if args.stdout:
        for i, k in enumerate(keys):
            if len(keys) > 1:
                print(f"# ----- key #{i} -----", file=sys.stderr)
            sys.stdout.write(k.decode("ascii", errors="replace").strip() + "\n")
        return 0

    out = Path(args.out)
    with open(out, "wb") as f:
        f.write(keys[0])
        if not keys[0].endswith(b"\n"):
            f.write(b"\n")
    print(f"[+] 已写入 {out.resolve()} （{len(keys)} 个候选，取第 1 个）", file=sys.stderr)
    if len(keys) > 1:
        print(f"[!] APK 含多个密钥块；如连接失败，可试 --stdout 逐个替换。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
