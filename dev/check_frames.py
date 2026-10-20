"""Check whether the MJPEG stream actually produces fresh frames."""
from __future__ import annotations

import hashlib
import sys
import time

import fresh_frame as F
import scan_sky as S

n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
print("counter now:", F.frame_counter())
for i in range(n):
    img = F.raw_frame()
    if img is None:
        print(f"{i}: NO FRAME")
    else:
        h = hashlib.md5(img).hexdigest()[:12]
        print(f"{i}: {len(img)} bytes  md5={h}  {S.analyse(img)}")
    time.sleep(3)
print("counter after:", F.frame_counter())
print("view:", str(S.native("get_view_state"))[:400])
