"""Field-level NMEA 0183 sentence builders.

These functions take plain values (degrees, knots, datetimes) and return a
finished sentence with checksum and <CR><LF>. They know nothing about
networking and nothing about equipment state; see models.py for the latter.

Sentence field layouts follow common NMEA 0183 practice (v2.3-style mode
fields on GLL/RMC/VTG). They were written from general knowledge of the
format, NOT from the IEC 61162-1 text, which is not part of this repository.
Tests check self-consistency and the checksum of known example sentences.
Check against IEC 61162-1 before claiming conformance.
"""

from datetime import datetime, timezone

from .checksum import build_sentence

KN_TO_KMH = 1.852


def _ddmm(value: float, deg_digits: int) -> str:
    whole = int(value)
    minutes = round((value - whole) * 60, 3)
    if minutes >= 60:  # rounding carried into the next degree
        whole += 1
        minutes = 0.0
    return f"{whole:0{deg_digits}d}{minutes:06.3f}"


def format_lat(degrees: float) -> tuple:
    """Decimal degrees -> ('ddmm.mmm', 'N'|'S')."""
    return _ddmm(abs(degrees), 2), "N" if degrees >= 0 else "S"


def format_lon(degrees: float) -> tuple:
    """Decimal degrees -> ('dddmm.mmm', 'E'|'W')."""
    return _ddmm(abs(degrees), 3), "E" if degrees >= 0 else "W"


def utc_time(when: datetime, decimals: int = 0) -> str:
    """hhmmss or hhmmss.ss (UTC)."""
    when = when.astimezone(timezone.utc)
    text = when.strftime("%H%M%S")
    if decimals:
        text += "." + f"{when.microsecond:06d}"[:decimals]
    return text


def _now(when):
    return when or datetime.now(timezone.utc)


def _ew(value: float) -> tuple:
    """(magnitude string, 'E'|'W') for an east-positive angle."""
    return f"{abs(value):.1f}", "E" if value >= 0 else "W"


def gll(lat, lon, when=None, talker="GP", status="A", decimals=0, mode=None):
    """GLL - geographic position, latitude/longitude and time."""
    when = _now(when)
    lat_s, ns = format_lat(lat)
    lon_s, ew = format_lon(lon)
    fields = [lat_s, ns, lon_s, ew, utc_time(when, decimals), status]
    if mode is not None:
        fields.append(mode)
    return build_sentence(talker, "GLL", fields)


def gga(lat, lon, when=None, talker="GP", quality=1, satellites=8, hdop=0.9,
        altitude_m=0.0, geoid_sep_m=0.0, decimals=0):
    """GGA - GPS fix data."""
    when = _now(when)
    lat_s, ns = format_lat(lat)
    lon_s, ew = format_lon(lon)
    return build_sentence(talker, "GGA", [
        utc_time(when, decimals), lat_s, ns, lon_s, ew, quality, f"{satellites:02d}",
        f"{hdop:.1f}", f"{altitude_m:.1f}", "M", f"{geoid_sep_m:.1f}", "M", None, None,
    ])


def rmc(lat, lon, when, sog_kn, cog_true, variation_deg, talker="GP",
        status="A", mode="A", decimals=0):
    """RMC - recommended minimum navigation data."""
    when = when.astimezone(timezone.utc)
    lat_s, ns = format_lat(lat)
    lon_s, ew = format_lon(lon)
    var_s, var_ew = _ew(variation_deg)
    return build_sentence(talker, "RMC", [
        utc_time(when, decimals), status, lat_s, ns, lon_s, ew,
        f"{sog_kn:.1f}", f"{cog_true % 360:.1f}", when.strftime("%d%m%y"),
        var_s, var_ew, mode,
    ])


def vtg(cog_true, sog_kn, variation_deg, talker="GP", mode="A"):
    """VTG - course and speed over ground. Magnetic course = true - variation(E)."""
    return build_sentence(talker, "VTG", [
        f"{cog_true % 360:.1f}", "T", f"{(cog_true - variation_deg) % 360:.1f}", "M",
        f"{sog_kn:.1f}", "N", f"{sog_kn * KN_TO_KMH:.1f}", "K", mode,
    ])


def zda(when, talker="GP", local_hours=0, local_minutes=0, decimals=2):
    """ZDA - time and date."""
    when = when.astimezone(timezone.utc)
    return build_sentence(talker, "ZDA", [
        utc_time(when, decimals), f"{when.day:02d}", f"{when.month:02d}", f"{when.year:04d}",
        f"{local_hours:02d}" if local_hours >= 0 else f"{local_hours:03d}", f"{local_minutes:02d}",
    ])


def hdt(heading_true, talker="HE"):
    """HDT - heading, true."""
    return build_sentence(talker, "HDT", [f"{heading_true % 360:.1f}", "T"])


def hdg(heading_mag, variation_deg, deviation_deg=0.0, talker="HE"):
    """HDG - heading, deviation and variation (magnetic heading)."""
    dev_s, dev_ew = _ew(deviation_deg)
    var_s, var_ew = _ew(variation_deg)
    return build_sentence(talker, "HDG", [f"{heading_mag % 360:.1f}", dev_s, dev_ew, var_s, var_ew])


def rot(rate_deg_per_min, talker="HE", valid=True):
    """ROT - rate of turn in degrees per minute; negative = bow to port."""
    return build_sentence(talker, "ROT", [f"{rate_deg_per_min:.1f}", "A" if valid else "V"])


def vhw(heading_true, heading_mag, stw_kn, talker="VW"):
    """VHW - water speed and heading."""
    return build_sentence(talker, "VHW", [
        f"{heading_true % 360:.1f}", "T", f"{heading_mag % 360:.1f}", "M",
        f"{stw_kn:.1f}", "N", f"{stw_kn * KN_TO_KMH:.1f}", "K",
    ])


def vbw(water_long_kn, water_trans_kn, ground_long_kn, ground_trans_kn, talker="VW",
        water_valid=True, ground_valid=True):
    """VBW - dual ground/water speed (longitudinal and transverse).

    Only the six classic fields are emitted; the stern fields added in later
    editions are omitted.
    """
    return build_sentence(talker, "VBW", [
        f"{water_long_kn:.1f}", f"{water_trans_kn:.1f}", "A" if water_valid else "V",
        f"{ground_long_kn:.1f}", f"{ground_trans_kn:.1f}", "A" if ground_valid else "V",
    ])


# --- Equipment-level helpers -------------------------------------------------

SENTENCE_KINDS = {
    "gnss": ("GGA", "RMC", "VTG", "GLL", "ZDA"),
    "gyro": ("HDT", "HDG", "ROT"),
    "log": ("VHW", "VBW"),
}


def sentences(source, when, kinds=None, decimals=2):
    """Return one sentence per requested kind for a sensor, all at time `when`.

    `source` is a GnssSource, GyroSource or SpeedLogSource from models.py.
    All sentences come from one `source.reading(when)` call, so they are
    mutually consistent. `kinds` defaults to every kind the equipment offers.
    """
    allowed = SENTENCE_KINDS[source.kind]
    kinds = tuple(k.upper() for k in (kinds or allowed))
    for k in kinds:
        if k not in allowed:
            raise ValueError(f"{source.kind} equipment cannot produce {k}; choose from {allowed}")
    r = source.reading(when)
    t = source.talker
    out = []
    for k in kinds:
        if source.kind == "gnss":
            out.append({
                "GGA": lambda: gga(r.lat, r.lon, r.when, t, 1, r.satellites, r.hdop,
                                   r.altitude_m, r.geoid_sep_m, decimals),
                "RMC": lambda: rmc(r.lat, r.lon, r.when, r.sog_kn, r.cog_true,
                                   r.variation_deg, t, decimals=decimals),
                "VTG": lambda: vtg(r.cog_true, r.sog_kn, r.variation_deg, t),
                "GLL": lambda: gll(r.lat, r.lon, r.when, t, "A", decimals, "A"),
                "ZDA": lambda: zda(r.when, t, decimals=decimals),
            }[k]())
        elif source.kind == "gyro":
            out.append({
                "HDT": lambda: hdt(r.heading_true, t),
                "HDG": lambda: hdg(r.heading_mag, r.variation_deg, 0.0, t),
                "ROT": lambda: rot(r.rot_deg_min, t),
            }[k]())
        else:
            out.append({
                "VHW": lambda: vhw(r.heading_true, r.heading_mag, r.stw_kn, t),
                "VBW": lambda: vbw(r.water_long_kn, r.water_trans_kn,
                                   r.ground_long_kn, r.ground_trans_kn, t),
            }[k]())
    return out
