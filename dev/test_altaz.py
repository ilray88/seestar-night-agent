import json, urllib.request
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
from datetime import datetime, timezone

BASE="http://127.0.0.1:5555"
def alp(path, extra=""):
    sep = "&" if "?" in path else "?"
    url = f"{BASE}/api/v1/telescope/1/{path}{sep}{extra}{'&' if extra else ''}ClientID=1&ClientTransactionID=9901"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

ra = alp("rightascension")["Value"]      # hours
dec = alp("declination")["Value"]        # deg
print(f"RA={ra} h  Dec={dec} deg")

loc = EarthLocation(lat=22.7261*u.deg, lon=114.046*u.deg, height=40*u.m)
t = Time(datetime.now(timezone.utc))

# treat firmware RA/Dec as JNow (FK5 equinox of date)
c_jnow = SkyCoord(ra=ra*15*u.deg, dec=dec*u.deg, frame="fk5", equinox=t)
aa = c_jnow.transform_to(AltAz(obstime=t, location=loc))
print(f"JNOW-> az={aa.az.deg:.2f} alt={aa.alt.deg:.2f}")

# also try ICRS interpretation for comparison
c_icrs = SkyCoord(ra=ra*15*u.deg, dec=dec*u.deg, frame="icrs")
aa2 = c_icrs.transform_to(AltAz(obstime=t, location=loc))
print(f"ICRS-> az={aa2.az.deg:.2f} alt={aa2.alt.deg:.2f}")

# compass reading for cross-check
print("NOTE compass direction (device) was 341.99 deg")
