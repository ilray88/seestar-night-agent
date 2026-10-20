"""One-off: make sure the filter wheel is really where the plan wants it.

The device silently refuses set_wheel_position / set_setting while a stack is
running (it answers error "stack is already running" / code 259 but the
JSON-RPC envelope still says result=0).  This script stops the stack first,
sets the wheel, verifies by reading it back, then restarts the stack.
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:5555/api/v1/telescope/1/action"
_TX = [77000]


def native(method, params=None, timeout=60):
    _TX[0] += 1
    body = json.dumps({
        "Action": "method_sync",
        "Parameters": json.dumps({"method": method, "params": params or {}}),
        "ClientID": 1,
        "ClientTransactionID": _TX[0],
    }).encode()
    req = urllib.request.Request(BASE, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="PUT")
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def view():
    return native("get_view_state")["Value"]["result"]["View"]


def wheel():
    return native("get_wheel_position")["Value"]["result"]


def main():
    want = 2  # LP
    v = view()
    print("target", v.get("target_name"), "state", v.get("state"),
          "stacked", (v.get("Stack") or {}).get("stacked_frame"))
    print("wheel before:", wheel())

    if wheel() == want:
        print("wheel already correct, nothing to do")
        return

    if v.get("state") == "working":
        native("iscope_stop_view", ["Stack"])
        print("stop sent")
        for _ in range(20):
            time.sleep(2)
            if view().get("state") != "working":
                break
        print("state now:", view().get("state"))

    for attempt in range(5):
        r = native("set_wheel_position", [want])
        err = (r.get("Value") or {}).get("error")
        for _ in range(10):
            time.sleep(3)
            w = wheel()
            if w == want:
                break
        print("attempt", attempt + 1, "wheel:", w, "err:", err)
        if w == want:
            break

    print("restarting stack")
    native("iscope_start_stack", {"restart": False})
    time.sleep(5)
    v = view()
    stk = v.get("Stack") or {}
    print("after: state", v.get("state"), "stage", v.get("stage"),
          "stacked", stk.get("stacked_frame"),
          "exp", (stk.get("Exposure") or {}).get("exp_ms"),
          "wheel", wheel())


if __name__ == "__main__":
    main()
