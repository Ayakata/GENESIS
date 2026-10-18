"""Open energy-like resource reservoir; this is not a matter-conserving chemistry."""

from dataclasses import dataclass

import numpy as np

from genesis.config import Config
from genesis.core.state import WorldState
from genesis.core.topology import diffuse


@dataclass(frozen=True)
class Flux:
    source: float
    sink: float


def update_resources(state: WorldState, config: Config) -> Flux:
    r = config.resource
    transported = diffuse(state.resource, state.conditions.land, r.diffusion, config.world.boundary)
    incoming = (
        r.source_rate * state.conditions.light * state.conditions.humidity * state.conditions.land
    )
    available = transported + incoming
    lost = r.decay * available
    state.resource = available - lost
    source = float(incoming.sum(dtype=np.float64))
    sink = float(lost.sum(dtype=np.float64))
    state.source_total += source
    state.sink_total += sink
    return Flux(source, sink)
