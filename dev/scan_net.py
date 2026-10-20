"""快速扫描网段内的 Seestar 端口（32323 Alpaca / 4700 原生 / 4801 图像）。"""
import socket
import sys
import concurrent.futures as cf

PORTS = [32323, 4700, 4801, 4800]


def probe(ip: str, port: int, timeout=0.7):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return ip, port
    except Exception:
        return None
    finally:
        s.close()


def scan(prefix: str, ports=PORTS):
    ips = [f"{prefix}.{i}" for i in range(1, 255)]
    hits = []
    with cf.ThreadPoolExecutor(max_workers=256) as ex:
        futs = [ex.submit(probe, ip, p) for ip in ips for p in ports]
        for f in cf.as_completed(futs):
            r = f.result()
            if r:
                hits.append(r)
    return hits


if __name__ == "__main__":
    for prefix in sys.argv[1:]:
        print(f"--- scanning {prefix}.0/24 ---", flush=True)
        res = scan(prefix)
        if res:
            for ip, port in sorted(res):
                print(f"  OPEN {ip}:{port}", flush=True)
        else:
            print("  no open ports", flush=True)
