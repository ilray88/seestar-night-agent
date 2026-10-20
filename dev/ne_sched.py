"""Night schedule optimizer for a wide NE window (az 0-108).

Computes, for each candidate, the dark/above-floor/in-window intervals and
the alt-az field-rotation rate, then proposes slots.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, get_sun
from astropy.time import Time
import astropy.units as u

LAT, LON, ELEV = 22.7261, 114.046, 40
loc = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ELEV * u.m)
LAT_R = np.radians(LAT)
AZ_MIN, AZ_MAX = 0.0, 108.0
ALT_MIN, ALT_MAX = 20.0, 70.0
W = 15.041  # deg/hr sidereal

CANDS = [
    ("M31", "Andromeda", 10.685, 41.269, "galaxy", 178),
    ("M33", "Triangulum", 23.462, 30.660, "galaxy", 73),
    ("NGC891", "Edge-on Gal", 35.64, 42.35, "galaxy", 14),
    ("NGC2403", "Galaxy", 114.20, 65.60, "galaxy", 21),
    ("M81", "Bode's", 148.89, 69.07, "galaxy", 27),
    ("M82", "Cigar", 148.97, 69.68, "galaxy", 11),
    ("IC1805", "Heart Neb", 38.20, 61.50, "emission", 60),
    ("IC1848", "Soul Neb", 40.90, 60.40, "emission", 30),
    ("NGC1499", "California", 60.00, 36.40, "emission", 145),
    ("IC405", "Flaming Star", 79.05, 34.30, "emission", 30),
    ("IC410", "Tadpoles", 79.10, 66.60, "emission", 25),
    ("NGC281", "Pacman", 13.15, 56.60, "emission", 35),
    ("NGC7635", "Bubble", 350.20, 61.20, "emission", 15),
    ("NGC7380", "Wizard", 341.75, 58.117, "emission", 25),
    ("IC1396", "Elephant Trunk", 324.70, 57.50, "emission", 170),
    ("NGC7023", "Iris", 315.00, 68.20, "reflection", 10),
    ("NGC7000", "N.America", 314.70, 44.30, "emission", 120),
    ("IC5070", "Pelican", 313.00, 44.40, "emission", 60),
    ("M45", "Pleiades", 56.75, 24.117, "cluster", 110),
    ("M35", "Gemini Cl", 92.27, 24.34, "cluster", 28),
    ("NGC869", "Double Cl", 34.75, 57.10, "cluster", 60),
    ("NGC457", "Owl Cl", 19.90, 58.20, "cluster", 20),
    ("NGC663", "Cassiopeia Cl", 26.00, 61.20, "cluster", 16),
    ("M103", "Open Cl", 23.30, 60.70, "cluster", 6),
    ("M76", "Little Dumbbell", 25.58, 51.60, "planetary", 3),
    ("M1", "Crab", 83.63, 22.01, "snr", 6),
    ("NGC2392", "Eskimo", 112.29, 20.91, "planetary", 1.2),
]

t0 = Time(datetime(2026, 10, 19, 11, 0, tzinfo=timezone.utc))
t1 = Time(datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc))
step_s = 300
n = int((t1 - t0).to_value(u.s) / step_s) + 1
times = t0 + np.arange(n) * step_s * u.s
frame = AltAz(obstime=times, location=loc)
sun = get_sun(times).transform_to(frame)
dark = sun.alt.deg < -15.0


def bjt(t):
    return (t.to_datetime() + timedelta(hours=8)).strftime("%H:%M")


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


print("WINDOW az %.0f-%.0f  alt %.0f-%.0f  dark(sun<-15)" % (AZ_MIN, AZ_MAX, ALT_MIN, ALT_MAX))
print("%-8s %-14s %-10s %5s %5s %6s %6s %7s  %s" % (
    "ID", "Name", "kind", "from", "to", "min", "maxAlt", "rot/h", "azRange"))
print("-" * 96)
rows = []
for tid, name, ra, dec, kind, size in CANDS:
    c = SkyCoord(ra * u.deg, dec * u.deg)
    aa = c.transform_to(frame)
    alt, az = aa.alt.deg, aa.az.deg
    vis = (alt >= ALT_MIN) & (alt <= ALT_MAX) & (az >= AZ_MIN) & (az <= AZ_MAX) & dark
    rr = runs(vis)
    if not rr:
        print("%-8s %-14s %-10s %5s %5s %6d %6s %7s  NO" % (tid, name, kind, "-", "-", 0, "-", "-"))
        continue
    a, b = max(rr, key=lambda r: r[1] - r[0])
    rot = W * np.cos(LAT_R) * np.cos(np.radians(az[a:b + 1])) / np.cos(np.radians(alt[a:b + 1]))
    rot = np.abs(rot)
    rows.append(dict(tid=tid, name=name, kind=kind, size=size,
                     a=a, b=b, minutes=(b - a) * 5,
                     maxalt=float(alt[a:b + 1].max()),
                     rot_med=float(np.median(rot)), rot_max=float(rot.max()),
                     az0=float(az[a]), az1=float(az[b]),
                     alt0=float(alt[a]), alt1=float(alt[b])))
    print("%-8s %-14s %-10s %5s %5s %6d %6.1f %7.1f  %.1f-%.1f" % (
        tid, name, kind, bjt(times[a]), bjt(times[b]), (b - a) * 5,
        float(alt[a:b + 1].max()), float(np.median(rot)), float(az[a]), float(az[b])))

print("\n=== BEST TARGETS BY KIND (in-window minutes) ===")
by = {}
for r in rows:
    by.setdefault(r["kind"], []).append(r)
for k, v in by.items():
    v.sort(key=lambda x: -x["minutes"])
    print("\n%s:" % k)
    for r in v[:4]:
        print("  %-8s %-14s %4d min  %s-%s  rot %.1f-%.1f  alt %.0f->%.0f  az %.0f->%.0f" % (
            r["tid"], r["name"], r["minutes"], bjt(times[r["a"]]), bjt(times[r["b"]]),
            r["rot_med"], r["rot_max"], r["alt0"], r["alt1"], r["az0"], r["az1"]))
