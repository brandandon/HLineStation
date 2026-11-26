"""Astronomy helpers: time, coordinate transforms, LSR correction, Milky Way model.

Everything is plain numpy so it is fast enough to run every frame and has no
network/IERS dependencies (works offline at a dark-sky site).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

try:
    import erfa  # pyerfa: Earth's barycentric velocity
except Exception:  # pragma: no cover
    erfa = None

C_KMS = 299792.458
HI_FREQ_MHZ = 1420.405751768
DEG = math.pi / 180.0

# Galactic rotation model (Reid et al. 2019)
R0_KPC = 8.15
V0_KMS = 236.0


# --------------------------------------------------------------------------- time
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def julian_date(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.timestamp() / 86400.0 + 2440587.5


def gmst_deg(jd: float) -> float:
    t = (jd - 2451545.0) / 36525.0
    g = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
         + 0.000387933 * t * t - t ** 3 / 38710000.0)
    return g % 360.0


def lst_deg(jd: float, lon_deg: float) -> float:
    return (gmst_deg(jd) + lon_deg) % 360.0


def fmt_hms(deg: float, hours=True) -> str:
    v = (deg / 15.0 if hours else deg) % 24.0 if hours else deg
    sign = "-" if v < 0 else ""
    v = abs(v)
    h = int(v)
    m = int((v - h) * 60)
    s = (v - h - m / 60) * 3600
    if hours:
        return f"{h:02d}h {m:02d}m {s:04.1f}s"
    return f"{sign}{h:02d}° {m:02d}′ {s:02.0f}″"


# --------------------------------------------------------------------- transforms
def radec_to_altaz(ra, dec, lst, lat):
    """All angles in degrees; arrays OK. Returns (alt, az) with az from N through E."""
    ra = np.asarray(ra, dtype=float) * DEG
    dec = np.asarray(dec, dtype=float) * DEG
    ha = lst * DEG - ra
    phi = lat * DEG
    sin_alt = np.sin(dec) * math.sin(phi) + np.cos(dec) * math.cos(phi) * np.cos(ha)
    alt = np.arcsin(np.clip(sin_alt, -1, 1))
    y = -np.cos(dec) * np.sin(ha)
    x = np.sin(dec) * math.cos(phi) - np.cos(dec) * math.sin(phi) * np.cos(ha)
    az = np.arctan2(y, x)
    return alt / DEG, (az / DEG) % 360.0


def altaz_to_radec(alt, az, lst, lat):
    alt = np.asarray(alt, dtype=float) * DEG
    az = np.asarray(az, dtype=float) * DEG
    phi = lat * DEG
    sin_dec = np.sin(alt) * math.sin(phi) + np.cos(alt) * math.cos(phi) * np.cos(az)
    dec = np.arcsin(np.clip(sin_dec, -1, 1))
    y = -np.sin(az) * np.cos(alt)
    x = np.sin(alt) * math.cos(phi) - np.cos(alt) * math.sin(phi) * np.cos(az)
    ha = np.arctan2(y, x)
    ra = (lst * DEG - ha) / DEG % 360.0
    return ra, dec / DEG


# J2000 equatorial -> galactic rotation matrix
_EQ2GAL = np.array([
    [-0.0548755604162154, -0.8734370902348850, -0.4838350155487132],
    [+0.4941094278755837, -0.4448296299600112, +0.7469822444972189],
    [-0.8676661490190047, -0.1980763734312015, +0.4559837761750669],
])


def _vec(lon, lat):
    lon = np.asarray(lon, dtype=float) * DEG
    lat = np.asarray(lat, dtype=float) * DEG
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


def _unvec(v):
    lon = np.arctan2(v[1], v[0]) / DEG % 360.0
    lat = np.arcsin(np.clip(v[2], -1, 1)) / DEG
    return lon, lat


def eq_to_gal(ra, dec):
    v = _vec(ra, dec)
    return _unvec(np.tensordot(_EQ2GAL, v, axes=1))


def gal_to_eq(l, b):
    v = _vec(l, b)
    return _unvec(np.tensordot(_EQ2GAL.T, v, axes=1))


_PREC_CACHE: dict = {}


def precession_matrix(jd: float) -> np.ndarray:
    """J2000 -> true equator & equinox of date (bias+precession+nutation)."""
    key = round(jd, 2)
    m = _PREC_CACHE.get(key)
    if m is None:
        if erfa is not None:
            m = np.array(erfa.pnm06a(jd, 0.0))
        else:
            m = np.eye(3)
        if len(_PREC_CACHE) > 50:
            _PREC_CACHE.clear()
        _PREC_CACHE[key] = m
    return m


def j2000_to_date(ra, dec, jd):
    return _unvec(np.tensordot(precession_matrix(jd), _vec(ra, dec), axes=1))


def date_to_j2000(ra, dec, jd):
    return _unvec(np.tensordot(precession_matrix(jd).T, _vec(ra, dec), axes=1))


def j2000_to_altaz(ra, dec, jd, lat, lon):
    r, d = j2000_to_date(ra, dec, jd)
    return radec_to_altaz(r, d, lst_deg(jd, lon), lat)


def altaz_to_j2000(alt, az, jd, lat, lon):
    r, d = altaz_to_radec(alt, az, lst_deg(jd, lon), lat)
    return date_to_j2000(r, d, jd)


def offset_point(lon0, lat0, rho, theta):
    """Point at angular distance rho, bearing theta (deg) from (lon0, lat0)."""
    la1, lo1 = lat0 * DEG, lon0 * DEG
    rho = np.asarray(rho) * DEG
    th = np.asarray(theta) * DEG
    la2 = np.arcsin(np.sin(la1) * np.cos(rho) + np.cos(la1) * np.sin(rho) * np.cos(th))
    lo2 = lo1 + np.arctan2(np.sin(th) * np.sin(rho) * np.cos(la1),
                           np.cos(rho) - np.sin(la1) * np.sin(la2))
    return (lo2 / DEG) % 360.0, la2 / DEG


# ------------------------------------------------------------------ Doppler / LSR
# Standard solar motion: 20 km/s toward RA 18h, Dec +30 (B1900) -> J2000
_SUN_APEX = _vec(270.9592, 30.0047) * 20.0
_AU_PER_DAY_TO_KMS = 149597870.7 / 86400.0


def earth_velocity_kms(jd: float) -> np.ndarray:
    """Earth barycentric velocity (km/s, ICRS ~ J2000 equatorial)."""
    if erfa is not None:
        _pvh, pvb = erfa.epv00(jd, 0.0)
        return np.array(pvb[1] if pvb.dtype.names is None else pvb["v"], dtype=float).ravel()[:3] * _AU_PER_DAY_TO_KMS
    # Fallback: circular orbit approximation (good to ~0.5 km/s)
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) * DEG
    eps = 23.439 * DEG
    v = 29.785
    vx, vy = v * math.sin(L), -v * math.cos(L)
    return np.array([vx, vy * math.cos(eps), vy * math.sin(eps)])


def vlsr_correction(ra: float, dec: float, jd: float, lat: float, lon: float) -> float:
    """km/s to ADD to a topocentric radial velocity to get LSR velocity."""
    n = _vec(ra, dec).ravel()
    v_earth = earth_velocity_kms(jd)
    lst = lst_deg(jd, lon) * DEG
    v_rot = 0.46512 * math.cos(lat * DEG) * np.array([-math.sin(lst), math.cos(lst), 0.0])
    return float(np.dot(v_earth + v_rot + _SUN_APEX.ravel(), n))


def freq_to_vtopo(f_mhz):
    """Radio-convention topocentric velocity (km/s) for observed frequency."""
    return C_KMS * (HI_FREQ_MHZ - np.asarray(f_mhz)) / HI_FREQ_MHZ


def vtopo_to_freq(v_kms):
    return HI_FREQ_MHZ * (1.0 - np.asarray(v_kms) / C_KMS)


# --------------------------------------------------------------- Milky Way model
def los_vlsr(l_deg, b_deg, d_kpc):
    """LSR velocity of gas at distance d along (l, b) for a flat rotation curve."""
    l = l_deg * DEG
    b = b_deg * DEG
    dp = np.asarray(d_kpc) * math.cos(b)
    R = np.sqrt(R0_KPC ** 2 + dp ** 2 - 2 * R0_KPC * dp * math.cos(l))
    R = np.maximum(R, 0.05)
    return V0_KMS * math.sin(l) * math.cos(b) * (R0_KPC / R - 1.0)


def distances_for_velocity(l_deg, v_kms):
    """Kinematic distance(s) in kpc for gas in the plane at longitude l.

    Returns (list_of_distances, ambiguous_flag). Uses a flat rotation curve.
    """
    l = l_deg * DEG
    s = math.sin(l)
    if abs(s) < 0.05:
        return [], False  # toward centre/anticentre: no velocity information
    w = v_kms / (V0_KMS * s)
    if 1.0 + w <= 0.02:
        return [], False
    R = R0_KPC / (1.0 + w)
    disc = R * R - (R0_KPC * s) ** 2
    c = R0_KPC * math.cos(l)
    if disc < 0:
        # beyond the tangent-point velocity: put it at the tangent point
        return ([c] if c > 0 else []), False
    root = math.sqrt(disc)
    ds = [d for d in (c - root, c + root) if d > 0.05]
    return ds, len(ds) == 2


def galactic_to_xy(l_deg, d_kpc, b_deg=0.0):
    """Sun-centred position -> galactocentric X (kpc, + toward l=90), Y (+ toward Sun).

    Origin is the Galactic Centre, Sun at (0, R0).
    """
    l = np.asarray(l_deg) * DEG
    dp = np.asarray(d_kpc) * math.cos(b_deg * DEG)
    x = dp * np.sin(l)
    y = R0_KPC - dp * np.cos(l)
    return x, y


# Four-arm logarithmic spiral loosely fitted to Reid et al. (2019):
# R(beta) = R_ref * exp(-beta * tan(pitch)), beta = galactocentric azimuth from the
# Sun direction, increasing in the sense of Galactic rotation.
ARMS = [
    ("Perseus", 10.05, 12.5, (180, 160, 255)),
    ("Sagittarius–Carina", 6.95, 12.5, (255, 170, 120)),
    ("Scutum–Centaurus", 4.92, 12.5, (120, 210, 255)),
    ("Norma–Outer", 3.48, 12.5, (160, 255, 170)),
]
LOCAL_ARM = ("Local (Orion) Arm", 8.45, 11.4, (255, 235, 140), (-20.0, 35.0))


def arm_polyline(r_ref, pitch_deg, beta_range=None, r_min=2.6, r_max=17.0, n=600):
    t = math.tan(pitch_deg * DEG)
    if beta_range is None:
        b_lo = math.log(r_ref / r_max) / t
        b_hi = math.log(r_ref / r_min) / t
    else:
        b_lo, b_hi = beta_range[0] * DEG, beta_range[1] * DEG
    beta = np.linspace(b_lo, b_hi, n)
    R = r_ref * np.exp(-beta * t)
    # Galactocentric: Y toward Sun, X toward l=90 direction of rotation.
    # Galactic rotation at the Sun points toward l = 90 (+X).
    x = R * np.sin(beta)
    y = R * np.cos(beta)
    return x, y


def all_arm_points():
    pts = []
    for _name, r, p, _c in ARMS:
        x, y = arm_polyline(r, p)
        pts.append(np.stack([x, y], axis=1))
    x, y = arm_polyline(LOCAL_ARM[1], LOCAL_ARM[2], LOCAL_ARM[4])
    pts.append(np.stack([x, y], axis=1))
    return np.concatenate(pts)


class HISimulator:
    """Synthesises a plausible HI profile for (l, b) from the arm model."""

    def __init__(self):
        self._arm_pts = all_arm_points()
        self._cache = {}

    def profile(self, l_deg, b_deg, v_axis):
        key = (round(l_deg * 2) / 2, round(b_deg * 2) / 2)
        if key not in self._cache:
            if len(self._cache) > 400:
                self._cache.clear()
            self._cache[key] = self._compute(*key)
        vv, tt = self._cache[key]
        return np.interp(v_axis, vv, tt, left=0.0, right=0.0)

    def _compute(self, l_deg, b_deg):
        d = np.linspace(0.02, 25.0, 900)
        x, y = galactic_to_xy(l_deg, d, b_deg)
        z = d * math.sin(b_deg * DEG)
        R = np.hypot(x, y)
        dist = np.min(np.hypot(x[:, None] - self._arm_pts[None, :, 0],
                               y[:, None] - self._arm_pts[None, :, 1]), axis=1)
        dens = 0.35 + 1.6 * np.exp(-0.5 * (dist / 0.45) ** 2)
        dens *= np.where(R < 3.0, 0.15, 1.0) * np.exp(-np.maximum(R - 13.0, 0) / 2.5)
        h = 0.12 + 0.02 * np.maximum(R - R0_KPC, 0)  # flaring disk
        dens *= np.exp(-0.5 * (z / h) ** 2)
        v = los_vlsr(l_deg, b_deg, d)
        vv = np.linspace(-320, 320, 1281)
        prof = np.zeros_like(vv)
        dd = d[1] - d[0]
        sig = 7.0
        for vi, w in zip(v, dens * dd):
            if w > 1e-4:
                prof += w * np.exp(-0.5 * ((vv - vi) / sig) ** 2)
        # local gas always present (even at high |b|) at ~0 km/s
        prof += 0.25 * np.exp(-0.5 * (vv / 6.0) ** 2) / max(abs(math.sin(b_deg * DEG)), 0.15)
        return vv, prof
