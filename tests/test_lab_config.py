import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lab import config as c  # noqa: E402


def write(directory, groups=None, senders=None):
    d = Path(directory)
    if groups is not None:
        (d / "groups.toml").write_text(groups)
    if senders is not None:
        (d / "senders.toml").write_text(senders)
    return d


GOOD_GROUPS = '[groups.a]\nip = "239.1.1.1"\nport = 5000\n[groups.b]\nip = "239.1.1.4"\n'
GOOD_SENDER = '''
[senders.s1]
equipment = "gnss"
talker = "GP"
source_ip = "192.168.1.10"
group = "a"
interval = 1.0
kinds = ["GGA", "rmc"]
'''


class RealConfig(unittest.TestCase):
    def test_shipped_config_loads_and_is_consistent(self):
        groups = c.load_groups()
        senders = c.load_senders(groups=groups)
        c.load_vessel()
        self.assertEqual({g.ip for g in groups.values()},
                         {"239.1.1.1", "239.1.1.2", "239.1.1.3", "239.1.1.4", "239.1.1.5"})
        self.assertEqual(set(senders), {"gnss1", "gnss2", "gyro1", "log1"})
        # Two senders share one IP; two distinct IPs exist for SSM tests.
        self.assertEqual(senders["gnss1"].source_ip, senders["gyro1"].source_ip)
        self.assertNotEqual(senders["gnss1"].source_ip, senders["gnss2"].source_ip)

    def test_build_source_for_every_sender(self):
        vessel = c.load_vessel()
        for cfg in c.load_senders().values():
            self.assertEqual(c.build_source(cfg, vessel).kind, cfg.equipment)


class Validation(unittest.TestCase):
    def check(self, groups=GOOD_GROUPS, senders=GOOD_SENDER, fn="senders"):
        with tempfile.TemporaryDirectory() as d:
            write(d, groups, senders)
            if fn == "groups":
                return c.load_groups(d)
            return c.load_senders(d)

    def test_good(self):
        s = self.check()["s1"]
        self.assertEqual(s.kinds, ("GGA", "RMC"))  # normalised to upper case

    def test_non_multicast_group(self):
        with self.assertRaises(c.ConfigError):
            self.check(groups='[groups.a]\nip = "192.168.1.5"\n', fn="groups")

    def test_duplicate_group_ip(self):
        with self.assertRaises(c.ConfigError):
            self.check(groups='[groups.a]\nip = "239.1.1.1"\n[groups.b]\nip = "239.1.1.1"\n', fn="groups")

    def test_bad_port(self):
        for port in (0, 70000, "5000"):
            with self.subTest(port=port), self.assertRaises(c.ConfigError):
                self.check(groups=f'[groups.a]\nip = "239.1.1.1"\nport = {port!r}\n'.replace("'", '"'), fn="groups")

    def test_unknown_group_in_sender(self):
        with self.assertRaises(c.ConfigError):
            self.check(senders=GOOD_SENDER.replace('group = "a"', 'group = "zzz"'))

    def test_bad_equipment_kind_and_interval(self):
        for bad in (GOOD_SENDER.replace('"gnss"', '"radar"'),
                    GOOD_SENDER.replace('["GGA", "rmc"]', '["HDT"]'),
                    GOOD_SENDER.replace("interval = 1.0", "interval = 0"),
                    GOOD_SENDER.replace('talker = "GP"', 'talker = "gp"'),
                    GOOD_SENDER.replace("192.168.1.10", "not-an-ip")):
            with self.subTest(bad=bad), self.assertRaises(c.ConfigError):
                self.check(senders=bad)

    def test_missing_file_and_bad_toml(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(c.ConfigError):
                c.load_groups(d)
            write(d, groups="[groups\n")
            with self.assertRaises(c.ConfigError):
                c.load_groups(d)

    def test_vessel_unknown_key(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, senders="[vessel]\nbogus = 1\n")
            with self.assertRaises(c.ConfigError):
                c.load_vessel(d)


class ResolveGroup(unittest.TestCase):
    def setUp(self):
        self.groups = c.load_groups()

    def test_by_name_and_ip(self):
        self.assertEqual(c.resolve_group("combined", self.groups).ip, "239.1.1.4")
        self.assertEqual(c.resolve_group("239.1.1.4", self.groups).name, "combined")

    def test_unconfigured_multicast_ip_uses_default_port(self):
        g = c.resolve_group("239.9.9.9", self.groups, default_port=6000)
        self.assertEqual((g.ip, g.port), ("239.9.9.9", 6000))

    def test_rejects_unicast_and_garbage(self):
        for bad in ("192.168.1.10", "nope"):
            with self.subTest(bad=bad), self.assertRaises(c.ConfigError):
                c.resolve_group(bad, self.groups)


if __name__ == "__main__":
    unittest.main()
