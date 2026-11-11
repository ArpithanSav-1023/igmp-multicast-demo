LAB RECORD v2

UDP Multicast, IGMP Membership, and Multi-Host Packet Analysis

Practical Linux networking laboratory

| Document field \| Value \|

| --- \| --- \|

| Document name \| lab_record_v2 \|

| Purpose \| Setup, implementation, verified observations, and next
  experiments \|

| Environment \| Two physical Linux laptops on the same IPv4 LAN \|

| Multicast endpoint \| 239.1.1.1:5000/UDP \|

| IGMP version observed \| IGMPv2 \|

| Status \| Phases 1--2 completed; receiver departure pending \|

| Evidence \| User-provided terminal output and Wireshark screenshots \|

## 1. Executive summary

This lab demonstrates IPv4 UDP multicast using two physical Linux
laptops. Laptop 2 runs three independent sender processes and a
receiver. Laptop 1 joins the same multicast group as a second receiver.
Wireshark is used to inspect UDP multicast data packets and IGMP control
messages.

Observed results establish that three sender sockets on Laptop 2 sent
UDP datagrams to 239.1.1.1:5000 and that Laptop 1 captured packets from
all three source ports. IGMPv2 membership reports for 239.1.1.1 were
observed from both host addresses during the experiment.

The next experiment is to stop Laptop 1's receiver and observe IGMP
behaviour, packet visibility at the interface, and whether Laptop 2's
receiver continues receiving.

## 2. Objectives

Distinguish unicast, broadcast, and multicast.

Send UDP datagrams to an IPv4 multicast group from multiple processes.

Join a multicast group from one or more receiving hosts.

Understand IGMP membership signalling and the role of an IGMP querier.

Use Wireshark filters to inspect UDP data and IGMP control packets.

Separate packet-capture evidence from assumptions about switch
forwarding and IGMP snooping.

## 3. Physical topology and addressing

| Component \| Observed value \| Role / notes \|

| --- \| --- \| --- \|

| Laptop 1 \| 192.168.1.15 \| Secondary receiver \|

| Laptop 1 interface \| enx207bd51e1472 \| Interface shown in
  `ip -br -4 addr` \|

| Laptop 2 \| 192.168.1.10 \| Three senders and primary receiver \|

| Laptop 2 interface \| enp3s0 \| Selected experiment interface \|

| Other Laptop 2 interface \| 192.168.1.22 on wlp0s20f3 \| Wireless
  interface; avoid selecting accidentally \|

| Querier candidate \| 192.168.1.254 \| Observed sending IGMPv2 General
  Membership Queries; identity unverified \|

| Group / port \| 239.1.1.1 / UDP 5000 \| Multicast destination \|

| Subnet \| 192.168.1.0/24 \| Shared LAN \|

Route checks: Laptop 1 ran `ip route get 192.168.1.79`, which selected
enx207bd51e1472 with source 192.168.1.15. Laptop 2 ran
`ip route get 192.168.1.15`, which selected enp3s0 with source
192.168.1.10.

## 4. Concepts

### 4.1 Unicast, broadcast, multicast

| Model \| Meaning \|

| --- \| --- \|

| Unicast \| One sender communicates with one destination host. \|

| Broadcast \| One sender targets all hosts in the local broadcast
  domain. \|

| Multicast \| A sender transmits to a group address; interested
  receivers join that group. \|

### 4.2 UDP data plane

The sender creates an IPv4 UDP socket, selects an outgoing interface,
sets multicast TTL, and sends datagrams to the group address and UDP
port. It does not need to know individual receiver addresses.

### 4.3 IGMP control plane

IGMP (Internet Group Management Protocol) allows IPv4 hosts and the
local multicast network to communicate group membership. A receiving
host requests membership through the operating-system socket API; the
kernel handles IGMP signalling. IGMP does not carry the demo's text
payloads: those are UDP datagrams.

### 4.4 Address and TTL notes

239.0.0.0/8 is the administratively scoped IPv4 multicast range; this
lab uses 239.1.1.1.

Multicast TTL 1 limits forwarding beyond the local network segment under
normal routing behaviour.

224.0.0.1 is the all-hosts multicast address commonly used as the
destination for general IGMP queries.

224.0.0.251 is commonly used by mDNS and is separate from this lab's
group.

## 5. Tools

| Tool \| Purpose \|

| --- \| --- \|

| Python 3 / socket \| Create UDP sender and receiver processes. \|

| Python struct \| Build the multicast membership request structure. \|

| Wireshark \| Capture and inspect UDP and IGMP packets. \|

| Linux iproute2 \| Inspect addresses and route/interface selection. \|

## 6. Application code

### 6.1 Original sender

import socket import time

GROUP = "239.1.1.1" PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
socket.IPPROTO_UDP) sock.setsockopt(socket.IPPROTO_IP,
socket.IP_MULTICAST_IF, socket.inet_aton("192.168.1.10"))
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

counter = 0 while True: message = f"IGMP DEMO \| Multicast packet
#{counter}" sock.sendto(message.encode(), (GROUP, PORT)) print(f"Sent:
{message}") counter += 1 time.sleep(1)

AF_INET selects IPv4; SOCK_DGRAM selects datagram sockets; IPPROTO_UDP
selects UDP. IP_MULTICAST_IF selects the outgoing interface using
192.168.1.10. IP_MULTICAST_TTL sets the packet TTL to 1. sendto()
transmits the encoded payload to the multicast group and UDP port.

### 6.2 Original receiver

import socket import struct

GROUP = "239.1.1.1" PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
socket.IPPROTO_UDP) sock.setsockopt(socket.SOL_SOCKET,
socket.SO_REUSEADDR, 1) sock.bind(("", PORT))

membership = struct.pack( "4s4s", socket.inet_aton(GROUP),
socket.inet_aton("192.168.1.15") ) sock.setsockopt(socket.IPPROTO_IP,
socket.IP_ADD_MEMBERSHIP, membership)

print(f"Listening for multicast on {GROUP}:{PORT}") while True: data,
address = sock.recvfrom(4096) print(f"{address}: {data.decode()}")

SO_REUSEADDR allows compatible local socket reuse. bind(('', PORT))
binds UDP port 5000 on local IPv4 interfaces. The membership structure
contains the multicast group and local interface address.
IP_ADD_MEMBERSHIP asks the kernel to join the group on that interface.
recvfrom() waits for datagrams and returns payload plus sender address.

The original snippets above are the initial examples. The working lab
scripts were invoked with command-line options such as --interface and
--interval. Inspect the repository's actual scripts before assuming
these snippets are byte-for-byte identical to the current files.

## 7. Reproduction procedure

### 7.1 Verify interfaces and routes

ip -br -4 addr ip route get 192.168.1.15 \# Laptop 2 ip route get
192.168.1.79 \# Laptop 1, if verifying Laptop 2 reachability

Confirm Laptop 1 uses 192.168.1.15 on enx207bd51e1472 and Laptop 2 uses
192.168.1.10 on enp3s0. Check the route output before running the demo.

### 7.2 Start processes on Laptop 2

| Terminal \| Process \| Command \|

| --- \| --- \| --- \|

| 1 \| Receiver 1 \| python3 scripts/receiver.py --interface
  192.168.1.10 \|

| 2 \| Sender 1 \| python3 scripts/sender.py --interface 192.168.1.10
  --interval 2 \|

| 3 \| Sender 2 \| python3 scripts/sender.py --interface 192.168.1.10
  --interval 3 \|

| 4 \| Sender 3 \| python3 scripts/sender.py --interface 192.168.1.10
  --interval 5 \|

### 7.3 Start receiver on Laptop 1

python3 scripts/receiver.py --interface 192.168.1.15

Keep each process in its own terminal. Different sender intervals make
the streams easier to distinguish.

## 8. Wireshark procedure

Start capture on the interface carrying the experiment traffic: enp3s0
on Laptop 2 and enx207bd51e1472 on Laptop 1. Enter display filters in
the display-filter bar at the top of the packet list, not in the
saved-filter management dialog.

| Purpose \| Display filter \|

| --- \| --- \|

| IGMP packets \| igmp \|

| UDP packets to the lab group and port \| ip.dst == 239.1.1.1 &&
  udp.dstport == 5000 \|

| Any IPv4 traffic involving the group \| ip.addr == 239.1.1.1 \|

| Laptop 2 to the group \| ip.src == 192.168.1.10 && ip.dst == 239.1.1.1
  \|

A display filter changes which captured packets are shown; it does not
alter traffic or join/leave a multicast group.

## 9. Completed experiments and observations

### 9.1 Phase 1 --- three senders and one receiver

| Observation \| Result / interpretation \|

| --- \| --- \|

| Three sender processes \| Three independent UDP source ports were
  visible, consistent with separate sender sockets. \|

| Destination \| All observed senders targeted 239.1.1.1:5000. \|

| IGMP \| An IGMPv2 membership report for 239.1.1.1 was observed. \|

| Queries \| General membership queries from 192.168.1.254 to 224.0.0.1
  were observed; .254 is a likely querier, not yet identified. \|

### 9.2 Phase 2 --- Laptop 1 joins as second receiver

| Packet field \| Observed value \|

| --- \| --- \|

| Source IP \| 192.168.1.10 \|

| Destination IP \| 239.1.1.1 \|

| UDP source ports \| 45218, 49687, 40623 \|

| UDP destination port \| 5000 \|

| Laptop 1 capture interface \| enx207bd51e1472 \|

Laptop 1's Wireshark capture showed UDP packets from 192.168.1.10 to
239.1.1.1:5000 with three distinct source ports. This is direct evidence
that Laptop 1's interface captured traffic from the three sender
sockets.

### 9.3 IGMP observations on Laptop 1

| Source \| Destination \| Observed message \| Interpretation \|

| --- \| --- \| --- \| --- \|

| 192.168.1.254 \| 224.0.0.1 \| IGMPv2 General Membership Query \|
  General query from likely querier. \|

| 192.168.1.15 \| 224.0.0.251 \| IGMPv2 Membership Report \| Separate
  group, commonly associated with mDNS. \|

| 192.168.1.15 \| 239.1.1.1 \| IGMPv2 Membership Report \| Laptop 1
  reported membership in the lab group. \|

## 10. Evidence boundaries

| Statement \| Status \|

| --- \| --- \|

| Three sender sockets transmitted to one group/port. \| Supported by
  distinct source ports and common destination. \|

| Laptop 1 captured multicast UDP traffic from Laptop 2. \| Directly
  observed. \|

| Laptop 1 announced membership in 239.1.1.1. \| Directly observed
  IGMPv2 Membership Report. \|

| 192.168.1.254 sent general IGMP queries. \| Directly observed. \|

| 192.168.1.254 is definitely a specific router/device. \| Not
  established. \|

| IGMP snooping is enabled. \| Not established. \|

| Switch selectively forwards only to member ports. \| Not established.
  \|

| Stopping the receiver produces a particular Leave message. \| Not
  tested yet. \|

Seeing IGMP packets does not itself prove IGMP snooping. Snooping is
switch behaviour and needs switch configuration/management evidence or a
controlled forwarding experiment.

## 11. Immediate next task --- receiver departure

Current position: Phase 2 is complete. Laptop 1 has joined 239.1.1.1 and
captured UDP packets. Now test what happens when its receiver
application exits.

On Laptop 1, go to the receiver terminal and press Ctrl+C.

Keep Wireshark capturing on enx207bd51e1472. Apply `igmp` and inspect
messages immediately after the receiver stops.

Record whether an IGMP Leave Group message appears. Do not assume it
must appear; record timing and packet details.

On Laptop 2, verify Receiver 1 continues receiving from all three
senders.

On Laptop 1, apply `ip.dst == 239.1.1.1 && udp.dstport == 5000` and
check whether packets remain visible at the interface after the
application exits.

Restart Laptop 1's receiver and observe whether a new membership report
appears.

Interpretation caution: application socket delivery, kernel group
membership, NIC packet reception, packet-capture visibility, and switch
forwarding state are different layers. A packet visible in Wireshark
does not prove that the stopped Python application received it.

## 12. Future experiments

| Phase \| Experiment \| Questions \|

| --- \| --- \| --- \|

| 3 \| Receiver departure/rejoin \| Does Leave Group appear? Does Laptop
  2 continue? What is visible after process exit? \|

| 4 \| IGMPv2 last-member behaviour \| Are group-specific queries sent?
  What are query intervals/counts? When does membership expire? \|

| 5 \| Interface and socket behaviour \| How do capture, kernel
  membership, and socket delivery differ? \|

| 6 \| IGMP snooping \| Does the switch learn group membership and
  selectively forward multicast? \|

| 7 \| Multiple multicast groups \| Can hosts join groups independently?
  \|

| 8 \| Multiple UDP ports \| How do group membership and UDP port
  binding interact? \|

## 13. Troubleshooting checklist

Confirm both laptops are on the intended LAN and can reach each other.

Run `ip -br -4 addr` and verify the intended interface address.

Run `ip route get <peer-ip>` and confirm the selected interface and
source IP.

Ensure sender IP_MULTICAST_IF and receiver IP_ADD_MEMBERSHIP use the
intended interface.

Confirm sender and receiver agree on group address and UDP port.

Check host firewall rules if packets are captured but the application
does not receive them.

Capture on the physical interface, not loopback, Docker, bridge, or VPN
interfaces.

Use `igmp` for control traffic and the UDP destination filter for
application data.

Do not infer IGMP snooping from host-side captures alone.

## 14. Future-run lab log template

| Field \| Value to record \|

| --- \| --- \|

| Date/time \| \[Fill in\] \|

| Experiment/phase \| \[Fill in\] \|

| Laptop 1 interface/IP \| \[Fill in\] \|

| Laptop 2 interface/IP \| \[Fill in\] \|

| Sender processes and intervals \| \[Fill in\] \|

| Receiver processes \| \[Fill in\] \|

| Capture interface(s) \| \[Fill in\] \|

| Display filters \| \[Fill in\] \|

| UDP observations \| \[Fill in\] \|

| IGMP observations \| \[Fill in\] \|

| Unexpected behaviour \| \[Fill in\] \|

| Evidence-based conclusion \| \[Fill in\] \|

| PCAPNG filenames \| \[Fill in\] \|

## 15. Glossary

| Term \| Meaning \|

| --- \| --- \|

| Multicast group \| An IPv4 multicast destination to which receivers
  subscribe. \|

| UDP \| Connectionless transport protocol carrying the demo payload. \|

| IGMP \| IPv4 protocol for communicating multicast group membership. \|

| Querier \| A device that sends periodic IGMP membership queries on a
  network. \|

| Membership Report \| IGMP message indicating interest in a multicast
  group. \|

| Leave Group \| IGMPv2 message indicating that a host is leaving a
  group. \|

| IGMP snooping \| Layer 2 switch function that observes IGMP messages
  to manage multicast forwarding. \|

| TTL \| IPv4 field limiting router-hop scope. \|

| PCAPNG \| Packet-capture file format used to preserve packet evidence.
  \|

## 16. Evidence preservation

Keep original packet captures. Do not overwrite them. PCAPNG files are
more useful than screenshots alone because packets can be re-examined
later. Prefer capturing without restrictive capture filters and applying
display filters afterward.

captures/ ├── phase-01-single-host/ │ ├── laptop-2-udp.pcapng │ └──
laptop-2-igmp.pcapng ├── phase-02-two-hosts/ │ ├── laptop-1-udp.pcapng │
├── laptop-1-igmp.pcapng │ └── laptop-2-observation.pcapng └──
phase-03-membership-departure/ └── pending/

For each capture, record the host, interface, capture start/stop time,
filters used, and event being investigated.

## 17. Version 2 status

The lab has demonstrated multi-process UDP multicast on one Linux host
and cross-host multicast reception on a second physical Linux host.
IGMPv2 membership reports for 239.1.1.1 and general membership queries
from 192.168.1.254 were observed. The next task is the
receiver-departure experiment. IGMP snooping and selective Layer 2
forwarding remain unverified.

Update this record after each experiment with exact commands, actual
outputs, packet details, capture filenames, and evidence-based
conclusions. Never replace pending items with assumed outcomes.
