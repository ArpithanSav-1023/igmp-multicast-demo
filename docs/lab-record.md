# IGMP Multicast Lab Record

Use this page to document a run of the lab.

## Environment

- Date/time:
- Sender OS / version:
- Receiver OS / version:
- Sender interface and IPv4:
- Receiver interface and IPv4:
- Switch / access point:
- Firewall state:
- Wireshark version:

## Configuration

- Multicast group: `239.1.1.1`
- UDP port: `5000`
- Sender TTL: `1`
- Sender interval: `1` second

## Observations

| Test | Expected | Actual observation |
|---|---|---|
| Receiver joins group | Kernel membership created; IGMP signalling as applicable | |
| Sender transmits | UDP packets to multicast group | |
| Receiver receives | Payload and sender source address displayed | |
| Receiver stops | Membership dropped locally; network state updates as applicable | |
| Two receivers join | Both can receive if network forwards multicast | |

## Packet inspection

- IGMP version/type observed:
- Source IPv4:
- Destination IPv4:
- UDP source port:
- UDP destination port:
- IPv4 TTL:
- Payload:
- Ethernet destination MAC:

## Findings / issues

Record packet loss, unexpected behavior, network limitations, and fixes here.
