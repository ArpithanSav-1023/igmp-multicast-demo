"""IEC 61162-1 / NMEA 0183 sentence helpers (Stage 3.1 / 3.2).

Pure standard library, no networking. Covers:
  - checksum calculation (XOR of characters between '$'/'!' and '*')
  - building a sentence from talker, formatter and fields
  - validating / parsing a received sentence
  - lat/lon formatting and two example builders (GLL, GGA)

Sentence layout:  $<talker><formatter>,<field>,...,<field>*<hh><CR><LF>
"""

from datetime import datetime, timezone

CRLF = "\r\n"
MAX_SENTENCE_LEN = 82  # including start char and <CR><LF>


def checksum(body: str) -> int:
    """8-bit XOR of every character in body.

    body is the text between the start delimiter ('$' or '!') and '*',
    exclusive of both.
    """
    value = 0
    for ch in body.encode("ascii"):
        value ^= ch
    return value


def build_sentence(talker: str, formatter: str, fields, start: str = "$") -> str:
    """Return a complete sentence including checksum and <CR><LF>.

    talker:    two upper-case letters, e.g. "GP"
    formatter: three upper-case letters, e.g. "GLL"
    fields:    iterable of values; None becomes an empty field
    """
    if start not in ("$", "!"):
        raise ValueError("start must be '$' or '!'")
    if len(talker) != 2 or not talker.isalpha() or not talker.isupper():
        raise ValueError(f"talker must be two upper-case letters: {talker!r}")
    if len(formatter) != 3 or not formatter.isalnum() or not formatter.isupper():
        raise ValueError(f"formatter must be three upper-case characters: {formatter!r}")

    parts = [talker + formatter]
    for field in fields:
        text = "" if field is None else str(field)
        if any(c in text for c in "$!*,\\^~\r\n"):
            raise ValueError(f"reserved character in field: {text!r}")
        parts.append(text)

    body = ",".join(parts)
    sentence = f"{start}{body}*{checksum(body):02X}{CRLF}"
    if len(sentence) > MAX_SENTENCE_LEN:
        raise ValueError(f"sentence is {len(sentence)} characters, max {MAX_SENTENCE_LEN}")
    return sentence


def parse_sentence(text: str):
    """Validate a sentence and split it into (talker, formatter, fields).

    Raises ValueError if the framing or checksum is wrong. A trailing
    <CR><LF> is optional on input.
    """
    text = text.rstrip("\r\n")
    if not text or text[0] not in "$!":
        raise ValueError("sentence must start with '$' or '!'")
    star = text.rfind("*")
    if star == -1 or len(text) - star - 1 != 2:
        raise ValueError("missing or malformed '*hh' checksum")
    body, given = text[1:star], text[star + 1:]
    try:
        expected_hex = int(given, 16)
    except ValueError:
        raise ValueError(f"checksum is not hexadecimal: {given!r}")
    actual = checksum(body)
    if actual != expected_hex:
        raise ValueError(f"checksum mismatch: sentence says {given.upper()}, computed {actual:02X}")

    address, *fields = body.split(",")
    if len(address) < 5:
        # Proprietary or unusual address fields are out of scope for stage 3.1.
        raise ValueError(f"unsupported address field: {address!r}")
    return address[:2], address[2:], fields


def format_lat(degrees: float) -> tuple:
    """Decimal degrees -> ('ddmm.mmm', 'N'|'S')."""
    hemi = "N" if degrees >= 0 else "S"
    return _ddmm(abs(degrees), 2), hemi


def format_lon(degrees: float) -> tuple:
    """Decimal degrees -> ('dddmm.mmm', 'E'|'W')."""
    hemi = "E" if degrees >= 0 else "W"
    return _ddmm(abs(degrees), 3), hemi


def _ddmm(value: float, deg_digits: int) -> str:
    whole = int(value)
    minutes = round((value - whole) * 60, 3)
    if minutes >= 60:  # rounding carried into the next degree
        whole += 1
        minutes = 0.0
    return f"{whole:0{deg_digits}d}{minutes:06.3f}"


def _utc_hhmmss(when: datetime) -> str:
    return when.strftime("%H%M%S")


def gll(lat: float, lon: float, when: datetime = None, talker: str = "GP", status: str = "A") -> str:
    """Geographic position - latitude/longitude."""
    when = when or datetime.now(timezone.utc)
    lat_s, ns = format_lat(lat)
    lon_s, ew = format_lon(lon)
    return build_sentence(talker, "GLL", [lat_s, ns, lon_s, ew, _utc_hhmmss(when), status])


def gga(lat: float, lon: float, when: datetime = None, talker: str = "GP",
        quality: int = 1, satellites: int = 8, hdop: float = 0.9,
        altitude_m: float = 0.0, geoid_sep_m: float = 0.0) -> str:
    """GPS fix data."""
    when = when or datetime.now(timezone.utc)
    lat_s, ns = format_lat(lat)
    lon_s, ew = format_lon(lon)
    return build_sentence(talker, "GGA", [
        _utc_hhmmss(when), lat_s, ns, lon_s, ew, quality, f"{satellites:02d}",
        f"{hdop:.1f}", f"{altitude_m:.1f}", "M", f"{geoid_sep_m:.1f}", "M", None, None,
    ])


if __name__ == "__main__":
    # Quick demo: print one of each sentence.
    print(gll(50.9662, 1.7685), end="")
    print(gga(48.1173, 11.5167, altitude_m=545.4, geoid_sep_m=46.9), end="")
