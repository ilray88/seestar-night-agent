import urllib.request, urllib.parse, ssl
host = "192.168.2.118"
paths = [
    "/M 31/Stacked_41_M 31_20.0s_IRCUT_20261018-200814.jpg",
    "/MyWorks/M 31/Stacked_41_M 31_20.0s_IRCUT_20261018-200814.jpg",
    "/M 31_sub/Light_M 31_20.0s_IRCUT_20261018-200758.fit",
    "/EMMC Images/MyWorks/M 31/Stacked_41_M 31_20.0s_IRCUT_20261018-200814.jpg",
]
for p in paths:
    url = f"http://{host}/{urllib.parse.quote(p.lstrip('/'))}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as r:
            data = r.read()
            print(f"OK  {p}\n    status={r.status} len={len(data)} head={data[:8]!r}")
    except Exception as e:
        print(f"ERR {p}\n    {type(e).__name__}: {str(e)[:140]}")
