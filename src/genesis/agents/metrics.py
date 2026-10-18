"""Observation-only metrics; they never influence agent survival or reproduction."""

from __future__ import annotations

import numpy as np

from genesis.agents.state import AgentLedger, AgentState
from genesis.core.state import WorldState
from genesis.lab.metrics import measure


def measure_sandbox(
    world: WorldState, population: AgentState, ledger: AgentLedger
) -> dict[str, int | float]:
    result = measure(world)
    energy = float(population.energy[: population.count].sum(dtype=np.float64))
    expected_agent = (
        ledger.initial_energy
        + ledger.assimilated
        - ledger.basal_loss
        - ledger.movement_loss
        - ledger.reproduction_loss
        - ledger.death_recycled
        - ledger.death_loss
    )
    current_total = float(result["resource_total"]) + energy
    expected_total = (
        world.initial_total
        + ledger.initial_energy
        + world.source_total
        - world.sink_total
        - ledger.assimilation_loss
        - ledger.basal_loss
        - ledger.movement_loss
        - ledger.reproduction_loss
        - ledger.death_loss
    )
    result.update(
        population=population.count,
        agent_energy_total=energy,
        agent_energy_mean=energy / population.count if population.count else 0.0,
        agent_age_mean=(
            float(population.age[: population.count].mean()) if population.count else 0.0
        ),
        births=ledger.births,
        deaths=ledger.deaths,
        consumed_total=ledger.consumed,
        assimilated_total=ledger.assimilated,
        assimilation_loss_total=ledger.assimilation_loss,
        basal_loss_total=ledger.basal_loss,
        movement_loss_total=ledger.movement_loss,
        reproduction_loss_total=ledger.reproduction_loss,
        death_recycled_total=ledger.death_recycled,
        death_loss_total=ledger.death_loss,
        agent_balance_error=energy - expected_agent,
        combined_energy_total=current_total,
        combined_balance_error=current_total - expected_total,
    )
    return result
