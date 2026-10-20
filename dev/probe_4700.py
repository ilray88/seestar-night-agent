"""直接对 4700 端口发 JSON-RPC 探测，确认是否 Seestar。"""
import json
import socket
import sys

ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.20.75"


def rpc(port, obj, timeout=5.0, read_timeout=4.0):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.sendall((json.dumps(obj) + "\r\n").encode())
        s.settimeout(read_timeout)
        chunks = []
        while True:
            try:
                d = s.recv(65536)
            except socket.timeout:
                break
            if not d:
                break
            chunks.append(d)
            if len(b"".join(chunks)) > 200000:
                break
        return b"".join(chunks)
    except Exception as e:
        return f"ERR {type(e).__name__}: {e}".encode()
    finally:
        s.close()


print("=== 4700: scan_iscope ===")
print(rpc(4700, {"id": 1, "method": "scan_iscope", "params": {}})[:800])

print("\n=== 4700: get_device_state ===")
print(rpc(4700, {"id": 2, "method": "get_device_state", "params": {}})[:800])

print("\n=== 4700: pi_is_verified ===")
print(rpc(4700, {"id": 3, "method": "pi_is_verified", "params": {}})[:400])
