"""Interface helpers: make sure lab traffic uses a wired Ethernet address.

The lab must never rely on automatic interface selection and must never
transmit through Wi-Fi. These helpers map a configured IPv4 address to the
interface that owns it and refuse anything that is not usable Ethernet.
"""

import json
import subprocess
from pathlib import Path

SYS_NET = Path("/sys/class/net")


class InterfaceError(Exception):
    """Raised when a configured address cannot be used for lab traffic."""


def ipv4_addresses() -> dict:
    """Map every local IPv4 address (including secondaries) to its interface name."""
    try:
        out = subprocess.run(["ip", "-j", "-4", "addr", "show"], check=True,
                             capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InterfaceError(f"cannot list addresses with 'ip -j -4 addr show': {exc}")
    mapping = {}
    for iface in json.loads(out):
        for addr in iface.get("addr_info", []):
            mapping[addr["local"]] = iface["ifname"]
    return mapping


def is_wireless(ifname: str) -> bool:
    base = SYS_NET / ifname
    return (base / "wireless").exists() or (base / "phy80211").exists()


def has_carrier(ifname: str) -> bool:
    try:
        return (SYS_NET / ifname / "carrier").read_text().strip() == "1"
    except OSError:
        return False


def require_ethernet_address(ip: str) -> str:
    """Return the interface name owning `ip`, or raise InterfaceError.

    Rejects addresses that are not local, are on loopback, or sit on a
    wireless interface. Does not require a particular interface name, so the
    same code works for 'enp3s0' and 'enx207bd51e1472'.
    """
    owners = ipv4_addresses()
    if ip not in owners:
        raise InterfaceError(f"{ip} is not assigned to any local interface "
                             f"(local: {', '.join(sorted(owners)) or 'none'})")
    ifname = owners[ip]
    if ifname == "lo":
        raise InterfaceError(f"{ip} is on the loopback interface")
    if is_wireless(ifname):
        raise InterfaceError(f"{ip} is on wireless interface {ifname}; lab traffic must use Ethernet")
    if not has_carrier(ifname):
        raise InterfaceError(f"{ifname} ({ip}) has no carrier; is the cable connected?")
    return ifname
