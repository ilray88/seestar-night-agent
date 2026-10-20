"""Night planner for a N/NE window: az 330 -> 110 (wrapping through north).

Window: az in [330,360) U [0,110], alt in [20,70], sun < -15.
Reports per-target in-window intervals, field rotation, and moon separation.

ASCII-only output.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, get_sun
from astropy.time import Time
import astropy.units as u

LAT, LON, ELEV = 22.7261, 114.046, 40
loc = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ELEV * u.m)
LAT_R = np.radians(LAT)
W = 15.041

AZ_LO, AZ_HI = 330.0, 110.0     # wrapping window
ALT_MIN, ALT_MAX = 20.0, 70.0

CANDS = [
    ("M31", "Andromeda", 10.685, 41.269, "galaxy", 178, 3.4),
    ("M33", "Triangulum", 23.462, 30.660, "galaxy", 73, 5.7),
    ("NGC891", "Edge-on Gal", 35.64, 42.35, "galaxy", 14, 9.9),
    ("NGC2403", "Galaxy", 114.20, 65.60, "galaxy", 21, 8.4),
    ("M81", "Bode's", 148.89, 69.07, "galaxy", 27, 6.9),
    ("M82", "Cigar", 148.97, 69.68, "galaxy", 11, 8.4),
    ("IC1805", "Heart Neb", 38.20, 61.50, "emission", 60, 6.5),
    ("IC1848", "Soul Neb", 40.90, 60.40, "emission", 30, 6.5),
    ("NGC1499", "California", 60.00, 36.40, "emission", 145, 6.0),
    ("IC405", "Flaming Star", 79.05, 34.30, "emission", 30, 6.0),
    ("IC410", "Tadpoles", 79.10, 66.60, "emission", 25, 10.0),
    ("NGC281", "Pacman", 13.15, 56.60, "emission", 35, 7.4),
    ("NGC7635", "Bubble", 350.20, 61.20, "emission", 15, 10.0),
    ("NGC7380", "Wizard", 341.75, 58.117, "emission", 25, 7.2),
    ("IC1396", "Elephant Trunk", 324.70, 57.50, "emission", 170, 3.5),
    ("NGC7023", "Iris", 315.00, 68.20, "reflection", 10, 6.8),
    ("NGC7000", "N.America", 314.70, 44.30, "emission", 120, 4.0),
    ("IC5070", "Pelican", 313.00, 44.40, "emission", 60, 8.0),
    ("NGC6888", "Crescent", 303.00, 38.20, "emission", 18, 7.4),
    ("NGC6960", "W.Veil", 311.40, 30.70, "snr", 70, 7.0),
    ("M45", "Pleiades", 56.75, 24.117, "cluster", 110, 1.6),
    ("M35", "Gemini Cl", 92.27, 24.34, "cluster", 28, 5.3),
    ("NGC869", "Double Cl", 34.75, 57.10, "cluster", 60, 4.3),
    ("NGC457", "Owl Cl", 19.90, 58.20, "cluster", 20, 6.4),
    ("NGC663", "Cassiopeia Cl", 26.00, 61.20, "cluster", 16, 7.1),
    ("M103", "Open Cl", 23.30, 60.70, "cluster", 6, 7.4),
    ("M76", "Little Dumbbell", 25.58, 51.60, "planetary", 3, 10.1),
    ("M1", "Crab", 83.63, 22.01, "snr", 6, 8.4),
    ("NGC2392", "Eskimo", 112.29, 20.91, "planetary", 1.2, 9.9),
    ("NGC7789", "Caroline Rose", 358.47, 56.73, "cluster", 16, 6.7),
    ("IC59", "IC59 Neb", 359.30, 61.10, "emission", 30, None),
    ("NGC6543", "Cat's Eye", 269.64, 66.63, "planetary", 0.4, 8.1),
]

t0 = Time(datetime(2026, 10, 19, 11, 0, tzinfo=timezone.utc))   # 19:00 BJT
t1 = Time(datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc))   # 05:00 BJT
step_s = 300
n = int((t1 - t0).to_value(u.s) / step_s) + 1
times = t0 + np.arange(n) * step_s * u.s
frame = AltAz(obstime=times, location=loc)
sun = get_sun(times).transform_to(frame)
moon = get_body("moon", times, loc).transform_to(frame)
dark = sun.alt.deg < -15.0


def bjt(t):
    return (t.to_datetime() + timedelta(hours=8)).strftime("%H:%M")


def in_window(az):
    azm = np.mod(az, 360.0)
    return (azm >= AZ_LO) | (azm <= AZ_HI)


def runs(mask):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1)); start = None
    if start is not None:
        out.append((start, n - 1))
    return out


print("WINDOW az %.0f->%.0f (wrap), alt %.0f-%.0f, sun<-15, night 19:00-05:00 BJT"
      % (AZ_LO, AZ_HI, ALT_MIN, ALT_MAX))
print("%-9s %-15s %-10s %5s %5s %5s %6s %7s  %s" % (
    "ID", "Name", "kind", "from", "to", "min", "maxAlt", "rot/h", "az range"))
print("-" * 100)

rows = []
for tid, name, ra, dec, kind, size, mag in CANDS:
    c = SkyCoord(ra * u.deg, dec * u.deg)
    aa = c.transform_to(frame)
    alt, az = aa.alt.deg, aa.az.deg
    vis = (alt >= ALT_MIN) & (alt <= ALT_MAX) & in_window(az) & dark
    rr = runs(vis)
    if not rr:
        print("%-9s %-15s %-10s %5s %5s %5d %6s %7s  NO" % (tid, name, kind, "-", "-", 0, "-", "-"))
        continue
    a, b = max(rr, key=lambda r: r[1] - r[0])
    rot = np.abs(W * np.cos(LAT_R) * np.cos(np.radians(az[a:b + 1])) / np.cos(np.radians(alt[a:b + 1])))
    sep = aa[a:b + 1].separation(moon[a:b + 1]).deg
    r = dict(tid=tid, name=name, kind=kind, size=size, mag=mag, a=a, b=b,
             minutes=(b - a) * 5, maxalt=float(alt[a:b + 1].max()),
             rot=float(np.median(rot)), rotmax=float(rot.max()),
             az0=float(np.mod(az[a], 360)), az1=float(np.mod(az[b], 360)),
             alt0=float(alt[a]), alt1=float(alt[b]), moonsep=float(sep.min()),
             slots=[(x[0], x[1]) for x in rr])
    rows.append(r)
    print("%-9s %-15s %-10s %5s %5s %5d %6.1f %7.1f  %.0f->%.0f" % (
        tid, name, kind, bjt(times[a]), bjt(times[b]), r["minutes"],
        r["maxalt"], r["rot"], r["az0"], r["az1"]))

print("\n=== scheduling metadata (in-window segments) ===")
for r in sorted(rows, key=lambda x: -x["minutes"]):
    segs = ", ".join("%s-%s" % (bjt(times[x]), bjt(times[y])) for x, y in r["slots"])
    print("  %-9s %-15s %4dmin  %s  rot~%.1f  moon %.0f  mag %s" % (
        r["tid"], r["name"], r["minutes"], segs, r["rot"], r["moonsep"], r["mag"]))
