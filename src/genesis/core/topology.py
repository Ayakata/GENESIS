"""Synchronous four-neighbour diffusion with impermeable inactive cells."""

import numpy as np
from numpy.typing import NDArray

from genesis.config import ConfigError

FloatField = NDArray[np.float64]
Mask = NDArray[np.bool_]


def diffuse(field: FloatField, active: Mask, rate: float, boundary: str) -> FloatField:
    """Each undirected edge exchanges rate*(b-a); no in-place ordering effects.

    Periodic grids of size 1 and 2 retain lattice neighbour multiplicities.
    At rate <= 1/4 this is a convex combination of nonnegative inputs.
    """
    if field.ndim != 2 or field.shape != active.shape:
        raise ValueError("field and active must be matching 2D arrays")
    if not np.isfinite(rate) or not 0 <= rate <= 0.25:
        raise ValueError("diffusion rate must be in [0,0.25]")
    if boundary not in ("closed", "periodic"):
        raise ConfigError(f"Unknown boundary: {boundary}")
    # Evaluate the equivalent convex combination instead of repeatedly subtracting
    # outward flux. The latter can create tiny negative values at rate=0.25.
    degree = np.zeros(field.shape, dtype=np.uint8)
    neighbour_sum = np.zeros_like(field)
    if boundary == "periodic":
        for axis in (0, 1):
            for shift in (-1, 1):
                neighbour = np.roll(field, shift, axis=axis)
                connected = active & np.roll(active, shift, axis=axis)
                degree += connected
                neighbour_sum += np.where(connected, neighbour, 0.0)
    else:
        horizontal = active[:, 1:] & active[:, :-1]
        degree[:, :-1] += horizontal
        degree[:, 1:] += horizontal
        neighbour_sum[:, :-1] += field[:, 1:] * horizontal
        neighbour_sum[:, 1:] += field[:, :-1] * horizontal
        vertical = active[1:, :] & active[:-1, :]
        degree[:-1, :] += vertical
        degree[1:, :] += vertical
        neighbour_sum[:-1, :] += field[1:, :] * vertical
        neighbour_sum[1:, :] += field[:-1, :] * vertical
    return (1.0 - rate * degree) * field + rate * neighbour_sum
