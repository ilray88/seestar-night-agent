import json
import urllib.request

def native(m, p=None, timeout=40):
    body = json.dumps({
        "Action": "method_sync",
        "Parameters": json.dumps({"method": m, "params": p if p is not None else {}}),
        "ClientID": 1, "ClientTransactionID": 7711,
    }).encode()
    r = urllib.request.Request(
        "http://127.0.0.1:5555/api/v1/telescope/1/action",
        data=body, headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.loads(f.read())


# 1) full setting structure
d = native("get_device_state")["Value"]["result"]
print("=== device_state.setting ===")
print(json.dumps(d.get("setting", {}), ensure_ascii=False, indent=2))
print("=== pi_status (subset) ===")
ps = d.get("pi_status", {})
print(json.dumps({k: ps[k] for k in list(ps)[:14]}, ensure_ascii=False, indent=2))

# 2) album listing -> ground truth for filter used
print()
print("=== albums: IC405 / IC405_sub ===")
alb = native("get_albums")["Value"]["result"]
groups = alb.get("list") or alb.get("albums") or alb
if isinstance(groups, dict):
    groups = groups.get("list", [])


def walk(node, depth=0):
    if isinstance(node, dict):
        name = node.get("name")
        if name and ("IC405" in str(name) or "IC1805" in str(name) or "NGC1499" in str(name)):
            fn = node.get("files") or node.get("file") or []
            print(" " * depth, "DIR:", name, "files:", len(fn) if isinstance(fn, list) else fn)
            if isinstance(fn, list):
                for f in fn[:4]:
                    if isinstance(f, dict):
                        print(" " * (depth + 2), f.get("name"))
                    else:
                        print(" " * (depth + 2), f)
        inner = node.get("list") or node.get("albums") or node.get("children")
        if isinstance(inner, list):
            for c in inner:
                walk(c, depth + 2)
    elif isinstance(node, list):
        for c in node:
            walk(c, depth)


print("keys:", list(alb)[:10] if isinstance(alb, dict) else type(alb))
walk(groups)

# 3) current view
v = native("get_view_state")["Value"]["result"]["View"]
st = v.get("Stack", {})
print()
print("=== view ===")
print("target=%s stage=%s state=%s stacked=%s dropped=%s exp=%s" % (
    v.get("target_name"), v.get("stage"), v.get("state"),
    st.get("stacked_frame"), st.get("dropped_frame"),
    (st.get("Exposure") or {}).get("exp_ms")))
print("wheel:", native("get_wheel_position")["Value"]["result"])
