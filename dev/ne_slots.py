"""Validate each planned slot: alt/az at start & end, field rotation, moon sep."""
from datetime import datetime, timedelta, timezone

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.time import Time
import astropy.units as u

LAT, LON, ELEV = 22.7261, 114.046, 40
loc = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ELEV * u.m)
LAT_R = np.radians(LAT)
W = 15.041

PLAN = [
    ("19:10", "20:40", "M31", "Andromeda Galaxy", 10.685, 41.269, 178),
    ("20:45", "22:00", "IC1805", "Heart Nebula", 38.20, 61.50, 60),
    ("22:00", "23:15", "NGC1499", "California Nebula", 60.00, 36.40, 145),
    ("23:15", "00:20", "M45", "Pleiades", 56.75, 24.117, 110),
    ("00:20", "01:10", "M1", "Crab Nebula", 83.63, 22.01, 6),
    ("03:00", "04:30", "M81", "Bode's + Cigar", 148.89, 69.07, 27),
    ("04:30", "05:00", "NGC2403", "Galaxy", 114.20, 65.60, 21),
]


def ut(hhmm):
    """BJT -> UTC. Hours < 12 belong to the next calendar day (after midnight)."""
    h, m = map(int, hhmm.split(":"))
    day = 19 if h >= 12 else 20
    return datetime(2026, 10, day, tzinfo=timezone.utc) + timedelta(hours=h - 8, minutes=m)


def bjt(t):
    return (t.to_datetime() + timedelta(hours=8)).strftime("%H:%M")


print("%-6s %-6s %-8s %-16s %5s %5s %5s %5s %6s %6s %6s" % (
    "from", "to", "ID", "Name", "alt0", "alt1", "az0", "az1", "rot0", "rot1", "moonS"))
print("-" * 96)

for a, b, tid, name, ra, dec, size in PLAN:
    t0, t1 = Time(ut(a)), Time(ut(b))
    ts = t0 + np.linspace(0, (t1 - t0).to_value(u.s), 25) * u.s
    fr = AltAz(obstime=ts, location=loc)
    c = SkyCoord(ra * u.deg, dec * u.deg)
    aa = c.transform_to(fr)
    alt, az = aa.alt.deg, aa.az.deg
    rot = np.abs(W * np.cos(LAT_R) * np.cos(np.radians(az)) / np.cos(np.radians(alt)))
    moon = get_body("moon", ts, loc).transform_to(fr)
    sep = aa.separation(moon).deg
    print("%-6s %-6s %-8s %-16s %5.1f %5.1f %5.1f %5.1f %6.1f %6.1f %6.1f" % (
        a, b, tid, name, alt[0], alt[-1], az[0], az[-1], rot[0], rot[-1], sep.min()))
    # warn if out of window at any point
    bad = (alt < 20) | (alt > 70) | (az < 0) | (az > 108)
    if bad.any():
        idx = np.where(bad)[0]
        print("      WARNING out-of-window at %s: alt=%.1f az=%.1f" % (
            bjt(ts[idx[0]]), alt[idx[0]], az[idx[0]]))

print("\n=== 15-min trace for each slot ===")
for a, b, tid, name, ra, dec, size in PLAN:
    print("\n%s %s  (%s-%s)" % (tid, name, a, b))
    c = SkyCoord(ra * u.deg, dec * u.deg)
    t0, t1 = Time(ut(a)), Time(ut(b))
    npts = 9
    ts = t0 + np.linspace(0, (t1 - t0).to_value(u.s), npts) * u.s
    fr = AltAz(obstime=ts, location=loc)
    aa = c.transform_to(fr)
    for i in range(npts):
        r = abs(W * np.cos(LAT_R) * np.cos(np.radians(aa.az.deg[i])) / np.cos(np.radians(aa.alt.deg[i])))
        print("  %s  alt=%5.1f  az=%6.1f  rot=%5.1f deg/h" % (
            bjt(ts[i]), aa.alt.deg[i], aa.az.deg[i], r))
