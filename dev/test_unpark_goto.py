"""Verify a goto works straight out of the parked state."""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "scripts")
import night_runner as NR

print("parked state:", (NR.try_native("get_device_state") or {}).get("mount"))

r = NR.goto_target_alpaca(0.7123, 41.2687, name="M31")
print("goto from parked:", r.get("ErrorNumber"), r.get("ErrorMessage"))

for i in range(45):
    time.sleep(4)
    p = NR.real_pointing()
    m = (NR.try_native("get_device_state") or {}).get("mount", {})
    if p:
        err = max(abs(p[0] - 0.7123) * 15, abs(p[1] - 41.2687))
        if i % 3 == 0:
            print(f"{i*4}s err={err:.2f} close={m.get('close')} "
                  f"move={m.get('move_type')}")
        if err < 0.3 and m.get("close") is False:
            print(f"REACHED in {i*4}s, err={err:.2f}")
            break
else:
    print("did not confirm")
