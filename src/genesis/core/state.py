"""Dense float64 fields; conditions are immutable during the current ruleset."""

from dataclasses import dataclass
from hashlib import sha256

import numpy as np

from genesis import RULESET_VERSION, STATE_SCHEMA_VERSION
from genesis.core.topology import FloatField, Mask


@dataclass(frozen=True)
class Conditions:
    elevation: FloatField
    land: Mask
    temperature: FloatField
    humidity: FloatField
    light: FloatField

    def __post_init__(self) -> None:
        for array in (self.elevation, self.land, self.temperature, self.humidity, self.light):
            array.flags.writeable = False


@dataclass
class WorldState:
    conditions: Conditions
    resource: FloatField
    tick: int = 0
    source_total: float = 0.0
    sink_total: float = 0.0
    transfer_in_total: float = 0.0
    transfer_out_total: float = 0.0
    initial_total: float = 0.0

    def assert_valid(self) -> None:
        arrays = (
            self.resource,
            self.conditions.elevation,
            self.conditions.temperature,
            self.conditions.humidity,
            self.conditions.light,
        )
        if any(a.shape != self.conditions.land.shape for a in arrays):
            raise RuntimeError("World field shape mismatch")
        if any(not np.isfinite(a).all() for a in arrays):
            raise RuntimeError("Non-finite world field")
        if (self.resource < 0).any() or (self.resource[~self.conditions.land] != 0).any():
            raise RuntimeError("Negative resource or resource outside land")
        if self.tick < 0 or any(
            not np.isfinite(v) or v < 0
            for v in (
                self.source_total,
                self.sink_total,
                self.transfer_in_total,
                self.transfer_out_total,
                self.initial_total,
            )
        ):
            raise RuntimeError("Invalid clock or resource ledger")

    def digest(self) -> str:
        """Canonical little-endian scientific state digest (excludes runtime metadata)."""
        h = sha256(f"{STATE_SCHEMA_VERSION}:{RULESET_VERSION}:{self.tick}".encode())
        arrays = (
            self.conditions.elevation,
            self.conditions.land,
            self.conditions.temperature,
            self.conditions.humidity,
            self.conditions.light,
            self.resource,
        )
        for a in arrays:
            h.update(str(a.shape).encode())
            h.update(a.astype("u1" if a.dtype == np.bool_ else "<f8").tobytes(order="C"))
        h.update(
            np.array(
                [
                    self.initial_total,
                    self.source_total,
                    self.sink_total,
                    self.transfer_in_total,
                    self.transfer_out_total,
                ],
                dtype="<f8",
            ).tobytes()
        )
        return h.hexdigest()
