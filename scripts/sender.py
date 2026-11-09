#!/usr/bin/env python3
"""Send periodic UDP datagrams to an IPv4 multicast group."""

import argparse
import socket
import time


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="239.1.1.1", help="IPv4 multicast group")
    parser.add_argument("--port", type=int, default=5000, help="UDP destination port")
    parser.add_argument(
        "--interface",
        required=True,
        help="Local IPv4 address of the interface used to send multicast",
    )
    parser.add_argument("--ttl", type=int, default=1, help="Multicast TTL (default: 1)")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between packets")
    return parser.parse_args()


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
    except OSError as exc:
        raise SystemExit(f"Invalid IPv4 address: {exc}")

    # 224.0.0.0/4 is the IPv4 multicast address block.
    group_first_octet = group_bytes[0]
    if not 224 <= group_first_octet <= 239:
        raise SystemExit(f"{args.group} is not an IPv4 multicast address")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    # Choose the local interface used for outgoing multicast packets.
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface_bytes)

    # Limit how many router hops the multicast packet may traverse.
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, args.ttl)

    print(
        f"Sending to {args.group}:{args.port} via {args.interface} "
        f"(TTL={args.ttl}, interval={args.interval}s). Press Ctrl+C to stop."
    )

    counter = 0
    try:
        while True:
            message = f"IGMP DEMO | Multicast packet #{counter}"
            sock.sendto(message.encode("utf-8"), (args.group, args.port))
            print(f"Sent: {message}")
            counter += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSender stopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
