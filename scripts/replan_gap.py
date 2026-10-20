"""Re-plan the remaining night using the LOW-CLOUD criterion.

The original plan parked the mount during 00:45-03:05 because the weather
model (gated on TOTAL cloud) predicted 85-97%.  The low-cloud forecast is
0-1% for that entire stretch, so the gap is actually the best part of the
night and should be filled with targets.
"""
from datetime import datetime, timedelta, timezone

from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time
import astropy.units as u

BJT = timezone(timedelta(hours=8))
LAT, LON = 22.7261, 114.046
loc = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg)

WIN_MIN, WIN_MAX = 330.0, 110.0
ALT_MIN, ALT_MAX = 20.0, 75.0

TARGETS = {
    "M31":       (0.7123, 41.2687, "galaxy"),
    "M45":       (3.7833, 24.1167, "cluster"),
    "NGC1499":   (4.0556, 36.6333, "emission"),
    "NGC891":    (2.3759, 42.3490, "galaxy"),
    "NGC2392":   (7.4863, 20.9120, "planetary"),
    "M35":       (6.1483, 24.3330, "cluster"),
    "M1":        (5.5755, 22.0140, "snr"),
    "M82":       (9.9312, 69.6800, "galaxy"),
    "M81":       (9.9259, 69.0650, "galaxy"),
    "NGC2403":   (7.6143, 65.6000, "galaxy"),
    "IC342":     (3.7801, 68.0960, "galaxy"),
    "IC405":     (5.2670, 34.3000, "emission"),
    "IC410":     (5.3670, 33.3000, "emission"),
    "NGC281":    (0.8670, 56.6000, "emission"),
    "NGC7635":   (23.3330, 61.2000, "emission"),
    "NGC7380":   (22.7830, 58.1000, "emission"),
    "IC1396":    (21.6500, 57.5000, "emission"),
    "IC443":     (6.2830, 22.5000, "emission"),
    "M36":       (5.6000, 34.1333, "cluster"),
    "M37":       (5.8717, 32.5500, "cluster"),
    "M38":       (5.4667, 35.8500, "cluster"),
    "NGC6543":   (17.9770, 66.6330, "planetary"),
    "NGC7000":   (20.9833, 44.3333, "emission"),
}


def in_window(az):
    return az >= WIN_MIN or az <= WIN_MAX


def altaz(ra_h, dec, when):
    c = SkyCoord(ra=ra_h * 15 * u.deg, dec=dec * u.deg, frame="icrs")
    t = Time(when)
    return c.transform_to(AltAz(obstime=t, location=loc))


def scan(name, ra, dec, t0, t1, step_min=10):
    """Return list of (time, alt, az, ok) samples through [t0, t1]."""
    out = []
    t = t0
    while t <= t1:
        aa = altaz(ra, dec, t)
        ok = in_window(aa.az.deg) and ALT_MIN <= aa.alt.deg <= ALT_MAX
        out.append((t, aa.alt.deg, aa.az.deg, ok))
        t += timedelta(minutes=step_min)
    return out


def summarize(name, ra, dec, t0, t1):
    s = scan(name, ra, dec, t0, t1)
    ok = [x for x in s if x[3]]
    if not ok:
        return None
    # longest continuous run
    best = cur = [ok[0]]
    prev = ok[0][0]
    for x in ok[1:]:
        if (x[0] - prev).total_seconds() <= 660:
            cur.append(x)
        else:
            if len(cur) > len(best):
                best = cur
            cur = [x]
        prev = x[0]
    if len(cur) > len(best):
        best = cur
    mins = (best[-1][0] - best[0][0]).total_seconds() / 60 + 10
    return {
        "name": name,
        "type": TARGETS[name][2],
        "start": best[0][0],
        "end": best[-1][0],
        "mins": mins,
        "az0": best[0][2],
        "az1": best[-1][2],
        "alt0": best[0][1],
        "alt1": best[-1][1],
        "altmax": max(x[1] for x in best),
    }


def main():
    # remaining night, in BJT
    t_start = datetime(2026, 10, 20, 0, 0, tzinfo=BJT)
    t_end = datetime(2026, 10, 20, 5, 30, tzinfo=BJT)

    print("=" * 96)
    print("Sun / twilight check (Shenzhen, 2026-10-20)")
    print("=" * 96)
    from astropy.coordinates import get_sun
    for hh in [4, 5, 5.5, 6]:
        t = datetime(2026, 10, 20, int(hh), int((hh % 1) * 60), tzinfo=BJT)
        sun = get_sun(Time(t)).transform_to(AltAz(obstime=Time(t), location=loc))
        print(f"  {t:%H:%M}  sun alt = {sun.alt.deg:6.2f} deg")

    print()
    print("=" * 96)
    print(f"Window az {WIN_MIN}->{WIN_MAX}, alt {ALT_MIN}-{ALT_MAX}; scan 00:00-05:30 BJT")
    print("=" * 96)
    rows = []
    for name, (ra, dec, _typ) in TARGETS.items():
        r = summarize(name, ra, dec, t_start, t_end)
        if r and r["mins"] >= 30:
            rows.append(r)
    rows.sort(key=lambda r: -r["mins"])

    print(f"{'target':<10}{'type':<11}{'win':<18}{'mins':>6}  {'az':>14}  {'alt':>12}")
    print("-" * 96)
    for r in rows:
        win = f"{r['start']:%H:%M}-{r['end']:%H:%M}"
        print(f"{r['name']:<10}{r['type']:<11}{win:<18}{r['mins']:>6.0f}  "
              f"{r['az0']:6.1f}->{r['az1']:6.1f}  "
              f"{r['alt0']:5.1f}->{r['alt1']:5.1f} ({r['altmax']:.1f})")

    print()
    print("=" * 96)
    print("Gap 00:45-03:05 candidates (detail)")
    print("=" * 96)
    g0 = datetime(2026, 10, 20, 0, 45, tzinfo=BJT)
    g1 = datetime(2026, 10, 20, 3, 5, tzinfo=BJT)
    for name, (ra, dec, _typ) in TARGETS.items():
        s = scan(name, ra, dec, g0, g1)
        okc = sum(1 for x in s if x[3])
        if okc < len(s) * 0.6:
            continue
        print(f"\n{name} ({TARGETS[name][2]})  {okc}/{len(s)} samples in window")
        for t, alt, az, ok in s:
            flag = "OK " if ok else "-- "
            print(f"   {t:%H:%M}  alt={alt:6.1f}  az={az:6.1f}  {flag}")


if __name__ == "__main__":
    main()
