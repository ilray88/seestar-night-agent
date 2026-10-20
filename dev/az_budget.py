from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
from datetime import datetime, timedelta, timezone

loc = EarthLocation(lat=22.7261*u.deg, lon=114.046*u.deg, height=40*u.m)

# BJT -> UTC
def bjt(h, m=0):
    base = datetime(2026,10,19, tzinfo=timezone.utc) + timedelta(hours=8)
    return base.replace(hour=0,minute=0) + timedelta(hours=h, minutes=m)

plan = [
    ("M31",       19,15, 20,45, 54, 50),
    ("IC1805",    20,50, 22, 5, 30, 26),
    ("NGC1499",   22,10, 23,25, 60, 60),
    ("M45",       23,30, 24,45, 79, 81),
    ("M81",        3, 5,  4,20, 23, 22),
    ("NGC2403",    4,20,  5, 0, 15, 10),
]
coords = {  # J2000 deg
 "M31":     (10.6847, 41.2687),
 "IC1805":  (38.2000, 61.4667),
 "NGC1499": (60.8333, 36.6333),
 "M45":     (56.7500, 24.1167),
 "M81":     (148.8882, 69.0653),
 "NGC2403": (114.2167, 65.6000),
}

print(f"{'target':10} {'time(BJT)':>16}  {'az':>7} {'alt':>7}")
prev_az = None
cum = 0.0
for name, h1,m1,h2,m2, az_s, az_e in plan:
    c = SkyCoord(ra=coords[name][0]*u.deg, dec=coords[name][1]*u.deg, frame="icrs")
    for hh,mm,tag in [(h1,m1,"start"),(h2,m2,"end")]:
        t = bjt(hh % 24, mm)
        if hh >= 24: t += timedelta(days=1)
        elif hh < 12: t += timedelta(days=1)
        aa = c.transform_to(AltAz(obstime=Time(t), location=loc))
        az = aa.az.deg
        print(f"{name:10} {t.strftime('%m-%d %H:%M')} {tag:>5}  {az:7.1f} {aa.alt.deg:7.1f}")
        if prev_az is not None:
            d = az - prev_az
            if d > 180: d -= 360
            if d < -180: d += 360
            cum += d
            print(f"{'':10} {'':16} {'move':>5}  dAz={d:+7.1f}  cum={cum:+7.1f}")
        prev_az = az

print(f"\nTOTAL cumulative azimuth travel: {cum:+.1f} deg")
print(f"Azimuth span covered: min..max")
