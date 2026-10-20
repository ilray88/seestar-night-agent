import urllib.request, urllib.parse
host="192.168.2.118"
def head(p):
    url=f"http://{host}/{urllib.parse.quote(p)}"
    req=urllib.request.Request(url, method="GET", headers={"Range":"bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            cr = r.headers.get("Content-Range")
            cl = r.headers.get("Content-Length")
            return f"OK {p}  Content-Range={cr}  Content-Length={cl}"
    except Exception as e:
        return f"ERR {p} {type(e).__name__} {str(e)[:80]}"

print(head("MyWorks/M 31_sub/Light_M 31_20.0s_IRCUT_20261018-200758.fit"))
print(head("MyWorks/M 31/Stacked_41_M 31_20.0s_IRCUT_20261018-200814.jpg"))
