import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import nmea  # noqa: E402


class ChecksumTests(unittest.TestCase):
    def test_gll_example_from_iec_61162_450(self):
        # Sentence taken from IEC 61162-450:2024 clause 7.2.3.1.
        self.assertEqual(nmea.checksum("GPGLL,5057.970,N,00146.110,E,142451,A"), 0x27)

    def test_gga_well_known_example(self):
        body = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
        self.assertEqual(nmea.checksum(body), 0x47)

    def test_empty_body(self):
        self.assertEqual(nmea.checksum(""), 0)


class BuildTests(unittest.TestCase):
    def test_build_matches_standard_example(self):
        s = nmea.build_sentence("GP", "GLL", ["5057.970", "N", "00146.110", "E", "142451", "A"])
        self.assertEqual(s, "$GPGLL,5057.970,N,00146.110,E,142451,A*27\r\n")

    def test_none_becomes_empty_field(self):
        s = nmea.build_sentence("GP", "XXX", ["a", None, "b"])
        self.assertTrue(s.startswith("$GPXXX,a,,b*"))

    def test_rejects_bad_talker(self):
        with self.assertRaises(ValueError):
            nmea.build_sentence("gp", "GLL", [])
        with self.assertRaises(ValueError):
            nmea.build_sentence("GPS", "GLL", [])

    def test_rejects_reserved_char_in_field(self):
        with self.assertRaises(ValueError):
            nmea.build_sentence("GP", "GLL", ["a,b"])

    def test_rejects_too_long(self):
        with self.assertRaises(ValueError):
            nmea.build_sentence("GP", "GLL", ["x" * 80])


class ParseTests(unittest.TestCase):
    def test_roundtrip(self):
        s = nmea.build_sentence("II", "HDT", ["123.4", "T"])
        self.assertEqual(nmea.parse_sentence(s), ("II", "HDT", ["123.4", "T"]))

    def test_accepts_without_crlf(self):
        self.assertEqual(nmea.parse_sentence("$GPGLL,5057.970,N,00146.110,E,142451,A*27")[1], "GLL")

    def test_bad_checksum(self):
        with self.assertRaises(ValueError):
            nmea.parse_sentence("$GPGLL,5057.970,N,00146.110,E,142451,A*28")

    def test_missing_checksum(self):
        with self.assertRaises(ValueError):
            nmea.parse_sentence("$GPGLL,5057.970,N,00146.110,E,142451,A")

    def test_bad_start(self):
        with self.assertRaises(ValueError):
            nmea.parse_sentence("GPGLL,1*00")

    def test_non_hex_checksum(self):
        with self.assertRaises(ValueError):
            nmea.parse_sentence("$GPGLL,1*ZZ")


class FormatTests(unittest.TestCase):
    def test_lat_lon(self):
        self.assertEqual(nmea.format_lat(48.1173), ("4807.038", "N"))
        self.assertEqual(nmea.format_lon(11.516667), ("01131.000", "E"))
        self.assertEqual(nmea.format_lat(-33.5), ("3330.000", "S"))
        self.assertEqual(nmea.format_lon(-0.5), ("00030.000", "W"))

    def test_rounding_carry(self):
        # 59.9999999 minutes must carry into the degree, not print 60.000.
        self.assertEqual(nmea.format_lat(10.9999999), ("1100.000", "N"))


class BuilderTests(unittest.TestCase):
    WHEN = datetime(2026, 1, 1, 12, 35, 19, tzinfo=timezone.utc)

    def test_gga_matches_known_sentence(self):
        s = nmea.gga(48.1173, 11.516667, self.WHEN, altitude_m=545.4, geoid_sep_m=46.9)
        self.assertEqual(s, "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n")

    def test_gll_is_valid(self):
        talker, fmt, fields = nmea.parse_sentence(nmea.gll(50.9662, 1.7685, self.WHEN))
        self.assertEqual((talker, fmt), ("GP", "GLL"))
        self.assertEqual(fields[4], "123519")


if __name__ == "__main__":
    unittest.main()
