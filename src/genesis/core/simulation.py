"""A single simulation owns its configuration, RNG and state. No global random state."""

from __future__ import annotations

from genesis.config import Config
from genesis.core.rng import RandomStreams
from genesis.core.state import WorldState
from genesis.environment.generation import generate
from genesis.environment.resources import Flux, update_resources


class Simulation:
    def __init__(self, config: Config):
        self.config = config
        self.rng = RandomStreams.from_seed(config.seed)
        self.state: WorldState = generate(config, self.rng.environment)

    @classmethod
    def restore(cls, config: Config, state: WorldState, rng: RandomStreams) -> Simulation:
        """Restore validated owned state without regenerating or consuming RNG."""
        instance = cls.__new__(cls)
        instance.config = config
        instance.rng = rng
        instance.state = state
        state.assert_valid()
        return instance

    def step(self) -> Flux:
        flux = update_resources(self.state, self.config)
        self.state.tick += 1
        self.state.assert_valid()
        return flux

    def advance(self, steps: int) -> None:
        if type(steps) is not int or steps < 0:
            raise ValueError("steps must be a nonnegative integer")
        for _ in range(steps):
            self.step()
