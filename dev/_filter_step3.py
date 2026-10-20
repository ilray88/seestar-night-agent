"""Step 3 of the filter experiment: start the stack and watch the wheel."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:5555/api/v1/telescope/1/action"
_tx = [60000]


def native(method, params=None, timeout=60):
    _tx[0] += 1
    body = json.dumps({
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1, "ClientTransactionID": _tx[0],
    }).encode()
    req = urllib.request.Request(BASE, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="PUT")
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def res(d):
    return d.get("Value", {}).get("result")


def wheel():
    try:
        return res(native("get_wheel_position"))
    except Exception as e:
        return f"ERR {e}"


def state():
    try:
        v = res(native("get_view_state")).get("View", {})
        return v.get("state"), v.get("stage"), (v.get("Stack") or {}).get("stacked_frame")
    except Exception as e:
        return f"ERR {e}", None, None


print("=== before start ===")
st, stage, stacked = state()
print(f"  wheel={wheel()} state={st} stage={stage} stacked={stacked}")

print("=== start stack, restart=False (resume, keeps frames) ===")
r = native("iscope_start_stack", {"restart": False}, timeout=90)
print("  ->", json.dumps(res(r), ensure_ascii=False)[:160])

for i in range(12):
    time.sleep(3)
    st, stage, stacked = state()
    print(f"  +{3*(i+1):2d}s wheel={wheel()} state={st} stage={stage} stacked={stacked}")
