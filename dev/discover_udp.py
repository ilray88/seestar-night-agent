"""Seestar UDP 广播发现（scan_iscope on 4720）—— 权威确认设备 IP。"""
import json
import socket
import sys

TARGETS = ["255.255.255.255", "192.168.2.255", "192.168.20.255"]

msg = json.dumps({"id": 1, "method": "scan_iscope", "params": {}})

for tgt in TARGETS:
    print(f"--- broadcast {tgt}:4720 ---", flush=True)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(3.0)
    try:
        s.sendto(msg.encode(), (tgt, 4720))
    except Exception as e:
        print("  send err:", e, flush=True)
        s.close()
        continue
    seen = set()
    while True:
        try:
            data, addr = s.recvfrom(4096)
        except socket.timeout:
            break
        if addr[0] in seen:
            continue
        seen.add(addr[0])
        print(f"  REPLY from {addr[0]}:{addr[1]}", flush=True)
        print("   ", data[:400], flush=True)
    if not seen:
        print("  no reply", flush=True)
    s.close()
