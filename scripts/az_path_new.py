"""Validate the NEW full-night plan (with gap filled) and compute the cable budget."""
from datetime import datetime, timedelta, timezone

from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time
import astropy.units as u

BJT = timezone(timedelta(hours=8))
LAT, LON = 22.7261, 114.046
loc = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg)
WIN_MIN, WIN_MAX = 330.0, 110.0

# name, ra_h, dec, start HH:MM, end HH:MM (end may be >24 for next day)
SLOTS = [
    ("M31",     0.7123,  41.2687, "19:15", "20:45"),
    ("IC1805",  2.5467,  61.4667, "20:50", "22:05"),
    ("NGC1499", 4.0556,  36.6333, "22:10", "23:25"),
    ("M45",     3.7833,  24.1167, "23:30", "24:45"),
    ("IC405",   5.2700,  34.2670, "24:45", "26:20"),   # NEW gap fill (Flame)
    ("IC443",   6.2870,  22.4670, "26:20", "27:35"),   # NEW gap fill (Jellyfish)
    ("M81",     9.9259,  69.0650, "27:35", "28:55"),
    ("NGC2403", 7.6143,  65.6000, "28:55", "29:15"),
]

DAY = datetime(2026, 10, 19, 0, 0, tzinfo=BJT)


def t_of(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return DAY + timedelta(days=h // 24, hours=h % 24, minutes=m)


def aa(ra, dec, t):
    c = SkyCoord(ra=ra * 15 * u.deg, dec=dec * u.deg, frame="icrs")
    return c.transform_to(AltAz(obstime=Time(t), location=loc))


def in_win(az):
    return az >= WIN_MIN or az <= WIN_MAX


print("=" * 104)
print("NEW full-night plan (gap 00:45-03:35 filled with IC405 + IC443)")
print("=" * 104)
print(f"{'target':<9}{'win':<14}{'min':>5}  {'az  start->end':>22}  {'alt start->end':>18}  {'dAz':>7} {'in win':>7}")
print("-" * 104)

prev_az = None
cum = 0.0
total = 0.0
ok_all = True
for name, ra, dec, s, e in SLOTS:
    ts, te = t_of(s), t_of(e)
    a0, a1 = aa(ra, dec, ts), aa(ra, dec, te)
    mins = (te - ts).total_seconds() / 60
    total += mins
    d = a1.az.deg - a0.az.deg
    if d > 180:
        d -= 360
    if d < -180:
        d += 360
    cum += abs(d)
    win = in_win(a0.az.deg) and in_win(a1.az.deg)
    if not win:
        ok_all = False
    print(f"{name:<9}{ts:%H:%M}-{te:%H:%M}  {mins:>5.0f}  "
          f"{a0.az.deg:8.1f} ->{a1.az.deg:8.1f}  "
          f"{a0.alt.deg:7.1f} ->{a1.alt.deg:7.1f}  {d:>7.1f} {'OK' if win else 'OUT':>7}")

print("-" * 104)
print(f"total imaging {total:.0f} min = {total/60:.1f} h")
print(f"cumulative azimuth travel (|sum of deltas|) = {cum:.1f} deg   [cable limit 200 deg]")
print(f"all slots in window: {ok_all}")

# finer azimuth sweep to catch intra-slot swings
print()
print("Fine azimuth sweep (10-min steps) to measure true cable travel")
fine = 0.0
last = None
for name, ra, dec, s, e in SLOTS:
    ts, te = t_of(s), t_of(e)
    t = ts
    while t <= te:
        az = aa(ra, dec, t).az.deg
        if last is not None:
            d = az - last
            if d > 180:
                d -= 360
            if d < -180:
                d += 360
            fine += abs(d)
        last = az
        t += timedelta(minutes=10)
print(f"  fine cumulative travel = {fine:.1f} deg   [limit 200 deg]  -> {'SAFE' if fine < 200 else 'RISK'}")
