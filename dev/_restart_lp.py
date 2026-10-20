"""Restart the running stack so that it is pure LP from frame 1.

The device resets the wheel to 1 (IRCUT) whenever iscope_start_stack is
called, so the sequence has to be:

    stop  -> set wheel 2 (persists while stopped)
          -> start stack (resets wheel to 1)
          -> set wheel 2 again *while running* (this one sticks)

Verified 2026-10-20 01:07: setting the wheel while state=working holds and
the sub-frame filenames flip to LP.
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:5555/api/v1/telescope/1/action"
_tx = [91000]


def native(method, params=None, timeout=60):
    _tx[0] += 1
    body = json.dumps({
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": _tx[0],
    }).encode()
    req = urllib.request.Request(BASE, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="PUT")
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def res(d):
    return d["Value"].get("result")


def view():
    return res(native("get_view_state"))["View"]


def state():
    v = view()
    return v.get("state"), v.get("stage"), (v.get("Stack") or {}).get("stacked_frame")


def wheel():
    return res(native("get_wheel_position"))


st, stage, n = state()
print("before: state=%s stage=%s stacked=%s wheel=%s" % (st, stage, n, wheel()))

print("stop stack ...")
print("  stop ->", res(native("iscope_stop_view", ["Stack"])))
for i in range(15):
    time.sleep(2)
    st, stage, n = state()
    if st != "working":
        break
print("  left working after %ds -> state=%s" % ((i + 1) * 2, st))

print("set wheel 2 while stopped ...")
print("  set ->", res(native("set_wheel_position", [2])))
time.sleep(3)
print("  wheel =", wheel())

print("restart stack (restart=True) ...")
print("  start ->", res(native("iscope_start_stack", {"restart": True})))
time.sleep(3)

# The critical step: re-apply the wheel while the stack is running.
print("re-apply wheel 2 while running ...")
print("  set ->", res(native("set_wheel_position", [2])))

for i in range(8):
    time.sleep(3)
    st, stage, n = state()
    w = wheel()
    print("  +%2ds wheel=%s state=%s stacked=%s" % ((i + 1) * 3, w, st, n))
