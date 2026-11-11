"""NMEA 0183 framing: checksum, sentence building and validation.

Sentence layout:  $<talker><formatter>,<field>,...,<field>*<hh><CR><LF>
The checksum is the 8-bit XOR of every character between the start
delimiter ('$' or '!') and '*', exclusive of both.
"""

CRLF = "\r\n"
MAX_SENTENCE_LEN = 82  # including start character and <CR><LF>


def checksum(body: str) -> int:
    """8-bit XOR of every character in body (text between '$'/'!' and '*')."""
    value = 0
    for ch in body.encode("ascii"):
        value ^= ch
    return value


def build_sentence(talker: str, formatter: str, fields, start: str = "$") -> str:
    """Return a complete sentence including checksum and <CR><LF>.

    talker:    two upper-case letters, e.g. "GP"
    formatter: three upper-case characters, e.g. "GLL"
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
        raise ValueError(f"unsupported address field: {address!r}")
    return address[:2], address[2:], fields
