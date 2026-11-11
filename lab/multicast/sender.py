"""Simulated navigation equipment sending NMEA 0183 over UDP multicast.

Usage (from the repository root):

    python3 -m lab.multicast.sender gnss1
    python3 -m lab.multicast.sender gnss2 --group combined --interval 0.5
    python3 -m lab.multicast.sender gnss1 --group 239.1.1.4 --port 5000 --count 20

Each datagram carries exactly one NMEA sentence (plain IEC 61162-1 style,
not the IEC 61162-450 'UdPbC' framing used by scripts/nmea_sender.py).

The socket is bound to the sender's configured source IP, the outgoing
interface is selected explicitly with IP_MULTICAST_IF, and the multicast TTL
is 1. Nothing is left to automatic interface selection.
"""

import argparse
import signal
import socket
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone

from .. import config as cfgmod
from ..nmea import generator
from . import interface


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m lab.multicast.sender",
                                description="Send simulated NMEA 0183 data to a multicast group.")
    p.add_argument("name", help="sender name from config/senders.toml (e.g. gnss1)")
    p.add_argument("--group", help="group name from groups.toml or a multicast IP (default: from config)")
    p.add_argument("--port", type=int, help="UDP destination port (default: from the group)")
    p.add_argument("--interval", type=float, help="seconds between sentences, for every kind")
    p.add_argument("--count", type=int, default=0, help="stop after N datagrams (0 = run until stopped)")
    p.add_argument("--no-loop", action="store_true",
                   help="disable IP_MULTICAST_LOOP so same-host receivers do not see our traffic")
    p.add_argument("--quiet", action="store_true", help="log only start and summary")
    p.add_argument("--config-dir", default=str(cfgmod.DEFAULT_CONFIG_DIR), help="configuration directory")
    return p.parse_args(argv)


def stamp(now=None):
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def make_socket(source_ip: str, ttl: int = 1, loop: bool = True) -> socket.socket:
    """UDP socket bound to `source_ip`, sending multicast out of that address's interface."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.bind((source_ip, 0))  # fixes the IP source address of every datagram
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1 if loop else 0)
    except OSError:
        sock.close()
        raise
    return sock


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        groups = cfgmod.load_groups(args.config_dir)
        senders = cfgmod.load_senders(args.config_dir, groups)
        vessel = cfgmod.load_vessel(args.config_dir)
        if args.name not in senders:
            raise cfgmod.ConfigError(f"unknown sender {args.name!r}; defined: {sorted(senders)}")
        sc = senders[args.name]
        group = cfgmod.resolve_group(args.group or sc.group, groups)
        port = args.port or group.port
        if not 1 <= port <= 65535:
            raise cfgmod.ConfigError("--port must be between 1 and 65535")
        interval = args.interval if args.interval is not None else sc.interval
        if interval <= 0:
            raise cfgmod.ConfigError("--interval must be greater than zero")
        ifname = interface.require_ethernet_address(sc.source_ip)
        sock = make_socket(sc.source_ip, ttl=1, loop=not args.no_loop)
    except (cfgmod.ConfigError, interface.InterfaceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    source = cfgmod.build_source(sc, vessel)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    dest = (group.ip, port)
    print(f"{stamp()} {sc.name} START talker={sc.talker} source={sc.source_ip} ({ifname}, wired) "
          f"-> {group.ip}:{port} group={group.name} ttl=1 loop={'off' if args.no_loop else 'on'} "
          f"interval={interval}s kinds={','.join(sc.kinds)}", flush=True)

    sent = Counter()
    total = 0
    start = time.monotonic()
    due = {kind: start for kind in sc.kinds}
    try:
        while not stop.is_set():
            now = time.monotonic()
            for kind in sc.kinds:
                if due[kind] > now:
                    continue
                when = datetime.now(timezone.utc)
                sentence = generator.sentences(source, when, [kind])[0]
                status = "ok"
                try:
                    sock.sendto(sentence.encode("ascii"), dest)
                except OSError as exc:
                    status = f"FAILED({exc})"
                else:
                    sent[kind] += 1
                    total += 1
                if not args.quiet or status != "ok":
                    print(f"{stamp(when)} {sc.name} TX {sc.source_ip} -> {group.ip}:{port} "
                          f"{sc.talker}{kind} #{total} {status}", flush=True)
                due[kind] = max(due[kind] + interval, now)
                if args.count and total >= args.count:
                    stop.set()
                    break
            if stop.is_set():
                break
            stop.wait(max(0.0, min(due.values()) - time.monotonic()))
    finally:
        sock.close()
        elapsed = max(time.monotonic() - start, 1e-9)
        by_kind = " ".join(f"{k}={n}" for k, n in sorted(sent.items()))
        print(f"{stamp()} {sc.name} STOP sent={total} rate={total / elapsed:.1f}/s {by_kind}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
