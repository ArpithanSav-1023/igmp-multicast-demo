"""NMEA TAG block helpers as used by IEC 61162-450:2024 (Stage 3.3 / 3.4).

Rules implemented here come from IEC 61162-450:2024 clause 7.2.3, 4.4.3 and
Annex B:
  - TAG block syntax:  \\code:value,code:value*hh\\
  - checksum: 8-bit XOR of every character between the opening '\\' and '*'
  - maximum length 80 characters including both '\\' delimiters
  - value characters: [-. A-Za-z0-9]
  - 's' value is an SFI "ccxxxx" (two characters + four digits, 9999 reserved)
  - 'g' value is "line-total-group", group code 1..99; if present it must
    be the first parameter in the block
  - 'n' value is a line count 1..999

Not implemented yet: authentication ('a'), relative time ('r'), cluster
identifiers ('x', 'z').
"""

import re
import time

MAX_TAG_BLOCK_LEN = 80
_VALUE_RE = re.compile(r"[-. A-Za-z0-9]+\Z")
_CODE_RE = re.compile(r"[a-z]\Z")  # Table B.1: all codes are one lower-case character
_SFI_RE = re.compile(r"[A-Z0-9]{2}[0-9]{4}\Z")
_G_RE = re.compile(r"([0-9]+)-([0-9]+)-([0-9]+)\Z")
_MAX_LEN = {"s": 15, "d": 15, "a": 32}  # Table B.1 maxima


def checksum(content: str) -> int:
    """XOR of all characters between the opening '\\' and the '*'."""
    value = 0
    for ch in content.encode("ascii"):
        value ^= ch
    return value


def sfi(talker: str, instance: int) -> str:
    """Build an SFI such as 'GP0001'. Instance 9999 is reserved (clause 4.4.3)."""
    if not 1 <= instance <= 9998:
        raise ValueError("SFI instance must be 1..9998 (9999 is reserved for un-configured SFs)")
    value = f"{talker}{instance:04d}"
    if not _SFI_RE.match(value):
        raise ValueError(f"invalid SFI: {value!r}")
    return value


def g_value(line: int, total: int, group: int) -> str:
    """Build a 'g' value, e.g. g_value(1, 2, 34) -> '1-2-34'."""
    if not (1 <= line <= total):
        raise ValueError("line must be between 1 and total")
    if not 1 <= group <= 99:
        raise ValueError("group code must be 1..99")
    return f"{line}-{total}-{group}"


def posix_ms(now: float = None) -> str:
    """Current time as integer milliseconds since the Unix epoch.

    Table B.1 only says "POSIX time, positive integer". The standard's own
    examples use 13-digit values (e.g. 1558090544462), so milliseconds are
    used here. This is an interpretation of those examples, not a stated rule.
    """
    return str(int((time.time() if now is None else now) * 1000))


def _validate_param(code: str, value: str) -> None:
    if not _CODE_RE.match(code):
        raise ValueError(f"parameter code must be one lower-case letter: {code!r}")
    if not _VALUE_RE.match(value):
        raise ValueError(f"invalid characters in value for {code!r}: {value!r}")
    if code in _MAX_LEN and len(value) > _MAX_LEN[code]:
        raise ValueError(f"value for {code!r} longer than {_MAX_LEN[code]} characters")
    if code == "s" and not _SFI_RE.match(value):
        raise ValueError(f"'s' value is not an SFI of the form ccxxxx: {value!r}")
    if code == "g":
        m = _G_RE.match(value)
        if not m:
            raise ValueError(f"'g' value must be line-total-group: {value!r}")
        line, total, group = (int(x) for x in m.groups())
        if not (1 <= line <= total and 1 <= group <= 99):
            raise ValueError(f"'g' value out of range: {value!r}")
    if code == "n" and not (value.isdigit() and 1 <= int(value) <= 999):
        raise ValueError(f"'n' value must be 1..999: {value!r}")
    if code == "c" and not (value.isdigit() and int(value) > 0):
        raise ValueError(f"'c' value must be a positive integer: {value!r}")


def build_tag_block(params) -> str:
    """Return one TAG block, e.g. '\\s:GP0001,c:1558090544462*hh\\'.

    params is an ordered sequence of (code, value) pairs. Order is preserved.
    """
    params = [(c, str(v)) for c, v in params]
    if not params:
        raise ValueError("a TAG block needs at least one parameter")
    for code, value in params:
        _validate_param(code, value)
    if any(code == "g" for code, _ in params) and params[0][0] != "g":
        raise ValueError("'g' must be the first parameter in the TAG block")

    content = ",".join(f"{c}:{v}" for c, v in params)
    block = f"\\{content}*{checksum(content):02X}\\"
    if len(block) > MAX_TAG_BLOCK_LEN:
        raise ValueError(f"TAG block is {len(block)} characters, max {MAX_TAG_BLOCK_LEN}")
    return block


def parse_tag_block(block: str):
    """Validate one TAG block string and return its [(code, value), ...].

    Raises ValueError on bad framing, length, checksum or parameter syntax.
    """
    if len(block) > MAX_TAG_BLOCK_LEN:
        raise ValueError(f"TAG block longer than {MAX_TAG_BLOCK_LEN} characters")
    if len(block) < 2 or block[0] != "\\" or block[-1] != "\\":
        raise ValueError("TAG block must start and end with '\\'")
    inner = block[1:-1]
    star = inner.rfind("*")
    if star == -1 or len(inner) - star - 1 != 2:
        raise ValueError("missing or malformed '*hh' checksum")
    content, given = inner[:star], inner[star + 1:]
    try:
        given_value = int(given, 16)
    except ValueError:
        raise ValueError(f"checksum is not hexadecimal: {given!r}")
    actual = checksum(content)
    if actual != given_value:
        raise ValueError(f"checksum mismatch: block says {given.upper()}, computed {actual:02X}")

    params = []
    for pair in content.split(","):
        code, sep, value = pair.partition(":")
        if not sep or not code or not value:
            raise ValueError(f"malformed parameter: {pair!r}")
        params.append((code, value))
    return params


def split_line(line: str):
    """Split '<tagblock>*<sentence><CR><LF>' into ([tag blocks], sentence).

    The sentence part (starting at '$' or '!') is returned unmodified so it
    can be handed to nmea.parse_sentence. TAG blocks are returned as strings.
    """
    blocks = []
    rest = line
    while rest.startswith("\\"):
        end = rest.find("\\", 1)
        if end == -1:
            raise ValueError("unterminated TAG block")
        blocks.append(rest[:end + 1])
        rest = rest[end + 1:]
    return blocks, rest


def compose_line(blocks, sentence: str) -> str:
    """Prefix a sentence with one or more TAG blocks (no separator, per B.5)."""
    if isinstance(blocks, str):
        blocks = [blocks]
    if not sentence or sentence[0] not in "$!":
        raise ValueError("sentence must start with '$' or '!'")
    return "".join(blocks) + sentence


if __name__ == "__main__":
    print(build_tag_block([("s", "GP0001"), ("c", posix_ms())]))
    print(build_tag_block([("g", "1-2-34"), ("s", "IN0001"), ("n", "333")]))
