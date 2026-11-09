import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import datagram as dg  # noqa: E402
import nmea  # noqa: E402
import tagblock as tb  # noqa: E402

GLL = "$GPGLL,5057.970,N,00146.110,E,142451,A*27\r\n"


def raw_block(content):
    """Hand-build a TAG block, bypassing the builder's validation."""
    return f"\\{content}*{tb.checksum(content):02X}\\"


def line(sfi="GP0001", sentence=GLL, **extra):
    params = [("s", sfi)] + list(extra.items())
    return tb.compose_line(tb.build_tag_block(params), sentence)


class HeaderTests(unittest.TestCase):
    def test_header_bytes(self):
        self.assertEqual(dg.HEADER, b"UdPbC\x00")
        self.assertEqual(len(dg.HEADER), 6)

    def test_build_starts_with_header(self):
        self.assertTrue(dg.build_datagram([line()]).startswith(b"UdPbC\x00"))

    def test_wrong_header_rejected(self):
        for bad in (b"RaUdP\x00", b"UdPbC", b"udpbc\x00", b""):
            with self.subTest(bad=bad), self.assertRaises(dg.DatagramError) as cm:
                dg.parse_datagram(bad + line().encode())
            self.assertEqual(cm.exception.kind, "header")


class RoundTripTests(unittest.TestCase):
    def test_single_line(self):
        parsed = dg.parse_datagram(dg.build_datagram([line()]))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].source, "GP0001")
        self.assertEqual((parsed[0].talker, parsed[0].formatter), ("GP", "GLL"))
        self.assertEqual(parsed[0].fields[0], "5057.970")

    def test_multiple_sentences_in_one_datagram(self):
        lines = [line("GP0001"), line("HE0001", nmea.build_sentence("HE", "HDT", ["123.4", "T"]))]
        parsed = dg.parse_datagram(dg.build_datagram(lines))
        self.assertEqual([p.formatter for p in parsed], ["GLL", "HDT"])
        self.assertEqual([p.source for p in parsed], ["GP0001", "HE0001"])

    def test_closest_s_wins(self):
        b1 = tb.build_tag_block([("s", "GP0001")])
        b2 = tb.build_tag_block([("s", "AB0001")])
        parsed = dg.parse_datagram(dg.build_datagram([tb.compose_line([b1, b2], GLL)]))
        self.assertEqual(parsed[0].sources, ["GP0001", "AB0001"])
        self.assertEqual(parsed[0].source, "AB0001")

    def test_non_sfi_s_is_ignored_when_a_valid_one_exists(self):
        b1 = raw_block("s:002300000")
        b2 = tb.build_tag_block([("s", "GP0001")])
        parsed = dg.parse_datagram(dg.build_datagram([tb.compose_line([b1, b2], GLL)]))
        self.assertEqual(parsed[0].sources, ["GP0001"])


class RejectionTests(unittest.TestCase):
    def check(self, data, kind):
        with self.assertRaises(dg.DatagramError) as cm:
            dg.parse_datagram(data)
        self.assertEqual(cm.exception.kind, kind)

    def test_sentence_without_tag_block(self):
        self.check(dg.HEADER + GLL.encode(), "tag")

    def test_only_non_sfi_source(self):
        block = raw_block("s:002300000")
        self.check(dg.HEADER + (block + GLL).encode(), "tag")

    def test_bad_tag_checksum(self):
        self.check(dg.HEADER + ("\\s:GP0001*00\\" + GLL).encode(), "tag")

    def test_bad_sentence_checksum_discards_whole_datagram(self):
        good = line()
        bad = line(sentence="$GPGLL,5057.970,N,00146.110,E,142451,A*28\r\n")
        self.check(dg.HEADER + (good + bad).encode(), "sentence")

    def test_missing_crlf(self):
        self.check(dg.HEADER + line().rstrip("\r\n").encode(), "sentence")

    def test_empty_payload(self):
        self.check(dg.HEADER, "sentence")

    def test_non_ascii(self):
        self.check(dg.HEADER + line().encode() + "é\r\n".encode(), "sentence")


class SizeTests(unittest.TestCase):
    def test_limit_is_1472(self):
        self.assertEqual(dg.MAX_DATAGRAM_SIZE, 1472)

    def test_exactly_at_limit_is_accepted(self):
        one = line()
        count = (dg.MAX_DATAGRAM_SIZE - len(dg.HEADER)) // len(one)
        data = dg.build_datagram([one] * count)
        self.assertLessEqual(len(data), dg.MAX_DATAGRAM_SIZE)
        self.assertGreater(len(data) + len(one), dg.MAX_DATAGRAM_SIZE)

    def test_over_limit_rejected_on_build(self):
        one = line()
        count = (dg.MAX_DATAGRAM_SIZE - len(dg.HEADER)) // len(one) + 1
        with self.assertRaises(dg.DatagramError) as cm:
            dg.build_datagram([one] * count)
        self.assertEqual(cm.exception.kind, "size")

    def test_over_limit_rejected_on_parse(self):
        with self.assertRaises(dg.DatagramError) as cm:
            dg.parse_datagram(dg.HEADER + b"x" * dg.MAX_DATAGRAM_SIZE)
        self.assertEqual(cm.exception.kind, "size")


if __name__ == "__main__":
    unittest.main()
