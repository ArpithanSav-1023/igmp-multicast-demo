"""Simulated vessel and navigation equipment.

Design goal: values from different sentences, and from different equipment on
the same vessel, never contradict each other.

  * `Vessel` is the single source of truth. It steams at constant speed in a
    steady turn, so its path is a circle. Everything is a closed-form function
    of time, so two separate processes given the same configuration compute
    the same truth with no shared state and no drift after weeks of uptime.
  * `GnssSource`, `GyroSource` and `SpeedLogSource` are sensors. They read the
    vessel at a given time and add small deterministic noise (seeded by sensor
    seed and whole-second timestamp, so repeated calls agree).

Simplifications (documented, not hidden): flat-earth conversion around the
circle centre, no leeway (COG equals true heading), and steady turn rate.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _noise(seed, label, when, scale):
    """Deterministic uniform noise in [-scale, scale] for one whole second."""
    rng = random.Random(f"{seed}:{label}:{int(when.timestamp())}")
    return rng.uniform(-scale, scale)


@dataclass(frozen=True)
class Vessel:
    center_lat: float = 50.9662        # centre of the circular track, degrees
    center_lon: float = 1.7685
    stw_kn: float = 10.0               # speed through the water
    current_kn: float = 0.3            # current along the course; SOG = STW + current
    turn_rate_deg_min: float = 3.0     # steady turn, positive = starboard
    heading0_deg: float = 0.0          # true heading at EPOCH
    variation_deg: float = 2.0         # magnetic variation, east positive
    epoch: datetime = EPOCH

    @property
    def sog_kn(self) -> float:
        return self.stw_kn + self.current_kn

    def _dt(self, when: datetime) -> float:
        return (when - self.epoch).total_seconds()

    def heading(self, when: datetime) -> float:
        """True heading in degrees [0, 360)."""
        return (self.heading0_deg + self.turn_rate_deg_min / 60.0 * self._dt(when)) % 360.0

    def cog(self, when: datetime) -> float:
        """Course over ground; equal to heading (no leeway modelled)."""
        return self.heading(when)

    def position(self, when: datetime):
        """(lat, lon) in degrees."""
        theta = math.radians(self.heading(when))
        omega_per_h = math.radians(self.turn_rate_deg_min) * 60.0
        if omega_per_h == 0:  # straight line from the centre point
            dist_nm = self.sog_kn * self._dt(when) / 3600.0
            north_nm = dist_nm * math.cos(theta)
            east_nm = dist_nm * math.sin(theta)
        else:
            # Circle: radius r = v / omega (signed). With heading theta,
            # N = Nc + r sin(theta), E = Ec - r cos(theta) gives velocity
            # (v cos theta, v sin theta) for any sign of omega.
            r_nm = self.sog_kn / omega_per_h
            north_nm = r_nm * math.sin(theta)
            east_nm = -r_nm * math.cos(theta)
        lat = self.center_lat + north_nm / 60.0
        lon = self.center_lon + east_nm / 60.0 / math.cos(math.radians(self.center_lat))
        return lat, lon


@dataclass(frozen=True)
class GnssFix:
    when: datetime
    lat: float
    lon: float
    sog_kn: float
    cog_true: float
    variation_deg: float
    satellites: int
    hdop: float
    altitude_m: float
    geoid_sep_m: float


@dataclass(frozen=True)
class GyroReading:
    when: datetime
    heading_true: float
    heading_mag: float
    rot_deg_min: float
    variation_deg: float


@dataclass(frozen=True)
class LogReading:
    when: datetime
    heading_true: float
    heading_mag: float
    stw_kn: float
    water_long_kn: float
    water_trans_kn: float
    ground_long_kn: float
    ground_trans_kn: float


@dataclass
class GnssSource:
    name: str
    vessel: Vessel
    talker: str = "GP"
    seed: int = 1
    position_noise_m: float = 1.5
    satellites: int = 8
    hdop: float = 0.9
    altitude_m: float = 12.3
    geoid_sep_m: float = 47.0
    kind: str = "gnss"

    def reading(self, when: datetime) -> GnssFix:
        lat, lon = self.vessel.position(when)
        m = self.position_noise_m
        dn = _noise(self.seed, "n", when, m) / 1852.0 / 60.0
        de = _noise(self.seed, "e", when, m) / 1852.0 / 60.0 / math.cos(math.radians(lat))
        return GnssFix(
            when=when, lat=lat + dn, lon=lon + de,
            sog_kn=max(0.0, self.vessel.sog_kn + _noise(self.seed, "sog", when, 0.05)),
            cog_true=(self.vessel.cog(when) + _noise(self.seed, "cog", when, 0.2)) % 360.0,
            variation_deg=self.vessel.variation_deg, satellites=self.satellites,
            hdop=self.hdop, altitude_m=self.altitude_m, geoid_sep_m=self.geoid_sep_m,
        )


@dataclass
class GyroSource:
    name: str
    vessel: Vessel
    talker: str = "HE"
    seed: int = 2
    kind: str = "gyro"

    def reading(self, when: datetime) -> GyroReading:
        true = (self.vessel.heading(when) + _noise(self.seed, "hdg", when, 0.1)) % 360.0
        var = self.vessel.variation_deg
        return GyroReading(
            when=when, heading_true=true, heading_mag=(true - var) % 360.0,
            rot_deg_min=self.vessel.turn_rate_deg_min + _noise(self.seed, "rot", when, 0.05),
            variation_deg=var,
        )


@dataclass
class SpeedLogSource:
    name: str
    vessel: Vessel
    talker: str = "VW"
    seed: int = 3
    kind: str = "log"

    def reading(self, when: datetime) -> LogReading:
        true = (self.vessel.heading(when) + _noise(self.seed, "hdg", when, 0.3)) % 360.0
        stw = max(0.0, self.vessel.stw_kn + _noise(self.seed, "stw", when, 0.05))
        sog = max(0.0, self.vessel.sog_kn + _noise(self.seed, "sog", when, 0.05))
        return LogReading(
            when=when, heading_true=true,
            heading_mag=(true - self.vessel.variation_deg) % 360.0, stw_kn=stw,
            water_long_kn=stw, water_trans_kn=0.0, ground_long_kn=sog, ground_trans_kn=0.0,
        )
