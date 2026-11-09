# IGMP + UDP Multicast Demo

A small, reproducible two-computer lab that demonstrates **IPv4 multicast group membership (IGMP)** and **UDP multicast data delivery** on a local network.

The project contains:
- a Python UDP multicast sender;
- a Python UDP multicast receiver;
- setup instructions for two Linux computers;
- Wireshark capture filters and a guided experiment;
- troubleshooting notes and a protocol explanation.

> This is a learning/demo project, not a production messaging system. UDP multicast does not guarantee delivery, ordering, retransmission, or authentication.

## 1. What you will build

Example lab values (replace these with the addresses on your own LAN):

| Item | Computer A | Computer B |
|---|---:|---:|
| Role | Sender | Receiver |
| LAN IPv4 address | `192.168.1.10` | `192.168.1.15` |
| UDP destination port | `5000` | `5000` |
| Multicast group | `239.1.1.1` | `239.1.1.1` |

The sender sends UDP datagrams to `239.1.1.1:5000`. The receiver joins multicast group `239.1.1.1` on its chosen local interface and listens on UDP port `5000`.

```text
 Computer A                                  Computer B
 192.168.1.10                                192.168.1.15
 +----------------+                          +----------------+
 | sender.py      | -- UDP to 239.1.1.1:5000 | receiver.py    |
 |                | =======================> | joins group    |
 +----------------+       LAN / switch       +----------------+
                               |
                     IGMP membership signalling
                     (host <-> multicast router;
                      possibly observed by snooping switch)
```

**Important:** `239.1.1.1` is a multicast destination, not the receiver's unicast address. The sender does not need to know each receiver's IP address.

## 2. Requirements

- Two computers connected to the same LAN/subnet for the simplest lab.
- Linux is the documented target (Ubuntu, Debian, Fedora, etc.).
- Python 3.8+.
- Wireshark is optional but strongly recommended.
- Both computers must be allowed to exchange local UDP traffic. Guest Wi-Fi, client/AP isolation, VLAN separation, or firewall rules may block the demo.

No third-party Python packages are required.

## 3. Find each computer's interface and IPv4 address

On **Computer A** and **Computer B**, run:

```bash
ip -br -4 addr
ip route
```

Example output might show:
- Computer A: `192.168.1.10/24` on `enp3s0`
- Computer B: `192.168.1.15/24` on `enp3s0`

Your interface might instead be named `wlp2s0`, `eno1`, `eth0`, etc.

To see which interface Linux would use to reach the other computer:

```bash
ip route get 192.168.1.15   # run on A, substitute B's address
```

Use the actual IPv4 address assigned to the LAN interface. Do not blindly copy the example addresses in this guide.

## 4. Get the project and configure it

Copy/clone this repository onto both computers. Then open a terminal in the project directory.

The scripts accept command-line arguments, so you can use the same code on both machines without editing source files.

### Computer A — sender

```bash
python3 scripts/sender.py --interface 192.168.1.10
```

Replace `192.168.1.10` with Computer A's actual LAN IPv4 address.

### Computer B — receiver

```bash
python3 scripts/receiver.py --interface 192.168.1.15
```

Replace `192.168.1.15` with Computer B's actual LAN IPv4 address.

Start the receiver first, then start the sender. You should see a message arrive approximately once per second.

To stop either program, press `Ctrl+C`.

### Optional: change group, port, interval, or TTL

```bash
python3 scripts/sender.py \
  --interface 192.168.1.10 \
  --group 239.1.1.1 \
  --port 5000 \
  --interval 1 \
  --ttl 1
```

```bash
python3 scripts/receiver.py \
  --interface 192.168.1.15 \
  --group 239.1.1.1 \
  --port 5000
```

The sender's `--interface` selects the outgoing interface. The receiver's `--interface` identifies the local interface on which it joins the group.

## 5. Run both programs on one computer (quick smoke test)

You can test the Python programs on one Linux machine before using two computers.

Find a local IPv4 address:

```bash
ip -br -4 addr
```

Open two terminals.

Terminal 1:

```bash
python3 scripts/receiver.py --interface 192.168.1.10
```

Terminal 2:

```bash
python3 scripts/sender.py --interface 192.168.1.10
```

Replace the address with an address actually assigned to that machine. A loopback-only setup may need different interface handling; this project's defaults are intended for a real LAN interface.

## 6. What is multicast?

IP multicast is a one-to-many (more precisely, one-to-many interested receivers) delivery model.

- **Unicast:** one sender addresses one receiver.
- **Broadcast:** one sender addresses all hosts on a broadcast domain (IPv4 broadcast).
- **Multicast:** one sender addresses a multicast group; hosts that join the group can receive the traffic.

IPv4 multicast addresses occupy `224.0.0.0/4` (`224.0.0.0` through `239.255.255.255`). The `239.0.0.0/8` block is administratively scoped and is commonly used for private/local multicast deployments. `239.1.1.1` is an example group chosen for this lab.

A multicast group is an IP destination representing a receiver group. It is not a machine, and it is not a UDP port. The UDP port identifies the receiving application/socket on a host.

## 7. What is IGMP?

**Internet Group Management Protocol (IGMP)** is an IPv4 control protocol used by hosts and multicast routers on a local network to manage multicast group membership.

In this demo:
1. The receiver asks the operating system to join `239.1.1.1` on a local interface.
2. The operating system records the membership and uses IGMP to signal interest as required by the IGMP version and network state.
3. A multicast router can use membership information to decide where multicast traffic is needed.
4. An Ethernet switch with **IGMP snooping** can inspect IGMP messages and limit multicast forwarding to ports with interested receivers.

IGMP is **not** carrying the demo text messages. Those messages are UDP payloads inside IP multicast packets.

### Keep these roles separate

| Technology | Job in this demo |
|---|---|
| UDP | Carries the application's message and destination port |
| IPv4 multicast | Addresses the packet to group `239.1.1.1` |
| IGMP | Signals/manages IPv4 multicast group membership |
| IGMP snooping | Optional switch feature that observes IGMP to manage Layer-2 forwarding |
| Ethernet | Carries the frame across the local network |

IGMP is commonly described as an IP-layer control protocol (IP protocol number 2); it is not TCP or UDP and has no UDP port.

## 8. Code walkthrough

### Sender (`scripts/sender.py`)

1. Creates an IPv4 datagram socket using `AF_INET`, `SOCK_DGRAM`, and `IPPROTO_UDP`.
2. Sets `IP_MULTICAST_IF` so the kernel sends multicast packets through the selected local interface.
3. Sets `IP_MULTICAST_TTL`. A TTL of `1` prevents a multicast packet from being forwarded by a router that decrements TTL from 1 to 0. It is a hop limit, not a universal security boundary.
4. Repeatedly encodes a text message to bytes and calls `sendto((group, port))`.
5. Sleeps for the configured interval.

### Receiver (`scripts/receiver.py`)

1. Creates an IPv4 UDP datagram socket.
2. Enables `SO_REUSEADDR`, commonly used for multicast receiver sockets and address reuse.
3. Binds to `0.0.0.0:5000` (all local IPv4 interfaces, UDP port 5000).
4. Packs the multicast group address and local interface address into the `ip_mreq` binary structure expected by `IP_ADD_MEMBERSHIP`.
5. Calls `IP_ADD_MEMBERSHIP` to ask the kernel to join the group on that interface.
6. Calls `recvfrom()` to receive datagrams, decode their payload, and display the sender's source address.
7. On Ctrl+C, requests `IP_DROP_MEMBERSHIP` and closes the socket.

**Why `struct.pack("4s4s", ...)`?** The traditional IPv4 `ip_mreq` structure contains two four-byte IPv4 addresses: the multicast group (`imr_multiaddr`) and the local interface (`imr_interface`). `inet_aton()` converts dotted-decimal IPv4 text into four packed bytes; `struct.pack()` combines the two fields into the eight-byte structure expected by this socket option on common Linux systems.

## 9. Observe it in Wireshark

Install Wireshark on one or both computers. Capture on the interface carrying the traffic (for example, `enp3s0` or `wlp2s0`).

Useful display filter:

```wireshark
igmp || (ip.dst == 239.1.1.1 && udp.dstport == 5000)
```

To isolate only the UDP application packets:

```wireshark
ip.dst == 239.1.1.1 && udp.dstport == 5000
```

To isolate IGMP:

```wireshark
igmp
```

Inspect a UDP packet:
- Ethernet II: destination MAC is typically an IPv4 multicast-mapped Ethernet MAC.
- IPv4: destination should be `239.1.1.1`; TTL should be `1`.
- UDP: destination port should be `5000`.
- Data: payload should contain `IGMP DEMO | Multicast packet #...`.

Inspect IGMP packets:
- You may see Membership Reports and Membership Queries.
- You may not see a fresh report every time the receiver starts: IGMP uses timers, queries, report suppression, and version-dependent behavior.
- A Leave Group message is not guaranteed to appear in every scenario/version; membership expiry and querier behavior matter.

**Capture point matters:** a sender capture shows outgoing packets; a receiver capture shows packets delivered to that host. A third computer on a switched network may not see unicast-like copies of multicast traffic unless the switch forwards them to that port, the network floods them, or port mirroring is configured.

## 10. Experiments

Run these experiments and record what you observe.

### Experiment A — normal operation
1. Start the receiver.
2. Start the sender.
3. Confirm that the receiver prints increasing packet numbers.
4. In Wireshark, identify the UDP destination address, destination port, source address, TTL, and payload.

Expected: the receiver gets approximately one packet per second.

### Experiment B — sender without a receiver
1. Stop the receiver.
2. Keep the sender running.
3. Observe that the sender continues transmitting.

Expected: UDP multicast sending does not require a receiver to be present. UDP has no receiver acknowledgement.

### Experiment C — receiver joins later
1. Keep the sender running.
2. Start the receiver again.

Expected: it begins receiving packets after joining. It does not receive old packets sent before it joined.

### Experiment D — two receivers
1. Start receivers on two different computers, each using its own local interface IP.
2. Start one sender.

Expected: both receivers can receive the same multicast datagrams if the network permits multicast forwarding.

### Experiment E — leave the group
1. Stop the receiver with Ctrl+C.
2. Observe the receiver's cleanup and, where visible, IGMP membership changes.
3. Keep in mind that IGMP reports/leaves depend on IGMP version and querier/network behavior.

## 11. Troubleshooting

### Sender prints messages, receiver gets nothing
Check:
- Sender `--interface` is the sender's actual LAN IP.
- Receiver `--interface` is the receiver's actual LAN IP.
- Both use exactly the same group and UDP port.
- Both computers are on a network that permits multicast between them.
- The receiver is started before testing.
- Host firewall rules allow UDP port 5000 and relevant local multicast traffic.
- Wi-Fi client isolation / guest network isolation is disabled.
- VLANs and routers are not blocking multicast.

### Verify basic unicast connectivity

From A:

```bash
ping 192.168.1.15
```

A successful ping is useful, but it does **not** prove multicast works.

### Check interface multicast capability / memberships

```bash
ip link show
ip maddr show
```

`ip maddr show` lists link-layer multicast addresses and IP multicast memberships known to the interface. Output can include automatically joined groups as well as the group used by this demo.

### Firewall

Firewall configuration differs by distribution and environment. For a temporary lab test, inspect the active firewall before changing it:

```bash
sudo ufw status
sudo firewall-cmd --state
sudo nft list ruleset
```

Do not disable the firewall permanently. If a rule is needed, add a narrow rule appropriate to your firewall and remove it after the lab.

### Wi-Fi caveats

Some access points isolate wireless clients or handle multicast specially (including multicast-to-unicast conversion, rate limiting, or filtering). Two computers connected to the same SSID are not necessarily allowed to exchange multicast traffic.

### No IGMP packets visible

- Start the capture before the receiver joins.
- Capture on the receiver's actual network interface.
- Check whether the receiver is already a member.
- Remember that IGMP reports are timer-driven and may not be emitted for every join in an obvious way.
- Verify that the application actually joined successfully (the receiver prints a joined message only after `setsockopt` succeeds).

## 12. Limitations and safety

- UDP is best-effort: packets may be lost, duplicated, or reordered.
- This demo has no retransmission, authentication, encryption, or congestion control.
- Multicast routing between subnets is not configured by this project.
- TTL 1 is a hop limit, not a substitute for network security policy.
- Do not use this demo to send sensitive data.
- Run it only on networks where you have permission to generate and capture traffic.

## 13. Further reading

- RFC 1112 — Host Extensions for IP Multicasting.
- RFC 2236 — Internet Group Management Protocol, Version 2.
- RFC 3376 — Internet Group Management Protocol, Version 3.
- Wireshark display filter reference: `igmp`.

---

## Quick-start summary

**Computer B (receiver):**
```bash
python3 scripts/receiver.py --interface <COMPUTER_B_LAN_IP>
```

**Computer A (sender):**
```bash
python3 scripts/sender.py --interface <COMPUTER_A_LAN_IP>
```

**Wireshark:**
```wireshark
igmp || (ip.dst == 239.1.1.1 && udp.dstport == 5000)
```
