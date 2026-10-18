from dataclasses import replace

import numpy as np
import pytest

from genesis.agents.metrics import measure_sandbox
from genesis.agents.simulation import SandboxSimulation
from genesis.config import AgentConfig, Config, ResourceConfig, TerrainConfig, WorldConfig


def uniform_config(agents: AgentConfig, *, width: int = 1, height: int = 1) -> Config:
    return Config(
        world=WorldConfig(width, height),
        terrain=TerrainConfig(kind="uniform"),
        resource=ResourceConfig(
            initial_min=10.0,
            initial_max=10.0,
            source_rate=0.0,
            diffusion=0.0,
            decay=0.0,
        ),
        agents=agents,
    )


def test_population_is_typed_soa_and_seeded_on_land():
    config = Config(
        seed=19,
        world=WorldConfig(31, 23),
        agents=AgentConfig(initial_count=100, max_population=200),
    )
    sim = SandboxSimulation(config)
    assert sim.agents.count == 100
    assert sim.agents.capacity == 200
    assert sim.agents.ids.dtype == np.int64
    assert sim.agents.x.dtype == sim.agents.y.dtype == np.int32
    assert sim.agents.energy.dtype == np.float64
    assert sim.agents.age.dtype == np.uint32
    assert all(
        array.dtype != object for array in vars(sim.agents).values() if hasattr(array, "dtype")
    )
    assert sim.world.conditions.land[
        sim.agents.y[: sim.agents.count], sim.agents.x[: sim.agents.count]
    ].all()


def test_feeding_and_action_costs_have_analytic_ledger():
    agents = AgentConfig(
        initial_count=1,
        max_population=10,
        initial_energy=2.0,
        basal_cost=0.5,
        move_cost=0.0,
        intake_rate=1.0,
        assimilation_efficiency=0.75,
        reproduction_threshold=100.0,
        offspring_energy=1.0,
        reproduction_cost=0.0,
        max_age=100,
    )
    sim = SandboxSimulation(uniform_config(agents))
    flux = sim.step().agents
    assert flux.consumed == pytest.approx(1.0)
    assert flux.assimilated == pytest.approx(0.75)
    assert flux.basal_loss == pytest.approx(0.5)
    assert sim.world.resource.item() == pytest.approx(9.0)
    assert sim.agents.energy[0] == pytest.approx(2.25)
    metrics = measure_sandbox(sim.world, sim.agents, sim.agent_ledger)
    assert metrics["balance_error"] == pytest.approx(0.0)
    assert metrics["agent_balance_error"] == pytest.approx(0.0)
    assert metrics["combined_balance_error"] == pytest.approx(0.0)


def test_cell_resource_is_shared_without_overconsumption():
    agents = AgentConfig(
        initial_count=4,
        max_population=4,
        initial_energy=1.0,
        basal_cost=0.0,
        move_cost=0.0,
        intake_rate=4.0,
        assimilation_efficiency=1.0,
        reproduction_threshold=100.0,
        offspring_energy=1.0,
        reproduction_cost=0.0,
        max_age=100,
    )
    config = replace(
        uniform_config(agents),
        resource=ResourceConfig(
            initial_min=2.0,
            initial_max=2.0,
            source_rate=0.0,
            diffusion=0.0,
            decay=0.0,
        ),
    )
    sim = SandboxSimulation(config)
    sim.step()
    np.testing.assert_allclose(sim.agents.energy[:4], 1.5)
    assert sim.world.resource.item() == 0.0
    assert sim.agent_ledger.consumed == 2.0


def test_reproduction_transfers_energy_and_records_cost_and_parentage():
    agents = AgentConfig(
        initial_count=1,
        max_population=4,
        initial_energy=10.0,
        basal_cost=0.0,
        move_cost=0.0,
        intake_rate=0.0,
        assimilation_efficiency=1.0,
        reproduction_threshold=10.0,
        offspring_energy=3.0,
        reproduction_cost=1.0,
        max_age=100,
    )
    sim = SandboxSimulation(uniform_config(agents))
    flux = sim.step().agents
    assert flux.births == 1
    assert sim.agents.count == 2
    np.testing.assert_array_equal(sim.agents.parent_ids[:2], [-1, 0])
    np.testing.assert_allclose(sim.agents.energy[:2], [6.0, 3.0])
    assert sim.agent_ledger.reproduction_loss == 1.0
    assert measure_sandbox(sim.world, sim.agents, sim.agent_ledger)[
        "combined_balance_error"
    ] == pytest.approx(0.0)


def test_age_death_recycles_configured_fraction_and_compacts():
    agents = AgentConfig(
        initial_count=1,
        max_population=4,
        initial_energy=8.0,
        basal_cost=0.0,
        move_cost=0.0,
        intake_rate=0.0,
        assimilation_efficiency=1.0,
        reproduction_threshold=100.0,
        offspring_energy=1.0,
        reproduction_cost=0.0,
        max_age=1,
        death_recycle_fraction=0.25,
    )
    config = replace(
        uniform_config(agents),
        resource=ResourceConfig(
            initial_min=0.0,
            initial_max=0.0,
            source_rate=0.0,
            diffusion=0.0,
            decay=0.0,
        ),
    )
    sim = SandboxSimulation(config)
    flux = sim.step().agents
    assert flux.deaths == 1 and sim.agents.count == 0
    assert sim.world.resource.item() == pytest.approx(2.0)
    assert sim.agent_ledger.death_recycled == pytest.approx(2.0)
    assert sim.agent_ledger.death_loss == pytest.approx(6.0)
    assert measure_sandbox(sim.world, sim.agents, sim.agent_ledger)[
        "combined_balance_error"
    ] == pytest.approx(0.0)


def test_movement_stays_on_land_and_charges_only_successful_moves():
    agents = AgentConfig(
        initial_count=100,
        max_population=100,
        initial_energy=10.0,
        basal_cost=0.0,
        move_cost=0.25,
        intake_rate=0.0,
        assimilation_efficiency=1.0,
        reproduction_threshold=100.0,
        offspring_energy=1.0,
        reproduction_cost=0.0,
        max_age=100,
    )
    config = replace(uniform_config(agents, width=5, height=4), world=WorldConfig(5, 4, "periodic"))
    sim = SandboxSimulation(config)
    sim.step()
    assert sim.agent_ledger.movement_loss == pytest.approx(25.0)
    assert sim.world.conditions.land[sim.agents.y[:100], sim.agents.x[:100]].all()


def test_same_seed_same_agent_trajectory_and_chunking():
    config = Config(
        seed=2026,
        world=WorldConfig(29, 17, "periodic"),
        agents=AgentConfig(initial_count=80, max_population=1000),
    )
    a, b = SandboxSimulation(config), SandboxSimulation(config)
    np.random.seed(9001)
    np.random.random(1000)
    a.advance(75)
    b.advance(30)
    b.advance(45)
    assert a.digest() == b.digest()
    assert measure_sandbox(a.world, a.agents, a.agent_ledger) == measure_sandbox(
        b.world, b.agents, b.agent_ledger
    )


@pytest.mark.parametrize("boundary", ["closed", "periodic"])
@pytest.mark.parametrize("seed", [0, 42, 2**64 - 1])
def test_long_run_agent_and_combined_energy_invariants(boundary, seed):
    sim = SandboxSimulation(
        Config(
            seed=seed,
            world=WorldConfig(27, 19, boundary),
            agents=AgentConfig(initial_count=60, max_population=1000, max_age=120),
        )
    )
    sim.advance(250)
    metrics = measure_sandbox(sim.world, sim.agents, sim.agent_ledger)
    assert abs(metrics["balance_error"]) < 1e-9
    assert abs(metrics["agent_balance_error"]) < 1e-9
    assert abs(metrics["combined_balance_error"]) < 1e-9
    assert 0 <= sim.agents.count <= sim.agents.capacity


def test_initial_agents_require_land():
    config = Config(
        world=WorldConfig(1, 1),
        terrain=TerrainConfig(islands=1, radius=0.000001, sea_level=0.99, noise=0),
        agents=AgentConfig(initial_count=1, max_population=1),
    )
    with pytest.raises(RuntimeError, match="no land"):
        SandboxSimulation(config)
