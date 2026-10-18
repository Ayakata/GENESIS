"""Observation-only metrics; they never influence agent survival or reproduction."""

from __future__ import annotations

import numpy as np

from genesis.agents.state import AgentLedger, AgentState
from genesis.core.state import WorldState
from genesis.evolution.genome import GENE_NAMES
from genesis.evolution.state import EvolutionLedger
from genesis.lab.metrics import measure


def measure_sandbox(
    world: WorldState,
    population: AgentState,
    ledger: AgentLedger,
    evolution: EvolutionLedger,
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
        mutated_loci=evolution.mutated_loci,
        clipped_loci=evolution.clipped_loci,
        mutated_offspring=evolution.mutated_offspring,
    )
    genomes = population.genome[: population.count]
    if population.count:
        means = genomes.mean(axis=0)
        standard_deviations = genomes.std(axis=0)
    else:
        means = standard_deviations = np.zeros(len(GENE_NAMES), dtype=np.float64)
    for index, name in enumerate(GENE_NAMES):
        result[f"gene_{name}_mean"] = float(means[index])
        result[f"gene_{name}_std"] = float(standard_deviations[index])
    result["genetic_variance_mean"] = float(np.mean(standard_deviations**2))
    return result
