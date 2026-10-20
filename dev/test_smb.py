import sys
try:
    import smbclient
    print("smbclient OK")
except Exception as e:
    print("import fail:", e); sys.exit(1)

host = "192.168.20.90"
# list shares
try:
    print("--- shares ---")
    for s in smbclient.list_shares(host, username="guest", password=""):
        print("SHARE:", repr(s.name), s.type)
except Exception as e:
    print("list_shares ERR:", type(e).__name__, e)

for share in ["EMMC Images", "EMMC_Images", "share", "MyWorks"]:
    try:
        entries = list(smbclient.scandir(rf"\\{host}\{share}", username="guest", password=""))
        print(f"DIR OK {share!r}: {len(entries)} entries")
        for e in entries[:8]:
            print("   ", e.name, "dir" if e.is_dir() else "file")
    except Exception as e:
        print(f"DIR ERR {share!r}:", type(e).__name__, str(e)[:120])
