from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
from datetime import datetime, timedelta, timezone

loc = EarthLocation(lat=22.7261*u.deg, lon=114.046*u.deg, height=40*u.m)

# CORRECT: BJT = UTC+8. Plan night starts 2026-10-19 evening BJT.
# 'h' uses 24+ convention for after-midnight (e.g. 24:45 = 00:45 next day)
BASE_UTC = datetime(2026,10,19,tzinfo=timezone.utc)
def utc_of(h, m=0):
    return BASE_UTC + timedelta(hours=h-8, minutes=m)

coords = {
 "M31":     (10.6847, 41.2687),
 "IC1805":  (38.2000, 61.4667),
 "NGC1499": (60.8333, 36.6333),
 "M45":     (56.7500, 24.1167),
 "M81":     (148.8882, 69.0653),
 "NGC2403": (114.2167, 65.6000),
}
plan = [
    ("M31",       19,15, 20,45),
    ("IC1805",    20,50, 22, 5),
    ("NGC1499",   22,10, 23,25),
    ("M45",       23,30, 24,45),
    ("M81",       27, 5, 28,20),
    ("NGC2403",   28,20, 29, 0),
]

def fmt_cum(a):
    return f"{a:+8.1f}"

print(f"{'target':9} {'BJT':16} {'UTC':6} {'az':>7} {'alt':>7}   dAz      cum")
prev = None; cum = 0.0; azs=[]
for name,h1,m1,h2,m2 in plan:
    c = SkyCoord(ra=coords[name][0]*u.deg, dec=coords[name][1]*u.deg, frame="icrs")
    for h,m,tag in [(h1,m1,"start"),(h2,m2,"end")]:
        t = utc_of(h,m)
        aa = c.transform_to(AltAz(obstime=Time(t), location=loc))
        az = aa.az.deg; alt = aa.alt.deg
        azs.append(az)
        line = f"{name:9} {t.astimezone(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')} {tag:>5} {az:7.1f} {alt:7.1f}"
        if prev is not None:
            d = az - prev
            if d > 180: d -= 360
            if d < -180: d += 360
            cum += d
            line += f"  {d:+7.1f} {fmt_cum(cum)}"
        print(line)
        prev = az

print(f"\nCumulative azimuth travel: {cum:+.1f} deg")
print(f"Azimuth range: {min(azs):.1f} .. {max(azs):.1f}  (span {max(azs)-min(azs):.1f} deg)")
