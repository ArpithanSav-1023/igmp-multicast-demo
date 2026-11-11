import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lab.nmea import generator as g  # noqa: E402
from lab.nmea.checksum import checksum, parse_sentence  # noqa: E402
from lab.nmea.models import (GnssSource, GyroSource, SpeedLogSource,  # noqa: E402
                             Vessel)

UTC = timezone.utc
T0 = datetime(2026, 11, 11, 10, 30, 15, 250000, tzinfo=UTC)


def fields_of(sentence):
    return parse_sentence(sentence)[2]


class KnownVectors(unittest.TestCase):
    """Example sentences whose checksums match this implementation.

    These guard the checksum and field order against regressions. They are
    examples recalled from common NMEA documentation, not text from IEC 61162-1.
    """

    def test_rmc(self):
        s = g.rmc(48.1173, 11.516667, datetime(1994, 3, 23, 12, 35, 19, tzinfo=UTC),
                  22.4, 84.4, -3.1)
        self.assertEqual(s, "$GPRMC,123519,A,4807.038,N,01131.000,E,22.4,84.4,230394,3.1,W,A*07\r\n")

    def test_checksum_of_remembered_rmc(self):
        self.assertEqual(checksum("GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W"), 0x6A)

    def test_checksum_of_remembered_vtg(self):
        self.assertEqual(checksum("GPVTG,054.7,T,034.4,M,005.5,N,010.2,K"), 0x48)

    def test_checksum_of_remembered_zda(self):
        self.assertEqual(checksum("GPZDA,160012.71,11,03,2004,-1,00"), 0x7D)

    def test_checksum_of_remembered_vhw(self):
        self.assertEqual(checksum("IIVHW,,T,,M,06.12,N,11.33,K"), 0x50)


class FieldBuilders(unittest.TestCase):
    def test_zda_fields(self):
        f = fields_of(g.zda(T0))
        self.assertEqual(f, ["103015.25", "11", "11", "2026", "00", "00"])

    def test_vtg_magnetic_course(self):
        f = fields_of(g.vtg(90.0, 10.0, 2.0))
        self.assertEqual(f[:4], ["90.0", "T", "88.0", "M"])
        self.assertEqual(f[4:8], ["10.0", "N", "18.5", "K"])

    def test_vtg_wraps_below_zero(self):
        self.assertEqual(fields_of(g.vtg(1.0, 5.0, 3.0))[2], "358.0")

    def test_hdt_wraps(self):
        self.assertEqual(fields_of(g.hdt(361.5)), ["1.5", "T"])

    def test_rot_sign_and_validity(self):
        self.assertEqual(fields_of(g.rot(-3.0)), ["-3.0", "A"])
        self.assertEqual(fields_of(g.rot(3.0, valid=False)), ["3.0", "V"])

    def test_vhw_kmh(self):
        f = fields_of(g.vhw(100.0, 98.0, 10.0))
        self.assertEqual(f, ["100.0", "T", "98.0", "M", "10.0", "N", "18.5", "K"])

    def test_vbw(self):
        self.assertEqual(fields_of(g.vbw(10.0, 0.0, 10.3, 0.0)), ["10.0", "0.0", "A", "10.3", "0.0", "A"])

    def test_variation_direction(self):
        self.assertEqual(fields_of(g.hdg(88.0, 2.0))[3:], ["2.0", "E"])
        self.assertEqual(fields_of(g.hdg(92.0, -2.0))[3:], ["2.0", "W"])

    def test_gll_mode_field_optional(self):
        self.assertEqual(len(fields_of(g.gll(1.0, 1.0, T0))), 6)
        self.assertEqual(len(fields_of(g.gll(1.0, 1.0, T0, mode="A"))), 7)

    def test_time_decimals(self):
        self.assertEqual(g.utc_time(T0), "103015")
        self.assertEqual(g.utc_time(T0, 2), "103015.25")


class VesselModel(unittest.TestCase):
    V = Vessel()

    def test_deterministic(self):
        self.assertEqual(self.V.position(T0), Vessel().position(T0))

    def test_circle_is_periodic(self):
        period = timedelta(minutes=360 / self.V.turn_rate_deg_min)
        a = self.V.position(T0)
        b = self.V.position(T0 + period)
        self.assertAlmostEqual(a[0], b[0], places=6)
        self.assertAlmostEqual(a[1], b[1], places=6)

    def test_moves_along_course(self):
        """A short step must change position in the direction of the heading."""
        v = Vessel(turn_rate_deg_min=0.0, heading0_deg=0.0)  # straight, heading north
        a, b = v.position(T0), v.position(T0 + timedelta(seconds=60))
        self.assertGreater(b[0], a[0])
        self.assertAlmostEqual(b[1], a[1], places=9)
        v = Vessel(turn_rate_deg_min=0.0, heading0_deg=90.0)  # east
        a, b = v.position(T0), v.position(T0 + timedelta(seconds=60))
        self.assertGreater(b[1], a[1])
        self.assertAlmostEqual(b[0], a[0], places=9)

    def test_distance_matches_speed(self):
        """Over 60 s at SOG the distance travelled equals SOG x time (nm)."""
        v = Vessel(turn_rate_deg_min=0.0, heading0_deg=0.0)
        a, b = v.position(T0), v.position(T0 + timedelta(seconds=360))
        nm = (b[0] - a[0]) * 60.0
        self.assertAlmostEqual(nm, v.sog_kn * 0.1, places=6)

    def test_circle_instantaneous_speed_equals_sog(self):
        """Speed derived from position differences equals SOG on the circle."""
        for turn in (3.0, -3.0, 6.0):
            v = Vessel(turn_rate_deg_min=turn)
            a, b = v.position(T0), v.position(T0 + timedelta(seconds=1))
            dn = (b[0] - a[0]) * 60.0
            de = (b[1] - a[1]) * 60.0 * math.cos(math.radians(v.center_lat))
            speed_kn = math.hypot(dn, de) * 3600.0
            self.assertAlmostEqual(speed_kn, v.sog_kn, delta=0.01)

    def test_velocity_direction_equals_heading(self):
        for turn in (3.0, -3.0):
            v = Vessel(turn_rate_deg_min=turn)
            a, b = v.position(T0), v.position(T0 + timedelta(seconds=1))
            dn = (b[0] - a[0]) * 60.0
            de = (b[1] - a[1]) * 60.0 * math.cos(math.radians(v.center_lat))
            bearing = math.degrees(math.atan2(de, dn)) % 360.0
            mid = v.heading(T0 + timedelta(seconds=0.5))
            diff = abs((bearing - mid + 180) % 360 - 180)
            self.assertLess(diff, 0.2)

    def test_heading_rate_matches_turn_rate(self):
        v = Vessel(turn_rate_deg_min=3.0)
        d = (v.heading(T0 + timedelta(seconds=60)) - v.heading(T0)) % 360
        self.assertAlmostEqual(d, 3.0, places=6)


class Equipment(unittest.TestCase):
    def setUp(self):
        self.vessel = Vessel()
        self.gnss1 = GnssSource("gnss1", self.vessel, "GP", seed=11)
        self.gnss2 = GnssSource("gnss2", self.vessel, "GN", seed=12)
        self.gyro = GyroSource("gyro1", self.vessel)
        self.log = SpeedLogSource("log1", self.vessel)

    def test_same_instant_sentences_agree(self):
        """GGA, RMC, GLL, ZDA and VTG from one GNSS describe the same fix."""
        gga, rmc, vtg, gll, zda = g.sentences(self.gnss1, T0, ["GGA", "RMC", "VTG", "GLL", "ZDA"])
        fg, fr, fv, fl, fz = (fields_of(x) for x in (gga, rmc, vtg, gll, zda))
        self.assertEqual(fg[0], fr[0])               # time GGA == RMC
        self.assertEqual(fg[0], fz[0])               # time GGA == ZDA
        self.assertEqual(fg[0], fl[4])               # time GGA == GLL
        self.assertEqual(fg[1:5], fr[2:6])           # position GGA == RMC
        self.assertEqual(fg[1:5], fl[0:4])           # position GGA == GLL
        self.assertEqual(fr[6], fv[4])               # SOG RMC == VTG
        self.assertEqual(fr[7], fv[0])               # COG RMC == VTG true

    def test_rmc_date_matches_zda(self):
        _, rmc = g.sentences(self.gnss1, T0, ["ZDA", "RMC"])
        zda = g.sentences(self.gnss1, T0, ["ZDA"])[0]
        d, m, y = fields_of(zda)[1:4]
        self.assertEqual(fields_of(rmc)[8], f"{d}{m}{y[2:]}")

    def test_repeated_calls_identical(self):
        self.assertEqual(g.sentences(self.gnss1, T0), g.sentences(self.gnss1, T0))

    def test_two_gnss_agree_within_a_few_metres(self):
        a, b = self.gnss1.reading(T0), self.gnss2.reading(T0)
        dn = (a.lat - b.lat) * 60.0 * 1852.0
        de = (a.lon - b.lon) * 60.0 * 1852.0 * math.cos(math.radians(a.lat))
        self.assertLess(math.hypot(dn, de), 6.0)
        self.assertLess(abs(a.sog_kn - b.sog_kn), 0.2)

    def test_two_gnss_distinguishable_by_talker(self):
        self.assertEqual(parse_sentence(g.sentences(self.gnss1, T0, ["GGA"])[0])[0], "GP")
        self.assertEqual(parse_sentence(g.sentences(self.gnss2, T0, ["GGA"])[0])[0], "GN")

    def test_gyro_heading_relations(self):
        hdt, hdg = g.sentences(self.gyro, T0, ["HDT", "HDG"])
        true = float(fields_of(hdt)[0])
        mag = float(fields_of(hdg)[0])
        var = float(fields_of(hdg)[3]) * (1 if fields_of(hdg)[4] == "E" else -1)
        self.assertAlmostEqual((true - var) % 360, mag, delta=0.11)

    def test_rot_matches_heading_change(self):
        rate = self.gyro.reading(T0).rot_deg_min
        later = T0 + timedelta(seconds=60)
        change = (self.gyro.reading(later).heading_true - self.gyro.reading(T0).heading_true) % 360
        self.assertAlmostEqual(change, rate, delta=0.5)

    def test_log_water_and_ground_speed_relation(self):
        vhw, vbw = g.sentences(self.log, T0, ["VHW", "VBW"])
        stw = float(fields_of(vhw)[4])
        water_long = float(fields_of(vbw)[0])
        ground_long = float(fields_of(vbw)[3])
        self.assertAlmostEqual(stw, water_long, delta=0.11)
        self.assertAlmostEqual(ground_long - water_long, self.vessel.current_kn, delta=0.2)

    def test_gnss_speed_agrees_with_log_ground_speed(self):
        gnss_sog = self.gnss1.reading(T0).sog_kn
        log_sog = self.log.reading(T0).ground_long_kn
        self.assertAlmostEqual(gnss_sog, log_sog, delta=0.2)

    def test_gnss_course_agrees_with_gyro_heading(self):
        diff = abs((self.gnss1.reading(T0).cog_true - self.gyro.reading(T0).heading_true + 180) % 360 - 180)
        self.assertLess(diff, 0.5)

    def test_all_sentences_valid_and_short(self):
        for src in (self.gnss1, self.gnss2, self.gyro, self.log):
            for s in g.sentences(src, T0):
                parse_sentence(s)
                self.assertLessEqual(len(s), 82)
                self.assertTrue(s.endswith("\r\n"))
                self.assertTrue(s.isascii())

    def test_wrong_kind_rejected(self):
        with self.assertRaises(ValueError):
            g.sentences(self.gyro, T0, ["GGA"])

    def test_valid_over_a_day(self):
        """Every generated sentence stays valid across a full day of timestamps."""
        for minutes in range(0, 24 * 60, 7):
            when = T0 + timedelta(minutes=minutes, seconds=minutes % 60)
            for src in (self.gnss1, self.gyro, self.log):
                for s in g.sentences(src, when):
                    parse_sentence(s)

    def test_latitude_and_longitude_within_range(self):
        for minutes in range(0, 24 * 60, 3):
            r = self.gnss1.reading(T0 + timedelta(minutes=minutes))
            self.assertTrue(-90 <= r.lat <= 90 and -180 <= r.lon <= 180)


if __name__ == "__main__":
    unittest.main()
