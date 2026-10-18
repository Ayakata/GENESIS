"""Stable stream assignments: never insert streams ahead of an existing stream."""

from dataclasses import dataclass

import numpy as np


@dataclass
class RandomStreams:
    environment: np.random.Generator
    agents: np.random.Generator

    @classmethod
    def from_seed(cls, seed: int) -> "RandomStreams":
        environment, agents = np.random.SeedSequence(seed).spawn(2)
        return cls(
            np.random.Generator(np.random.PCG64(environment)),
            np.random.Generator(np.random.PCG64(agents)),
        )
