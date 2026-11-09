"""IEC 61162-450 "UdPbC" datagram builder and parser (Stage 3.5).

Datagram layout (IEC 61162-450:2024 clauses 6.2.4, 7.1, 7.2):

    "UdPbC" 0x00                      6-byte header
    <TAG block(s)><sentence><CR><LF>  one or more lines, no separators

Rules implemented:
  - header is the ASCII string "UdPbC" followed by a null byte (7.1.1)
  - total datagram size, including header, is at most 1472 bytes (6.2.4)
  - every sentence must be preceded by at least one valid TAG block (7.2.3.1)
  - a sentence needs an 's' parameter holding a valid SFI, otherwise it is
    ignored (7.2.3.2, 7.2.3.4)
  - any TAG block or sentence syntax error discards the whole datagram (7.2.4)

Not implemented: TAG-only lines, 'g' group consistency checks, error counters
(7.1.2 / 7.2.5), authentication.
"""

from dataclasses import dataclass
from typing import List, Tuple

import nmea
import tagblock

HEADER = b"UdPbC\x00"
MAX_DATAGRAM_SIZE = 1472


class DatagramError(ValueError):
    """Raised for an invalid datagram. `kind` is one of: header, size, tag, sentence."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind


@dataclass
class Line:
    tag_params: List[Tuple[str, str]]  # all TAG parameters, in order of appearance
    talker: str
    formatter: str
    fields: List[str]
    sources: List[str]  # every 's' value that is a valid SFI, left to right
    raw: str  # the full line as received, including <CR><LF>

    @property
    def source(self) -> str:
        """The 's' SFI closest to the sentence (clause 7.2.3.2: closest wins)."""
        return self.sources[-1]


def build_datagram(lines) -> bytes:
    """Concatenate header and lines. Each line is TAG block(s) + sentence + CRLF."""
    if isinstance(lines, str):
        lines = [lines]
    if not lines:
        raise DatagramError("sentence", "a datagram needs at least one line")
    payload = "".join(lines)
    try:
        data = HEADER + payload.encode("ascii")
    except UnicodeEncodeError as exc:
        raise DatagramError("sentence", f"non-ASCII character: {exc}")
    if len(data) > MAX_DATAGRAM_SIZE:
        raise DatagramError("size", f"{len(data)} bytes exceeds {MAX_DATAGRAM_SIZE}")
    # Fail early on anything a conforming receiver would reject.
    parse_datagram(data)
    return data


def parse_datagram(data: bytes) -> List[Line]:
    """Validate a datagram and return its parsed lines.

    Raises DatagramError for the first problem found; per clause 7.2.4 the
    caller must then discard the whole datagram.
    """
    if not data.startswith(HEADER):
        raise DatagramError("header", f"expected {HEADER!r}, got {data[:6]!r}")
    if len(data) > MAX_DATAGRAM_SIZE:
        raise DatagramError("size", f"{len(data)} bytes exceeds {MAX_DATAGRAM_SIZE}")
    try:
        text = data[len(HEADER):].decode("ascii")
    except UnicodeDecodeError as exc:
        raise DatagramError("sentence", f"non-ASCII payload: {exc}")
    if not text:
        raise DatagramError("sentence", "datagram has no lines")
    if not text.endswith(nmea.CRLF):
        raise DatagramError("sentence", "last line is not terminated by <CR><LF>")

    result = []
    for raw in text.split(nmea.CRLF)[:-1]:
        raw += nmea.CRLF
        try:
            blocks, sentence = tagblock.split_line(raw)
        except ValueError as exc:
            raise DatagramError("tag", str(exc))
        if not blocks:
            raise DatagramError("tag", "sentence is not preceded by a TAG block")

        params = []
        for block in blocks:
            try:
                params.extend(tagblock.parse_tag_block(block))
            except ValueError as exc:
                raise DatagramError("tag", str(exc))

        sources = [v for c, v in params if c == "s" and tagblock._SFI_RE.match(v)]
        if not sources:
            raise DatagramError("tag", "no 's' parameter holding a valid SFI")

        try:
            talker, formatter, fields = nmea.parse_sentence(sentence)
        except ValueError as exc:
            raise DatagramError("sentence", str(exc))
        result.append(Line(params, talker, formatter, fields, sources, raw))
    return result


if __name__ == "__main__":
    sentence = nmea.gll(50.9662, 1.7685)
    block = tagblock.build_tag_block([("s", "GP0001"), ("c", tagblock.posix_ms())])
    data = build_datagram([tagblock.compose_line(block, sentence)])
    print(data)
    print(f"{len(data)} bytes")
