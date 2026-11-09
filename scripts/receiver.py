#!/usr/bin/env python3
"""Join an IPv4 multicast group and print received UDP datagrams."""

import argparse
import socket
import struct


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="239.1.1.1", help="IPv4 multicast group")
    parser.add_argument("--port", type=int, default=5000, help="UDP port to listen on")
    parser.add_argument(
        "--interface",
        required=True,
        help="Local IPv4 address of the interface that joins the multicast group",
    )
    return parser.parse_args()


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

    # ip_mreq = { struct in_addr imr_multiaddr; struct in_addr imr_interface; }
    # Each IPv4 address occupies four bytes, giving an eight-byte membership request.
    membership = struct.pack("4s4s", group_bytes, interface_bytes)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    joined = False

    try:
        # Common multicast receiver setup: allow compatible local socket reuse.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Listen on the requested UDP port on all local IPv4 interfaces.
        sock.bind(("", args.port))

        # Ask the kernel to join this group on the specified local interface.
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        joined = True

        print(
            f"Joined multicast group {args.group} on {args.interface}; "
            f"listening on UDP port {args.port}. Press Ctrl+C to stop."
        )

        while True:
            data, sender = sock.recvfrom(4096)
            message = data.decode("utf-8", errors="replace")
            print(f"{sender[0]}:{sender[1]} -> {args.group}:{args.port} | {message}")

    except KeyboardInterrupt:
        print("\nReceiver stopping.")
    finally:
        # Explicitly drop membership before closing the socket.
        if joined:
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, membership)
            except OSError:
                pass
        sock.close()


if __name__ == "__main__":
    main()
