"""读取/修改 Seestar 的 auto_power_off 设置。

通过 seestar_alp 已建立的 4700 连接发送 set_setting 命令。
注意：设备只允许单一 TCP 连接，因此不能另开连接，必须复用后端进程。
这里改为调用后端的 Web 路由（front/app.py 的 /settings）来下发。
"""
import json
import sys
import urllib.request
import urllib.parse

BASE = "http://127.0.0.1:5432"
CMD = "http://127.0.0.1:5555"


def post(url, data=None):
    body = urllib.parse.urlencode(data or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "read"
    if action == "read":
        code, body = get(f"{BASE}/eventstatus")
        try:
            j = json.loads(body)
            print("eventstatus keys:", list(j.keys())[:20])
        except Exception:
            print(body[:500])
