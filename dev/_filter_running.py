"""Set the filter wheel while the stack is RUNNING and see if it sticks."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:5555/api/v1/telescope/1/action"
_tx = [70000]


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
    v = res(native("get_view_state")).get("View", {})
    return v.get("state"), (v.get("Stack") or {}).get("stacked_frame")


st, stacked = state()
print(f"before: wheel={wheel()} state={st} stacked={stacked}")

print("set wheel 2 while running ->",
      json.dumps(native("set_wheel_position", [2]), ensure_ascii=False)[:200])

for i in range(14):
    time.sleep(3)
    st, stacked = state()
    print(f"  +{3*(i+1):2d}s wheel={wheel()} state={st} stacked={stacked}")
