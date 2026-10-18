"""Local agent rules with explicit transfers and action costs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from genesis.agents.state import AgentLedger, AgentState
from genesis.config import AgentConfig, Config
from genesis.core.state import WorldState


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


def initialize_population(
    world: WorldState, config: AgentConfig, rng: np.random.Generator
) -> tuple[AgentState, AgentLedger]:
    population = AgentState.empty(config.max_population)
    if config.initial_count:
        land_y, land_x = np.nonzero(world.conditions.land)
        if not land_x.size:
            raise RuntimeError("Cannot place initial agents: world has no land")
        selected = rng.integers(0, land_x.size, size=config.initial_count)
        population.add(
            land_x[selected].astype(np.int32),
            land_y[selected].astype(np.int32),
            np.full(config.initial_count, config.initial_energy, dtype=np.float64),
            np.full(config.initial_count, -1, dtype=np.int64),
        )
    ledger = AgentLedger(initial_energy=config.initial_count * config.initial_energy)
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
    if not count or config.agents.move_cost == 0 and world.resource.size == 1:
        return 0.0
    directions = rng.integers(0, 4, size=count)
    dx = np.array([1, 0, -1, 0], dtype=np.int32)[directions]
    dy = np.array([0, 1, 0, -1], dtype=np.int32)[directions]
    old_x = population.x[:count]
    old_y = population.y[:count]
    new_x = old_x + dx
    new_y = old_y + dy
    height, width = world.resource.shape
    if config.world.boundary == "periodic":
        new_x %= width
        new_y %= height
        valid = world.conditions.land[new_y, new_x]
    else:
        inside = (new_x >= 0) & (new_x < width) & (new_y >= 0) & (new_y < height)
        valid = np.zeros(count, dtype=np.bool_)
        valid[inside] = world.conditions.land[new_y[inside], new_x[inside]]
    can_pay = population.energy[:count] >= config.agents.move_cost
    moved = valid & can_pay & ((new_x != old_x) | (new_y != old_y))
    population.x[:count][moved] = new_x[moved]
    population.y[:count][moved] = new_y[moved]
    loss = float(moved.sum()) * config.agents.move_cost
    population.energy[:count][moved] -= config.agents.move_cost
    return loss


def _feed(world: WorldState, population: AgentState, config: AgentConfig) -> tuple[float, float]:
    count = population.count
    if not count or config.intake_rate == 0:
        return 0.0, 0.0
    height, width = world.resource.shape
    flat_cells = population.y[:count].astype(np.int64) * width + population.x[:count]
    occupants = np.bincount(flat_cells, minlength=height * width)
    flat_resource = world.resource.reshape(-1)
    cell_consumed = np.minimum(flat_resource, occupants * config.intake_rate)
    per_agent = cell_consumed[flat_cells] / occupants[flat_cells]
    flat_resource -= cell_consumed
    population.energy[:count] += per_agent * config.assimilation_efficiency
    consumed = float(cell_consumed.sum(dtype=np.float64))
    assimilated = consumed * config.assimilation_efficiency
    world.transfer_out_total += consumed
    return consumed, assimilated


def _reproduce(
    population: AgentState, config: AgentConfig, rng: np.random.Generator
) -> tuple[int, float]:
    current = population.count
    slots = population.capacity - current
    if not current or slots <= 0:
        return 0, 0.0
    eligible = np.flatnonzero(population.energy[:current] >= config.reproduction_threshold)
    if eligible.size > slots:
        eligible = np.sort(rng.choice(eligible, size=slots, replace=False))
    births = int(eligible.size)
    if not births:
        return 0, 0.0
    population.energy[eligible] -= config.offspring_energy + config.reproduction_cost
    population.add(
        population.x[eligible].copy(),
        population.y[eligible].copy(),
        np.full(births, config.offspring_energy, dtype=np.float64),
        population.ids[eligible].copy(),
    )
    return births, births * config.reproduction_cost


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
    config: Config,
    rng: np.random.Generator,
) -> AgentFlux:
    """Advance agents once after the environment update for the same world tick."""
    count = population.count
    population.age[:count] += 1
    basal = np.minimum(population.energy[:count], config.agents.basal_cost)
    population.energy[:count] -= basal
    basal_loss = float(basal.sum(dtype=np.float64))
    movement_loss = _move(world, population, config, rng)
    consumed, assimilated = _feed(world, population, config.agents)
    births, reproduction_loss = _reproduce(population, config.agents, rng)
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
    )
