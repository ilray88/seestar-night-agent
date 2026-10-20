"""Detailed per-slot alt/az + field rotation for the NE-window plan."""
from datetime import datetime, timedelta, timezone

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, get_sun
from astropy.time import Time
import astropy.units as u

LAT, LON, ELEV = 22.7261, 114.046, 40
loc = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ELEV * u.m)
LAT_R = np.radians(LAT)

# Plan slots (Beijing time)
SLOTS = [
    ("19:20", "20:20", "M31", "Andromeda", 10.685, 41.269),
    ("20:20", "21:20", "IC1805", "Heart Nebula", 38.20, 61.50),
    ("21:20", "22:20", "NGC1499", "California Nebula", 60.00, 36.40),
    ("22:20", "23:10", "IC1848", "Soul Nebula", 40.90, 60.40),
    ("23:10", "00:00", "M45", "Pleiades", 56.75, 24.117),
    ("00:00", "01:00", "M1", "Crab Nebula", 83.63, 22.01),
    ("01:00", "02:00", "M35", "Gemini Cluster", 92.27, 24.34),
    ("02:00", "03:00", "NGC2392", "Eskimo Nebula", 112.29, 20.91),
    ("03:00", "04:00", "M81", "Bode's Galaxy", 148.89, 69.07),
]


def to_time(hhmm):
    h, m = map(int, hhmm.split(":"))
    base = datetime(2026, 10, 19, tzinfo=timezone.utc)
    if h < 12:  # after midnight -> next UTC day? BJT >= 00:00
        pass
    return base + timedelta(hours=h - 8, minutes=m)  # BJT -> UTC


print("%-7s %-7s %-9s %-18s %6s %6s %6s %8s %6s" % (
    "from", "to", "ID", "Name", "alt0", "alt1", "az", "rot/h", "moonSep"))
print("-" * 90)

for a, b, tid, name, ra, dec in SLOTS:
    t0 = Time(to_time(a)); t1 = Time(to_time(b))
    ts = t0 + np.linspace(0, (t1 - t0).to_value(u.s), 12) * u.s
    fr = AltAz(obstime=ts, location=loc)
    c = SkyCoord(ra * u.deg, dec * u.deg)
    aa = c.transform_to(fr)
    alt, az = aa.alt.deg, aa.az.deg
    moon = get_body("moon", ts, loc).transform_to(fr)
    sep = aa.separation(moon).deg

    # field rotation rate: dq/dt = w * cos(lat) * cos(az) / cos(alt), w in deg/hr
    w = 15.041
    rot = w * np.cos(np.radians(LAT)) * np.cos(np.radians(az)) / np.cos(np.radians(alt))
    print("%-7s %-7s %-9s %-18s %6.1f %6.1f %6.1f %8.1f %6.1f" % (
        a, b, tid, name, alt[0], alt[-1], az.mean(), np.abs(rot).mean(), sep.min()))

print()
print("=== alt/az at 30-min steps for prime targets ===")
for tid, name, ra, dec in [("M31", "Andromeda", 10.685, 41.269),
                           ("IC1805", "Heart", 38.20, 61.50),
                           ("NGC1499", "California", 60.00, 36.40),
                           ("IC1848", "Soul", 40.90, 60.40),
                           ("M45", "Pleiades", 56.75, 24.117)]:
    print("\n" + tid + " " + name)
    c = SkyCoord(ra * u.deg, dec * u.deg)
    for hh, mm in [(19, 0), (19, 30), (20, 0), (20, 30), (21, 0), (21, 30),
                   (22, 0), (22, 30), (23, 0), (23, 30), (0, 0)]:
        t = Time(to_time("%02d:%02d" % (hh, mm)))
        fr = AltAz(obstime=t, location=loc)
        p = c.transform_to(fr)
        print("  %02d:%02d  alt=%6.1f  az=%6.1f" % (hh, mm, p.alt.deg, p.az.deg))
