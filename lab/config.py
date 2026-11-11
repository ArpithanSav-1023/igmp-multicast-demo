"""Load and validate the lab's TOML configuration (standard library only)."""

import ipaddress
import tomllib
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

from .nmea.generator import SENTENCE_KINDS
from .nmea.models import GnssSource, GyroSource, SpeedLogSource, Vessel

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


class ConfigError(Exception):
    """Raised for any invalid or missing configuration."""


@dataclass(frozen=True)
class Group:
    name: str
    ip: str
    port: int
    purpose: str = ""


@dataclass(frozen=True)
class SenderConfig:
    name: str
    equipment: str
    talker: str
    source_ip: str
    group: str
    interval: float
    kinds: tuple
    seed: int = 1
    description: str = ""


def _load(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"missing config file: {path}")
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}")


def _ipv4(value, what):
    try:
        return ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        raise ConfigError(f"{what}: not an IPv4 address: {value!r}")


def _port(value, what):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
        raise ConfigError(f"{what}: port must be an integer 1..65535, got {value!r}")
    return value


def load_groups(config_dir=DEFAULT_CONFIG_DIR) -> dict:
    data = _load(Path(config_dir) / "groups.toml").get("groups", {})
    if not data:
        raise ConfigError("groups.toml defines no [groups.*] tables")
    groups = {}
    for name, g in data.items():
        addr = _ipv4(g.get("ip"), f"group {name}")
        if not addr.is_multicast:
            raise ConfigError(f"group {name}: {addr} is not a multicast address")
        groups[name] = Group(name, str(addr), _port(g.get("port", 5000), f"group {name}"),
                             g.get("purpose", ""))
    ips = [g.ip for g in groups.values()]
    if len(set(ips)) != len(ips):
        raise ConfigError("groups.toml: two groups share the same multicast IP")
    return groups


def load_senders(config_dir=DEFAULT_CONFIG_DIR, groups=None) -> dict:
    data = _load(Path(config_dir) / "senders.toml")
    groups = groups if groups is not None else load_groups(config_dir)
    raw = data.get("senders", {})
    if not raw:
        raise ConfigError("senders.toml defines no [senders.*] tables")
    senders = {}
    for name, s in raw.items():
        where = f"sender {name}"
        equipment = s.get("equipment")
        if equipment not in SENTENCE_KINDS:
            raise ConfigError(f"{where}: equipment must be one of {sorted(SENTENCE_KINDS)}, got {equipment!r}")
        kinds = tuple(str(k).upper() for k in s.get("kinds", SENTENCE_KINDS[equipment]))
        bad = [k for k in kinds if k not in SENTENCE_KINDS[equipment]]
        if bad or not kinds:
            raise ConfigError(f"{where}: kinds {bad or kinds} not valid for {equipment}; "
                              f"choose from {SENTENCE_KINDS[equipment]}")
        interval = s.get("interval", 1.0)
        if not isinstance(interval, (int, float)) or isinstance(interval, bool) or interval <= 0:
            raise ConfigError(f"{where}: interval must be a number > 0, got {interval!r}")
        group = s.get("group")
        if group not in groups:
            raise ConfigError(f"{where}: unknown group {group!r}; defined: {sorted(groups)}")
        talker = s.get("talker", "")
        if len(talker) != 2 or not talker.isalpha() or not talker.isupper():
            raise ConfigError(f"{where}: talker must be two upper-case letters, got {talker!r}")
        senders[name] = SenderConfig(
            name=name, equipment=equipment, talker=talker,
            source_ip=str(_ipv4(s.get("source_ip"), where)), group=group,
            interval=float(interval), kinds=kinds, seed=int(s.get("seed", 1)),
            description=s.get("description", ""),
        )
    return senders


def load_vessel(config_dir=DEFAULT_CONFIG_DIR) -> Vessel:
    table = dict(_load(Path(config_dir) / "senders.toml").get("vessel", {}))
    allowed = {f.name for f in fields(Vessel)}
    unknown = set(table) - allowed
    if unknown:
        raise ConfigError(f"[vessel]: unknown keys {sorted(unknown)}")
    if "epoch" in table:
        try:
            epoch = datetime.fromisoformat(str(table["epoch"]))
        except ValueError:
            raise ConfigError(f"[vessel] epoch is not an ISO-8601 time: {table['epoch']!r}")
        table["epoch"] = epoch if epoch.tzinfo else epoch.replace(tzinfo=timezone.utc)
    return Vessel(**table)


def build_source(cfg: SenderConfig, vessel: Vessel):
    """Create the sensor model for a configured sender."""
    cls = {"gnss": GnssSource, "gyro": GyroSource, "log": SpeedLogSource}[cfg.equipment]
    return cls(name=cfg.name, vessel=vessel, talker=cfg.talker, seed=cfg.seed)


def resolve_group(spec: str, groups: dict, default_port=5000) -> Group:
    """Accept a configured group name or a literal multicast IPv4 address."""
    if spec in groups:
        return groups[spec]
    try:
        addr = ipaddress.IPv4Address(spec)
    except (ipaddress.AddressValueError, ValueError):
        raise ConfigError(f"unknown group {spec!r}; defined: {sorted(groups)} (or give a multicast IP)")
    if not addr.is_multicast:
        raise ConfigError(f"{addr} is not a multicast address")
    for g in groups.values():
        if g.ip == str(addr):
            return g
    return Group(name=str(addr), ip=str(addr), port=default_port)
