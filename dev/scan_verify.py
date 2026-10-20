"""Verify that pointing reads back correctly after a goto."""
from __future__ import annotations

import sys
import time

import scan_sky as S

az = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
alt = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0

print("equ before:", S.equ_coord())

ra, dec = S.altaz_to_radec(az, alt)
print(f"target az={az:.1f} alt={alt:.1f} -> RA={ra:.4f}h Dec={dec:.4f}")

print("goto:", (S.goto(ra, dec, name="verify") or {}).get("ErrorNumber"))
t0 = time.time()
ok, err = S.wait_settled(ra, dec, timeout=180)
print(f"settled={ok} err={err} in {time.time()-t0:.1f}s")

cur = S.equ_coord()
if cur:
    back_az, back_alt = S.radec_to_altaz(*cur)
    print(f"actual RA={cur[0]:.4f}h Dec={cur[1]:.4f} -> az={back_az:.1f} alt={back_alt:.1f}")
    print(f"delta az={back_az-az:+.1f} alt={back_alt-alt:+.1f}")
print("frame:", S.analyse(S.grab()))
