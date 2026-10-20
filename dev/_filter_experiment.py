"""Definitive filter-wheel experiment.

Ground truth from get_albums: on 2026-10-18 the scope produced
`Light_NGC 6992_20.0s_LP_...`, so the LP wheel position IS reachable.  Tonight
every sub is IRCUT.  Hypothesis: the runner sets the wheel while the previous
target's stack is still running, the device silently ignores it (same class of
failure as set_setting code 259), and nothing re-sends it afterwards.

This script walks the exact sequence and polls the wheel after every step:
    stop stack -> set wheel 2 -> start stack
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:5555/api/v1/telescope/1/action"
_tx = [50000]


def native(method, params=None, timeout=40):
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


def show(tag):
    st, stage, stacked = state()
    print(f"  [{tag}] wheel={wheel()}  state={st} stage={stage} stacked={stacked}")


print("=== before ===")
show("init")

print("=== step 1: stop stack ===")
print("  stop ->", res(native("iscope_stop_view", ["Stack"])))
for i in range(15):
    time.sleep(2)
    st = state()[0]
    if st != "working":
        print(f"  state left 'working' after {2*(i+1)}s -> {st}")
        break
show("after stop")

print("=== step 2: set wheel to 2 (LP) ===")
print("  set ->", res(native("set_wheel_position", [2])))
for i in range(10):
    time.sleep(3)
    print(f"    +{3*(i+1):2d}s wheel={wheel()}  wstate={res(native('get_wheel_state'))}")

print("=== step 3: start stack (restart=True) ===")
print("  start ->", json.dumps(res(native("iscope_start_stack", {"restart": True}),
                                 timeout=60), ensure_ascii=False)[:120])
for i in range(10):
    time.sleep(3)
    st, stage, stacked = state()
    print(f"    +{3*(i+1):2d}s wheel={wheel()}  state={st} stage={stage} stacked={stacked}")

print("=== final ===")
show("final")
