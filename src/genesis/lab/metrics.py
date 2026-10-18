from __future__ import annotations

import numpy as np

from genesis.core.state import WorldState


def measure(state: WorldState) -> dict[str, int | float]:
    total = float(state.resource.sum(dtype=np.float64))
    expected = state.initial_total + state.source_total - state.sink_total
    return {
        "tick": state.tick,
        "land_cells": int(state.conditions.land.sum()),
        "resource_total": total,
        "resource_min": float(state.resource.min()),
        "resource_max": float(state.resource.max()),
        "source_total": state.source_total,
        "sink_total": state.sink_total,
        "balance_error": total - expected,
    }
