"""Temporary ready-made-agent sandbox composed around the independent core simulation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from genesis.agents.dynamics import AgentFlux, initialize_population, update_agents
from genesis.config import Config
from genesis.core.simulation import Simulation as EnvironmentSimulation
from genesis.core.state import WorldState
from genesis.environment.resources import Flux


@dataclass(frozen=True)
class SandboxFlux:
    environment: Flux
    agents: AgentFlux


class SandboxSimulation:
    def __init__(self, config: Config):
        self.config = config
        self.environment = EnvironmentSimulation(config)
        self.agents, self.agent_ledger = initialize_population(
            self.environment.state, config.agents, self.environment.rng.agents
        )

    @property
    def world(self) -> WorldState:
        return self.environment.state

    def step(self) -> SandboxFlux:
        environment_flux = self.environment.step()
        agent_flux = update_agents(
            self.world,
            self.agents,
            self.agent_ledger,
            self.config,
            self.environment.rng.agents,
        )
        self.world.assert_valid()
        self.agents.assert_valid(self.world)
        self.agent_ledger.assert_valid()
        return SandboxFlux(environment_flux, agent_flux)

    def advance(self, steps: int) -> None:
        if type(steps) is not int or steps < 0:
            raise ValueError("steps must be a nonnegative integer")
        for _ in range(steps):
            self.step()

    def digest(self) -> str:
        h = sha256(self.world.digest().encode())
        h.update(self.agents.digest().encode())
        rng_state = self.environment.rng.agents.bit_generator.state
        h.update(json.dumps(rng_state, sort_keys=True, separators=(",", ":")).encode())
        return h.hexdigest()
