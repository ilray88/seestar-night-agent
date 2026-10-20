"""Single-point goto test: verify command path + measure frame."""
from __future__ import annotations

import json
import sys

import scan_sky as S


def main():
    az = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    alt = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0

    print(f"current: RA={S._req('rightascension').get('Value')} "
          f"Dec={S._req('declination').get('Value')}")

    # stop any running view first (phone app may have left one running)
    try:
        print("stop_view:", S.native("iscope_stop_view", ["ContinuousExposure"], timeout=40))
    except Exception as e:
        print("stop_view err:", e)
    try:
        print("stop stack:", S.native("iscope_stop_view", ["Stack"], timeout=40))
    except Exception as e:
        print("stop stack err:", e)

    ra, dec = S.altaz_to_radec(az, alt)
    print(f"target az={az} alt={alt} -> RA={ra:.4f}h Dec={dec:.4f}")

    r = S.goto(ra, dec, name="test")
    print("goto reply:", json.dumps(r)[:400])

    ok = S.wait_slew(120)
    print("slew done:", ok)

    got_ra = S._req("rightascension").get("Value")
    got_dec = S._req("declination").get("Value")
    back_az, back_alt = S.radec_to_altaz(got_ra, got_dec)
    print(f"reported after: RA={got_ra:.4f}h Dec={got_dec:.4f} -> az={back_az:.1f} alt={back_alt:.1f}")
    print("delta az=%.1f alt=%.1f" % (back_az - az, back_alt - alt))

    stats = S.analyse(S.grab())
    print("frame:", stats)


if __name__ == "__main__":
    main()
