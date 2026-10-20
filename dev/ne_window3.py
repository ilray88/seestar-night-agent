"""Alt/az visibility in a NE-facing window, with honest numbers.

ASCII-only output.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, get_sun
from astropy.time import Time
import astropy.units as u

LAT, LON, ELEV = 22.7261, 114.046, 40
loc = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ELEV * u.m)

AZ_MIN, AZ_MAX = 0.0, 108.0
ALT_MIN, ALT_MAX = 20.0, 70.0

TARGETS = [
    ("M31", "Andromeda", 10.685, 41.269, "galaxy"),
    ("M33", "Triangulum", 23.462, 30.660, "galaxy"),
    ("NGC891", "Edge-on Galaxy", 35.64, 42.35, "galaxy"),
    ("NGC2403", "Galaxy", 114.20, 65.60, "galaxy"),
    ("M81", "Bode's Galaxy", 148.89, 69.07, "galaxy"),
    ("M82", "Cigar Galaxy", 148.97, 69.68, "galaxy"),
    ("NGC281", "Pacman Nebula", 13.15, 56.60, "emission"),
    ("NGC7380", "Wizard Nebula", 341.75, 58.117, "emission"),
    ("NGC7635", "Bubble Nebula", 350.20, 61.20, "emission"),
    ("IC1805", "Heart Nebula", 38.20, 61.50, "emission"),
    ("IC1848", "Soul Nebula", 40.90, 60.40, "emission"),
    ("NGC1499", "California Neb", 60.00, 36.40, "emission"),
    ("IC405", "Flaming Star", 79.05, 34.30, "emission"),
    ("IC410", "Tadpoles", 79.10, 66.60, "emission"),
    ("IC1396", "Elephant Trunk", 324.70, 57.50, "emission"),
    ("NGC7023", "Iris Nebula", 315.00, 68.20, "reflection"),
    ("NGC7000", "North America", 314.70, 44.30, "emission"),
    ("IC5070", "Pelican Nebula", 313.00, 44.40, "emission"),
    ("NGC6960", "Western Veil", 311.40, 30.70, "snr"),
    ("NGC6992", "Eastern Veil", 314.30, 31.70, "snr"),
    ("NGC6888", "Crescent Nebula", 303.00, 38.20, "emission"),
    ("M76", "Little Dumbbell", 25.58, 51.60, "planetary"),
    ("M27", "Dumbbell Nebula", 299.90, 22.72, "planetary"),
    ("M57", "Ring Nebula", 283.40, 33.03, "planetary"),
    ("M45", "Pleiades", 56.75, 24.117, "cluster"),
    ("NGC869", "Double Cluster", 34.75, 57.10, "cluster"),
    ("NGC457", "Owl Cluster", 19.90, 58.20, "cluster"),
    ("NGC663", "Cassiopeia Cl", 26.00, 61.20, "cluster"),
    ("M103", "Open Cluster", 23.30, 60.70, "cluster"),
    ("NGC457b", "Stock 2", 35.60, 59.60, "cluster"),
    ("M42", "Orion Nebula", 83.822, -5.391, "emission"),
    ("M35", "Gemini Cluster", 92.27, 24.34, "cluster"),
    ("M1", "Crab Nebula", 83.63, 22.01, "snr"),
    ("NGC2392", "Eskimo Neb", 112.29, 20.91, "planetary"),
]

t0 = Time(datetime(2026, 10, 19, 11, 0, tzinfo=timezone.utc))   # 19:00 BJT
t1 = Time(datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc))   # 05:00 BJT
step_s = 600
n = int((t1 - t0).to_value(u.s) / step_s) + 1
times = t0 + np.arange(n) * step_s * u.s
frame = AltAz(obstime=times, location=loc)

sun = get_sun(times).transform_to(frame)
moon = get_body("moon", times, loc).transform_to(frame)


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


rows = []
for tid, name, ra, dec, kind in TARGETS:
    c = SkyCoord(ra * u.deg, dec * u.deg)
    aa = c.transform_to(frame)
    alt, az = aa.alt.deg, aa.az.deg
    dark = sun.alt.deg < -15.0
    vis = (alt >= ALT_MIN) & (alt <= ALT_MAX) & (az >= AZ_MIN) & (az <= AZ_MAX) & dark
    rr = runs(vis)
    if not rr:
        rows.append(dict(tid=tid, name=name, kind=kind, minutes=0))
        continue
    a, b = max(rr, key=lambda r: r[1] - r[0])
    minutes = (b - a) * 10
    sep = aa[a:b + 1].separation(moon[a:b + 1]).deg
    rows.append(dict(
        tid=tid, name=name, kind=kind, minutes=minutes,
        start=bjt(times[a]), end=bjt(times[b]),
        max_alt=round(float(alt[a:b + 1].max()), 1),
        az_start=round(float(az[a]), 1),
        az_end=round(float(az[b]), 1),
        moon_sep=round(float(sep.min()), 1),
        moon_alt=round(float(moon[a:b + 1].alt.deg.max()), 1),
    ))

rows.sort(key=lambda r: -r["minutes"])
print("WINDOW az %.0f-%.0f, alt %.0f-%.0f, sun<-15.  Night 19:00-05:00 BJT" % (AZ_MIN, AZ_MAX, ALT_MIN, ALT_MAX))
fmt = "%-8s %-16s %-9s %5s %5s %5s %6s %6s %6s %s"
print(fmt % ("ID", "Name", "kind", "from", "to", "min", "maxAlt", "az0", "az1", "moonSep"))
print("-" * 90)
for r in rows:
    if r["minutes"] == 0:
        print(fmt % (r["tid"], r["name"], r["kind"], "-", "-", 0, "-", "-", "-", "NO"))
    else:
        print(fmt % (r["tid"], r["name"], r["kind"], r["start"], r["end"],
                     r["minutes"], r["max_alt"], r["az_start"], r["az_end"],
                     "%.1f" % r["moon_sep"]))

print("\nMOON: alt/az/illum-ish")
for i in range(0, n, 3):
    print("  %s  alt=%6.1f az=%6.1f" % (bjt(times[i]), moon.alt.deg[i], moon.az.deg[i]))

