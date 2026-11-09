#!/usr/bin/env python3
"""Join a multicast group and parse IEC 61162-450 'UdPbC' datagrams.

Valid datagrams are printed line by line. Invalid datagrams are discarded as a
whole (IEC 61162-450:2024 clause 7.2.4) and counted by reason.
"""

import argparse
import collections
import socket
import struct

import datagram


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interface", required=True, help="Local IPv4 address that joins the group")
    p.add_argument("--group", default="239.192.0.4", help="Multicast group (default: NAVD)")
    p.add_argument("--port", type=int, default=60004, help="UDP port (default: 60004)")
    return p.parse_args()


def main():
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("Error: --port must be between 1 and 65535")
    try:
        group_bytes = socket.inet_aton(args.group)
        interface_bytes = socket.inet_aton(args.interface)
    except OSError as exc:
        raise SystemExit(f"Invalid IPv4 address: {exc}")
    if not 224 <= group_bytes[0] <= 239:
        raise SystemExit(f"{args.group} is not an IPv4 multicast address")

    membership = struct.pack("4s4s", group_bytes, interface_bytes)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    joined = False
    ok = 0
    discarded = collections.Counter()
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to the group address (not 0.0.0.0) so only this group's traffic
        # reaches the socket, even if the host has joined other groups on this port.
        sock.bind((args.group, args.port))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        joined = True
        print(f"Joined {args.group} on {args.interface}; listening on UDP {args.port}. Ctrl+C to stop.")

        while True:
            data, sender = sock.recvfrom(65535)
            try:
                lines = datagram.parse_datagram(data)
            except datagram.DatagramError as exc:
                discarded[exc.kind] += 1
                print(f"{sender[0]}:{sender[1]} DISCARDED ({exc}) [{len(data)} bytes]")
                continue
            ok += 1
            for ln in lines:
                n = dict(ln.tag_params).get("n", "-")
                c = dict(ln.tag_params).get("c", "-")
                print(f"{sender[0]}:{sender[1]} src={ln.source} n={n} c={c} "
                      f"{ln.talker}{ln.formatter} {','.join(ln.fields)}")
    except KeyboardInterrupt:
        print(f"\nReceiver stopping. valid datagrams={ok} discarded={dict(discarded) or 0}")
    finally:
        if joined:
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, membership)
            except OSError:
                pass
        sock.close()


if __name__ == "__main__":
    main()
