"""Verify the final night plan slot by slot.

BJT 19:00 Oct-19 .. 05:00 Oct-20 -> UTC 11:00 Oct-19 .. 21:00 Oct-19.
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
AZ_LO, AZ_HI, ALT_MIN, ALT_MAX = 330.0, 110.0, 20.0, 70.0

# (start, end, id, name, ra, dec, filter)
PLAN = [
    ("19:15", "20:45", "M31", "Andromeda Galaxy", 10.685, 41.269, "IRCUT"),
    ("20:50", "22:05", "IC1805", "Heart Nebula", 38.20, 61.50, "LP"),
    ("22:10", "23:25", "NGC1499", "California Nebula", 60.00, 36.40, "LP"),
    ("23:30", "00:45", "M45", "Pleiades", 56.75, 24.117, "IRCUT"),
    ("03:05", "04:20", "M81", "Bode's + Cigar", 148.89, 69.07, "IRCUT"),
    ("04:20", "05:00", "NGC2403", "Galaxy", 114.20, 65.60, "IRCUT"),
]


def bjt_to_utc(hhmm):
    h, m = map(int, hhmm.split(":"))
    # BJT 12:00-23:59 -> Oct 19 ; BJT 00:00-11:59 -> Oct 20. UTC = BJT - 8h,
    # so the whole observing night maps onto UTC 11:00-21:00 Oct 19.
    day = 19 if h >= 12 else 20
    return datetime(2026, 10, day, tzinfo=timezone.utc) + timedelta(hours=h - 8, minutes=m)


def bjt_str(t):
    return (t.to_datetime() + timedelta(hours=8)).strftime("%H:%M")


def in_window(az_deg):
    az = float(np.mod(az_deg, 360.0))
    return (az >= AZ_LO) or (az <= AZ_HI)


print("Window az %.0f->%.0f, alt %.0f-%.0f" % (AZ_LO, AZ_HI, ALT_MIN, ALT_MAX))
hdr = "%-6s %-6s %-8s %-18s %5s %5s %6s %6s %6s %6s"
print(hdr % ("from", "to", "ID", "Name", "alt0", "alt1", "az0", "az1", "rot", "moonS"))
print("-" * 92)

ok_all = True
for a, b, tid, name, ra, dec, filt in PLAN:
    t0, t1 = Time(bjt_to_utc(a)), Time(bjt_to_utc(b))
    npts = max(2, int((t1 - t0).to_value(u.s) / 300) + 1)
    ts = t0 + np.linspace(0, (t1 - t0).to_value(u.s), npts) * u.s
    fr = AltAz(obstime=ts, location=loc)
    aa = SkyCoord(ra * u.deg, dec * u.deg).transform_to(fr)
    alt, az = aa.alt.deg, aa.az.deg
    rot = np.abs(W * np.cos(LAT_R) * np.cos(np.radians(az)) / np.cos(np.radians(alt)))
    moon = get_body("moon", ts, loc).transform_to(fr)
    sep = aa.separation(moon).deg
    sun_alt = get_sun(ts).transform_to(fr).alt.deg
    bad = (alt < ALT_MIN) | (alt > ALT_MAX) | np.array([not in_window(x) for x in az])
    status = ""
    if bad.any():
        i = int(np.where(bad)[0][0])
        status = "  <-- OUT at %s (alt %.1f az %.1f)" % (bjt_str(ts[i]), alt[i], az[i])
        ok_all = False
    print(hdr % (a, b, tid, name, "%.1f" % alt[0], "%.1f" % alt[-1],
                 "%.0f" % (az[0] % 360), "%.0f" % (az[-1] % 360),
                 "%.1f" % np.median(rot), "%.0f" % sep.min()) + status)
    if sun_alt.max() > -15:
        print("      NOTE: not fully dark until %s" % bjt_str(ts[np.argmax(sun_alt < -15)]))

print("\nAll slots inside window:", ok_all)

print("\n=== 10-minute trace ===")
for a, b, tid, name, ra, dec, filt in PLAN:
    print("\n%s %s  %s-%s  filter=%s" % (tid, name, a, b, filt))
    t0, t1 = Time(bjt_to_utc(a)), Time(bjt_to_utc(b))
    ts = t0 + np.linspace(0, (t1 - t0).to_value(u.s), 8) * u.s
    fr = AltAz(obstime=ts, location=loc)
    aa = SkyCoord(ra * u.deg, dec * u.deg).transform_to(fr)
    for i in range(len(ts)):
        r = abs(W * np.cos(LAT_R) * np.cos(np.radians(aa.az.deg[i])) / np.cos(np.radians(aa.alt.deg[i])))
        print("   %s  alt=%5.1f az=%6.1f (norm %5.1f) rot=%5.1f" % (
            bjt_str(ts[i]), aa.alt.deg[i], aa.az.deg[i], aa.az.deg[i] % 360, r))
