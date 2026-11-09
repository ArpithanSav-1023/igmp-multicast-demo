#!/usr/bin/env python3
"""Send simulated GNSS data as IEC 61162-450 'UdPbC' datagrams over UDP multicast.

Each datagram carries a GLL and a GGA sentence, each preceded by a TAG block
with the source SFI (s), a millisecond POSIX time (c) and a line counter (n).

Defaults use the NAVD transmission group from IEC 61162-450:2024 Table 4
(239.192.0.4, UDP 60004) and TTL 64 (the standard's default, 6.2.1 note 2).
"""

import argparse
import socket
import time
from datetime import datetime, timezone

import datagram
import nmea
import tagblock


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interface", required=True, help="Local IPv4 address used to send")
    p.add_argument("--group", default="239.192.0.4", help="Multicast group (default: NAVD)")
    p.add_argument("--port", type=int, default=60004, help="UDP destination port (default: 60004)")
    p.add_argument("--ttl", type=int, default=64, help="Multicast TTL (default: 64)")
    p.add_argument("--interval", type=float, default=1.0, help="Seconds between datagrams")
    p.add_argument("--talker", default="GP", help="Two-letter talker / SFI prefix (default: GP)")
    p.add_argument("--instance", type=int, default=1, help="SFI instance 1..9998 (default: 1)")
    p.add_argument("--count", type=int, default=0, help="Stop after N datagrams (0 = run forever)")
    return p.parse_args()


def main():
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("Error: --port must be between 1 and 65535")
    if not 0 <= args.ttl <= 255:
        raise SystemExit("Error: --ttl must be between 0 and 255")
    if args.interval <= 0:
        raise SystemExit("Error: --interval must be greater than zero")
    try:
        group_bytes = socket.inet_aton(args.group)
        interface_bytes = socket.inet_aton(args.interface)
        source = tagblock.sfi(args.talker, args.instance)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Error: {exc}")
    if not 224 <= group_bytes[0] <= 239:
        raise SystemExit(f"{args.group} is not an IPv4 multicast address")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface_bytes)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, args.ttl)

    print(f"Sending UdPbC datagrams from {source} to {args.group}:{args.port} via {args.interface} "
          f"(TTL={args.ttl}, interval={args.interval}s). Press Ctrl+C to stop.")

    # Slowly moving simulated position (degrees).
    lat, lon = 50.9662, 1.7685
    line_no = 1  # 'n' counter, 1..999 then wraps to 1 (7.2.3.6)
    sent = 0
    try:
        while True:
            now = datetime.now(timezone.utc)
            lines = []
            for sentence in (nmea.gll(lat, lon, now, args.talker),
                             nmea.gga(lat, lon, now, args.talker, altitude_m=12.3, geoid_sep_m=47.0)):
                block = tagblock.build_tag_block([
                    ("s", source),
                    ("c", tagblock.posix_ms(now.timestamp())),
                    ("n", line_no),
                ])
                lines.append(tagblock.compose_line(block, sentence))
                line_no = line_no % 999 + 1
            data = datagram.build_datagram(lines)
            sock.sendto(data, (args.group, args.port))
            sent += 1
            print(f"Sent #{sent} ({len(data)} bytes): {data[len(datagram.HEADER):].decode()!r}")
            lat += 0.00001
            lon += 0.00001
            if args.count and sent >= args.count:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSender stopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
