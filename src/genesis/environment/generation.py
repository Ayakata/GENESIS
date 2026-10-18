"""Seeded terrain is a test environment, not an emergent biological structure."""

import numpy as np

from genesis.config import Config
from genesis.core.state import Conditions, WorldState
from genesis.core.topology import FloatField


def generate(config: Config, rng: np.random.Generator) -> WorldState:
    height, width = config.world.height, config.world.width
    yy, xx = np.meshgrid(
        (np.arange(height) + 0.5) / height,
        (np.arange(width) + 0.5) / width,
        indexing="ij",
    )
    elevation: FloatField = np.zeros((height, width), dtype=np.float64)
    if config.terrain.kind == "uniform":
        elevation.fill(1.0)
        land = np.ones_like(elevation, dtype=np.bool_)
    else:
        for _ in range(config.terrain.islands):
            cx, cy = rng.uniform(0, 1, 2)
            rx, ry = config.terrain.radius * rng.uniform(0.7, 1.3, 2)
            dx, dy = np.abs(xx - cx), np.abs(yy - cy)
            if config.world.boundary == "periodic":
                dx, dy = np.minimum(dx, 1 - dx), np.minimum(dy, 1 - dy)
            hill = np.exp(-0.5 * ((dx / rx) ** 2 + (dy / ry) ** 2))
            np.maximum(elevation, hill, out=elevation)
        elevation += config.terrain.noise * rng.random(elevation.shape)
        np.clip(elevation, 0, 1, out=elevation)
        land = elevation > config.terrain.sea_level
    c = config.conditions
    latitude = np.abs(2 * yy - 1)
    temperature = c.equator_temperature - c.polar_drop * latitude - c.elevation_drop * elevation
    humidity = rng.uniform(c.humidity_min, c.humidity_max, elevation.shape)
    light = np.broadcast_to(
        c.light_max - (c.light_max - c.light_min) * latitude, elevation.shape
    ).copy()
    resource = rng.uniform(
        config.resource.initial_min, config.resource.initial_max, elevation.shape
    )
    resource *= land
    state = WorldState(
        conditions=Conditions(elevation, land, temperature, humidity, light),
        resource=resource,
        initial_total=float(resource.sum(dtype=np.float64)),
    )
    state.assert_valid()
    return state
