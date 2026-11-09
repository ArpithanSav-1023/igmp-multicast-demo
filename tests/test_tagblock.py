import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import nmea  # noqa: E402
import tagblock as tb  # noqa: E402


class StandardVectors(unittest.TestCase):
    """TAG blocks copied from IEC 61162-450:2024 clause 7.2.3.3 and 7.2.3.7."""

    VECTORS = [
        (r"\g:1-2-34,s:IN0001*3A\\", [("g", "1-2-34"), ("s", "IN0001")]),
        (r"\g:2-2-34,s:IN0001*39\\", [("g", "2-2-34"), ("s", "IN0001")]),
        (r"\g:1-2-46,s:IN0001*3F\\", [("g", "1-2-46"), ("s", "IN0001")]),
        (r"\g:2-2-46,s:IN0001*3C\\", [("g", "2-2-46"), ("s", "IN0001")]),
        (r"\g:1-2-34,s:TI0001,n:333*6B\\", [("g", "1-2-34"), ("s", "TI0001"), ("n", "333")]),
    ]

    def test_parse_standard_blocks(self):
        for raw, expected in self.VECTORS:
            block = raw[:-1]  # the raw strings above end in an escaped backslash
            with self.subTest(block=block):
                self.assertEqual(tb.parse_tag_block(block), expected)

    def test_build_reproduces_standard_blocks(self):
        for raw, params in self.VECTORS:
            block = raw[:-1]
            with self.subTest(block=block):
                self.assertEqual(tb.build_tag_block(params), block)

    def test_full_line_from_standard(self):
        line = "\\g:1-2-34,s:IN0001*3A\\!ABVDM,1,1,1,B,100000?0?wJm4:`GMUrf40g604:4,0*04"
        blocks, sentence = tb.split_line(line)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(tb.parse_tag_block(blocks[0])[1], ("s", "IN0001"))
        # The sentence checksum in the standard's example is also verifiable.
        talker, fmt, _ = nmea.parse_sentence(sentence)
        self.assertEqual((talker, fmt), ("AB", "VDM"))


class BuildTests(unittest.TestCase):
    def test_roundtrip_with_c(self):
        block = tb.build_tag_block([("s", "GP0001"), ("c", "1558090544462")])
        self.assertEqual(tb.parse_tag_block(block), [("s", "GP0001"), ("c", "1558090544462")])

    def test_g_must_be_first(self):
        with self.assertRaises(ValueError):
            tb.build_tag_block([("s", "IN0001"), ("g", "1-2-3")])

    def test_rejects_bad_sfi(self):
        for bad in ("GNSS01", "GP001", "gp0001", "GP00011"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tb.build_tag_block([("s", bad)])

    def test_rejects_reserved_chars_in_value(self):
        for bad in ("a,b", "a*b", "a\\b", "a$b", "a!b"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tb.build_tag_block([("t", bad)])

    def test_rejects_long_block(self):
        with self.assertRaises(ValueError):
            tb.build_tag_block([("t", "x" * 80)])

    def test_n_range(self):
        tb.build_tag_block([("n", "999")])
        for bad in ("0", "1000", "-1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tb.build_tag_block([("n", bad)])

    def test_g_range(self):
        for bad in ("3-2-1", "0-2-1", "1-2-100", "1-2", "a-b-c"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tb.build_tag_block([("g", bad)])

    def test_empty_params(self):
        with self.assertRaises(ValueError):
            tb.build_tag_block([])

    def test_sfi_helper(self):
        self.assertEqual(tb.sfi("GP", 1), "GP0001")
        with self.assertRaises(ValueError):
            tb.sfi("GP", 9999)

    def test_g_helper(self):
        self.assertEqual(tb.g_value(1, 2, 34), "1-2-34")

    def test_posix_ms(self):
        self.assertEqual(tb.posix_ms(1558090544.462), "1558090544462")


class ParseTests(unittest.TestCase):
    def test_bad_checksum(self):
        with self.assertRaises(ValueError):
            tb.parse_tag_block("\\s:IN0001*00\\")

    def test_missing_delimiters(self):
        for bad in ("s:IN0001*3A", "\\s:IN0001*3A", "s:IN0001*3A\\"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tb.parse_tag_block(bad)

    def test_malformed_pair(self):
        content = "s"
        block = f"\\{content}*{tb.checksum(content):02X}\\"
        with self.assertRaises(ValueError):
            tb.parse_tag_block(block)


class LineTests(unittest.TestCase):
    def test_compose_and_split(self):
        sentence = nmea.build_sentence("GP", "GLL", ["5057.970", "N", "00146.110", "E", "142451", "A"])
        b1 = tb.build_tag_block([("s", "GP0001")])
        b2 = tb.build_tag_block([("s", "AB0001")])
        line = tb.compose_line([b1, b2], sentence)
        blocks, rest = tb.split_line(line)
        self.assertEqual(blocks, [b1, b2])
        self.assertEqual(rest, sentence)

    def test_standard_multi_s_example(self):
        # From 7.2.3.1: two stacked 's' blocks on a GLL sentence.
        b1 = tb.build_tag_block([("s", "GP0001")])
        b2 = tb.build_tag_block([("s", "AB0001")])
        line = b1 + b2 + "$GPGLL,5057.970,N,00146.110,E,142451,A*27\r\n"
        blocks, _ = tb.split_line(line)
        self.assertEqual([tb.parse_tag_block(b)[0][1] for b in blocks], ["GP0001", "AB0001"])

    def test_unterminated(self):
        with self.assertRaises(ValueError):
            tb.split_line("\\s:GP0001*00$GPGLL")

    def test_compose_requires_sentence(self):
        with self.assertRaises(ValueError):
            tb.compose_line(["\\s:GP0001*00\\"], "GPGLL")


if __name__ == "__main__":
    unittest.main()
