"""Compatibility shim: the implementation now lives in lab/nmea/.

Kept so that existing scripts (nmea_sender.py, datagram.py, ...) and tests
that do `import nmea` keep working unchanged.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lab.nmea.checksum import CRLF, MAX_SENTENCE_LEN, build_sentence, checksum, parse_sentence  # noqa: E402,F401
from lab.nmea.generator import format_lat, format_lon, gga, gll  # noqa: E402,F401

if __name__ == "__main__":
    # Quick demo: print one of each sentence.
    print(gll(50.9662, 1.7685), end="")
    print(gga(48.1173, 11.5167, altitude_m=545.4, geoid_sep_m=46.9), end="")
