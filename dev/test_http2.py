import urllib.request, urllib.parse
host="192.168.2.118"
def try_get(p):
    url=f"http://{host}/{urllib.parse.quote(p)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url,method="GET"),timeout=8) as r:
            d=r.read(4000)
            return f"OK {p} status={r.status} len(first)={len(d)} body={d[:200]!r}"
    except Exception as e:
        return f"ERR {p} -> {type(e).__name__}: {str(e)[:80]}"

# directory listing attempts
for p in ["MyWorks/", "MyWorks", "MyWorks/M 31/", "MyWorks/M 31_sub/"]:
    print(try_get(p)); print()
# FITS extensions
for ext in ["fit","fits"]:
    print(try_get(f"MyWorks/M 31_sub/Light_M 31_20.0s_IRCUT_20261018-200758.{ext}")); print()
