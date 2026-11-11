"""Integration test: real sockets, real kernel, this host's Ethernet interface.

Skipped automatically unless 192.168.1.10 and 192.168.1.11 are assigned to a
wired interface that has carrier. It proves what the kernel delivered:
the IP source address of each datagram, its TTL, and the arrival interface.
It does NOT prove anything about the switch; the traffic is looped back
locally on the sending host.
"""

import os
import socket
import struct
import subprocess
import sys
import time
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from lab.multicast import interface  # noqa: E402
from lab.nmea.checksum import parse_sentence  # noqa: E402

SRC_A, SRC_B = "192.168.1.10", "192.168.1.11"
GROUP, PORT = "239.1.1.4", 50555  # private test port, not the lab's 5000
IP_PKTINFO = 8
IP_RECVTTL = 12  # Linux value; not exposed by Python's socket module


def _usable():
    try:
        return (interface.require_ethernet_address(SRC_A) ==
                interface.require_ethernet_address(SRC_B))
    except interface.InterfaceError:
        return False


@unittest.skipUnless(_usable(), "192.168.1.10/.11 not assigned to a wired interface with carrier")
class TwoSourcesOneGroup(unittest.TestCase):
    def setUp(self):
        self.ifname = interface.require_ethernet_address(SRC_A)
        self.ifindex = socket.if_nametoindex(self.ifname)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.IPPROTO_IP, IP_RECVTTL, 1)
        s.setsockopt(socket.IPPROTO_IP, IP_PKTINFO, 1)
        s.bind((GROUP, PORT))
        mreq = struct.pack("4s4s", socket.inet_aton(GROUP), socket.inet_aton(SRC_A))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.settimeout(0.5)
        self.sock = s

    def tearDown(self):
        self.sock.close()

    def _run_senders(self, *names):
        procs = [subprocess.Popen(
            [sys.executable, "-m", "lab.multicast.sender", n, "--group", GROUP, "--port", str(PORT),
             "--count", "10", "--interval", "0.1", "--quiet"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for n in names]
        received = []
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            try:
                data, anc, _, addr = self.sock.recvmsg(2048, 256)
            except socket.timeout:
                if all(p.poll() is not None for p in procs):
                    break
                continue
            ttl = ifindex = None
            for level, kind, payload in anc:
                if level == socket.IPPROTO_IP and kind == socket.IP_TTL:
                    ttl = struct.unpack("i", payload[:4])[0]
                elif level == socket.IPPROTO_IP and kind == IP_PKTINFO:
                    ifindex = struct.unpack("iII", payload[:12])[0]
            received.append((addr[0], data.decode("ascii"), ttl, ifindex))
        outputs = [p.communicate(timeout=5)[0] for p in procs]
        for p, out in zip(procs, outputs):
            self.assertEqual(p.returncode, 0, out)
        return received

    def test_two_distinct_sources_reach_one_group(self):
        got = self._run_senders("gnss1", "gnss2")
        sources = {src for src, *_ in got}
        self.assertEqual(sources, {SRC_A, SRC_B}, f"saw sources {sources}")

    def test_payload_talker_matches_source_ip(self):
        got = self._run_senders("gnss1", "gnss2")
        for src, text, *_ in got:
            talker, _, _ = parse_sentence(text)  # also validates the checksum
            self.assertEqual(talker, {SRC_A: "GP", SRC_B: "GN"}[src])

    def test_ttl_is_one(self):
        got = self._run_senders("gnss1")
        self.assertTrue(got)
        self.assertEqual({ttl for _, _, ttl, _ in got}, {1})

    def test_arrival_interface_is_the_wired_one(self):
        got = self._run_senders("gnss1", "gnss2")
        self.assertTrue(got)
        self.assertEqual({idx for *_, idx in got}, {self.ifindex}, f"expected ifindex {self.ifindex} ({self.ifname})")

    def test_two_senders_sharing_one_ip(self):
        got = self._run_senders("gnss1", "gyro1")  # both use 192.168.1.10
        self.assertEqual({src for src, *_ in got}, {SRC_A})
        talkers = {parse_sentence(text)[0] for _, text, *_ in got}
        self.assertEqual(talkers, {"GP", "HE"})


if __name__ == "__main__":
    unittest.main()
