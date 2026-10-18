"""Structure-of-arrays population state and explicit agent-energy ledger."""

from __future__ import annotations

from dataclasses import dataclass, fields
from hashlib import sha256

import numpy as np
from numpy.typing import NDArray

from genesis import AGENT_RULESET_VERSION, STATE_SCHEMA_VERSION
from genesis.core.state import WorldState
from genesis.evolution.genome import GENE_COUNT, GenomeArray

Int64Array = NDArray[np.int64]
Int32Array = NDArray[np.int32]
UInt32Array = NDArray[np.uint32]
Float64Array = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass
class AgentState:
    """Dense active prefix of fixed-capacity typed arrays; no per-agent Python objects."""

    ids: Int64Array
    parent_ids: Int64Array
    x: Int32Array
    y: Int32Array
    energy: Float64Array
    age: UInt32Array
    genome: GenomeArray
    count: int
    next_id: int

    @classmethod
    def empty(cls, capacity: int) -> AgentState:
        if capacity < 0:
            raise ValueError("capacity must be nonnegative")
        return cls(
            ids=np.empty(capacity, dtype=np.int64),
            parent_ids=np.empty(capacity, dtype=np.int64),
            x=np.empty(capacity, dtype=np.int32),
            y=np.empty(capacity, dtype=np.int32),
            energy=np.empty(capacity, dtype=np.float64),
            age=np.empty(capacity, dtype=np.uint32),
            genome=np.empty((capacity, GENE_COUNT), dtype=np.float64),
            count=0,
            next_id=0,
        )

    @property
    def capacity(self) -> int:
        return int(self.ids.size)

    def add(
        self,
        x: Int32Array,
        y: Int32Array,
        energy: Float64Array,
        parent_ids: Int64Array,
        genome: GenomeArray,
    ) -> None:
        size = int(x.size)
        if any(array.ndim != 1 or array.size != size for array in (y, energy, parent_ids)):
            raise ValueError("agent append arrays must be matching one-dimensional arrays")
        if genome.shape != (size, GENE_COUNT):
            raise ValueError(f"agent genomes must have shape [{size},{GENE_COUNT}]")
        if self.count + size > self.capacity:
            raise RuntimeError("agent population capacity exceeded")
        target = slice(self.count, self.count + size)
        self.ids[target] = np.arange(self.next_id, self.next_id + size, dtype=np.int64)
        self.parent_ids[target] = parent_ids
        self.x[target] = x
        self.y[target] = y
        self.energy[target] = energy
        self.age[target] = 0
        self.genome[target] = genome
        self.count += size
        self.next_id += size

    def compact(self, keep: BoolArray) -> None:
        if keep.shape != (self.count,):
            raise ValueError("keep mask must match active population")
        retained = int(keep.sum())
        for array in (
            self.ids,
            self.parent_ids,
            self.x,
            self.y,
            self.energy,
            self.age,
            self.genome,
        ):
            array[:retained] = array[: self.count][keep]
        self.count = retained

    def assert_valid(self, world: WorldState) -> None:
        arrays = (self.ids, self.parent_ids, self.x, self.y, self.energy, self.age)
        if any(array.ndim != 1 or array.size != self.capacity for array in arrays):
            raise RuntimeError("Agent SoA capacity mismatch")
        if self.genome.shape != (self.capacity, GENE_COUNT):
            raise RuntimeError("Agent genome capacity mismatch")
        if not 0 <= self.count <= self.capacity or self.next_id < self.count:
            raise RuntimeError("Invalid agent counters")
        active = slice(0, self.count)
        if not np.isfinite(self.energy[active]).all() or (self.energy[active] < 0).any():
            raise RuntimeError("Invalid agent energy")
        genomes = self.genome[: self.count]
        if not np.isfinite(genomes).all() or (genomes < 0).any() or (genomes > 1).any():
            raise RuntimeError("Agent gene outside [0,1]")
        height, width = world.resource.shape
        if (
            (self.x[active] < 0).any()
            or (self.x[active] >= width).any()
            or (self.y[active] < 0).any()
            or (self.y[active] >= height).any()
        ):
            raise RuntimeError("Agent outside world")
        if self.count and not world.conditions.land[self.y[active], self.x[active]].all():
            raise RuntimeError("Agent outside active land")
        if self.count and np.unique(self.ids[active]).size != self.count:
            raise RuntimeError("Duplicate agent id")

    def digest(self) -> str:
        h = sha256(f"{STATE_SCHEMA_VERSION}:{AGENT_RULESET_VERSION}:{self.count}".encode())
        for array in (self.ids, self.parent_ids, self.x, self.y, self.energy, self.age):
            active = array[: self.count]
            h.update(active.dtype.str.encode())
            h.update(active.astype(active.dtype.newbyteorder("<")).tobytes(order="C"))
        genome = self.genome[: self.count]
        h.update(genome.astype("<f8").tobytes(order="C"))
        h.update(np.array([self.next_id], dtype="<i8").tobytes())
        return h.hexdigest()


@dataclass
class AgentLedger:
    initial_energy: float = 0.0
    consumed: float = 0.0
    assimilated: float = 0.0
    assimilation_loss: float = 0.0
    basal_loss: float = 0.0
    movement_loss: float = 0.0
    reproduction_loss: float = 0.0
    death_recycled: float = 0.0
    death_loss: float = 0.0
    births: int = 0
    deaths: int = 0

    def assert_valid(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name in ("births", "deaths"):
                if type(value) is not int or value < 0:
                    raise RuntimeError("Invalid agent event ledger")
            elif not np.isfinite(value) or value < 0:
                raise RuntimeError("Invalid agent energy ledger")
