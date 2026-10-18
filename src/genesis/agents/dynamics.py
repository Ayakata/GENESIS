"""Local agent rules with explicit transfers and action costs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from genesis.agents.state import AgentLedger, AgentState
from genesis.config import AgentConfig, Config
from genesis.core.state import WorldState
from genesis.evolution.genome import Gene, express, initialize_genomes, mutate
from genesis.evolution.state import EvolutionLedger


@dataclass(frozen=True)
class AgentFlux:
    consumed: float
    assimilated: float
    basal_loss: float
    movement_loss: float
    reproduction_loss: float
    death_recycled: float
    death_loss: float
    births: int
    deaths: int
    mutated_loci: int
    clipped_loci: int
    mutated_offspring: int


def initialize_population(
    world: WorldState, config: Config, rng: np.random.Generator
) -> tuple[AgentState, AgentLedger]:
    agents = config.agents
    population = AgentState.empty(agents.max_population)
    if agents.initial_count:
        land_y, land_x = np.nonzero(world.conditions.land)
        if not land_x.size:
            raise RuntimeError("Cannot place initial agents: world has no land")
        selected = rng.integers(0, land_x.size, size=agents.initial_count)
        genomes = initialize_genomes(agents.initial_count, config=config.evolution, rng=rng)
        population.add(
            land_x[selected].astype(np.int32),
            land_y[selected].astype(np.int32),
            np.full(agents.initial_count, agents.initial_energy, dtype=np.float64),
            np.full(agents.initial_count, -1, dtype=np.int64),
            genomes,
        )
    ledger = AgentLedger(initial_energy=agents.initial_count * agents.initial_energy)
    population.assert_valid(world)
    ledger.assert_valid()
    return population, ledger


def _move(
    world: WorldState,
    population: AgentState,
    config: Config,
    rng: np.random.Generator,
) -> float:
    count = population.count
    if not count:
        return 0.0
    traits = express(population.genome[:count])
    random_directions = rng.integers(0, 4, size=count)
    dx = np.array([1, 0, -1, 0], dtype=np.int32)
    dy = np.array([0, 1, 0, -1], dtype=np.int32)
    old_x = population.x[:count]
    old_y = population.y[:count]
    height, width = world.resource.shape
    candidate_x = old_x[:, None] + dx
    candidate_y = old_y[:, None] + dy
    if config.world.boundary == "periodic":
        candidate_x %= width
        candidate_y %= height
        valid = world.conditions.land[candidate_y, candidate_x]
    else:
        inside = (
            (candidate_x >= 0) & (candidate_x < width) & (candidate_y >= 0) & (candidate_y < height)
        )
        safe_x = np.clip(candidate_x, 0, width - 1)
        safe_y = np.clip(candidate_y, 0, height - 1)
        valid = inside & world.conditions.land[safe_y, safe_x]
        candidate_x, candidate_y = safe_x, safe_y

    candidate_resource = np.where(valid, world.resource[candidate_y, candidate_x], -np.inf)
    best_value = candidate_resource.max(axis=1)
    tie_score = rng.random(candidate_resource.shape)
    tie_score[(candidate_resource != best_value[:, None]) | ~valid] = -1.0
    sensed_directions = tie_score.argmax(axis=1)
    senses = rng.random(count) < traits.sensing
    directions = np.where(senses, sensed_directions, random_directions)
    row = np.arange(count)
    new_x = candidate_x[row, directions]
    new_y = candidate_y[row, directions]
    destination_valid = valid[row, directions]
    destination_resource = candidate_resource[row, directions]
    current_resource = world.resource[old_y, old_x]

    move_probability = (0.1 + 0.9 * traits.speed) * (0.25 + 0.75 * traits.exploration)
    reproduction_reserve = config.agents.reproduction_threshold * traits.reproduction * traits.body
    low_energy = population.energy[:count] < reproduction_reserve
    move_probability *= np.where(low_energy, 1.0 - 0.75 * traits.caution, 1.0)
    accepts_worse = (
        (~senses)
        | (destination_resource > current_resource)
        | (rng.random(count) < traits.exploration)
    )
    attempts = (rng.random(count) < move_probability) & accepts_worse
    costs = config.agents.move_cost * traits.body * (0.25 + traits.speed**2)
    can_pay = population.energy[:count] >= costs
    moved = destination_valid & attempts & can_pay & ((new_x != old_x) | (new_y != old_y))
    population.x[:count][moved] = new_x[moved]
    population.y[:count][moved] = new_y[moved]
    loss = float(costs[moved].sum(dtype=np.float64))
    population.energy[:count][moved] -= costs[moved]
    return loss


def _feed(world: WorldState, population: AgentState, config: AgentConfig) -> tuple[float, float]:
    count = population.count
    if not count or config.intake_rate == 0:
        return 0.0, 0.0
    height, width = world.resource.shape
    traits = express(population.genome[:count])
    flat_cells = population.y[:count].astype(np.int64) * width + population.x[:count]
    demand = config.intake_rate * np.sqrt(traits.body) * traits.metabolism
    cell_demand = np.bincount(flat_cells, weights=demand, minlength=height * width)
    flat_resource = world.resource.reshape(-1)
    cell_consumed = np.minimum(flat_resource, cell_demand)
    allocation = np.divide(
        cell_consumed,
        cell_demand,
        out=np.zeros_like(cell_consumed),
        where=cell_demand > 0,
    )
    per_agent = demand * allocation[flat_cells]
    flat_resource -= cell_consumed
    efficiency = np.minimum(1.0, config.assimilation_efficiency * traits.efficiency)
    assimilated_by_agent = per_agent * efficiency
    population.energy[:count] += assimilated_by_agent
    consumed = float(cell_consumed.sum(dtype=np.float64))
    assimilated = float(assimilated_by_agent.sum(dtype=np.float64))
    world.transfer_out_total += consumed
    return consumed, assimilated


def _reproduce(
    population: AgentState, config: Config, rng: np.random.Generator
) -> tuple[int, float, int, int, int]:
    current = population.count
    slots = population.capacity - current
    if not current or slots <= 0:
        return 0, 0.0, 0, 0, 0
    traits = express(population.genome[:current])
    offspring_energy = config.agents.offspring_energy * traits.body
    reproduction_cost = config.agents.reproduction_cost * traits.body
    threshold = config.agents.reproduction_threshold * traits.reproduction * traits.body
    required = offspring_energy + reproduction_cost
    eligible = np.flatnonzero(population.energy[:current] >= np.maximum(threshold, required))
    if eligible.size > slots:
        eligible = np.sort(rng.choice(eligible, size=slots, replace=False))
    births = int(eligible.size)
    if not births:
        return 0, 0.0, 0, 0, 0
    inheritance = mutate(population.genome[eligible], config.evolution, rng)
    population.energy[eligible] -= required[eligible]
    population.add(
        population.x[eligible].copy(),
        population.y[eligible].copy(),
        offspring_energy[eligible],
        population.ids[eligible].copy(),
        inheritance.genomes,
    )
    return (
        births,
        float(reproduction_cost[eligible].sum(dtype=np.float64)),
        inheritance.mutated_loci,
        inheritance.clipped_loci,
        inheritance.mutated_offspring,
    )


def _remove_dead(
    world: WorldState, population: AgentState, config: AgentConfig
) -> tuple[int, float, float]:
    count = population.count
    if not count:
        return 0, 0.0, 0.0
    dead = (population.energy[:count] <= 0) | (population.age[:count] >= config.max_age)
    deaths = int(dead.sum())
    if not deaths:
        return 0, 0.0, 0.0
    remaining = population.energy[:count][dead]
    recycled = remaining * config.death_recycle_fraction
    lost = remaining - recycled
    np.add.at(
        world.resource,
        (population.y[:count][dead], population.x[:count][dead]),
        recycled,
    )
    recycled_total = float(recycled.sum(dtype=np.float64))
    lost_total = float(lost.sum(dtype=np.float64))
    world.transfer_in_total += recycled_total
    population.compact(~dead)
    return deaths, recycled_total, lost_total


def update_agents(
    world: WorldState,
    population: AgentState,
    ledger: AgentLedger,
    evolution_ledger: EvolutionLedger,
    config: Config,
    rng: np.random.Generator,
) -> AgentFlux:
    """Advance agents once after the environment update for the same world tick."""
    count = population.count
    population.age[:count] += 1
    traits = express(population.genome[:count])
    maintenance = (
        config.agents.basal_cost * traits.body**0.75 * traits.metabolism
        + config.evolution.sensing_cost * traits.sensing**2
        + config.evolution.efficiency_cost * population.genome[:count, Gene.EFFICIENCY] ** 2
    )
    basal = np.minimum(population.energy[:count], maintenance)
    population.energy[:count] -= basal
    basal_loss = float(basal.sum(dtype=np.float64))
    movement_loss = _move(world, population, config, rng)
    consumed, assimilated = _feed(world, population, config.agents)
    births, reproduction_loss, mutated_loci, clipped_loci, mutated_offspring = _reproduce(
        population, config, rng
    )
    deaths, death_recycled, death_loss = _remove_dead(world, population, config.agents)

    ledger.consumed += consumed
    ledger.assimilated += assimilated
    ledger.assimilation_loss += consumed - assimilated
    ledger.basal_loss += basal_loss
    ledger.movement_loss += movement_loss
    ledger.reproduction_loss += reproduction_loss
    ledger.death_recycled += death_recycled
    ledger.death_loss += death_loss
    ledger.births += births
    ledger.deaths += deaths
    evolution_ledger.mutated_loci += mutated_loci
    evolution_ledger.clipped_loci += clipped_loci
    evolution_ledger.mutated_offspring += mutated_offspring
    return AgentFlux(
        consumed=consumed,
        assimilated=assimilated,
        basal_loss=basal_loss,
        movement_loss=movement_loss,
        reproduction_loss=reproduction_loss,
        death_recycled=death_recycled,
        death_loss=death_loss,
        births=births,
        deaths=deaths,
        mutated_loci=mutated_loci,
        clipped_loci=clipped_loci,
        mutated_offspring=mutated_offspring,
    )
