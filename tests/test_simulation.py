from dataclasses import replace

import numpy as np
import pytest

from genesis.config import ConditionsConfig, Config, ResourceConfig, TerrainConfig, WorldConfig
from genesis.core.rng import RandomStreams
from genesis.core.simulation import Simulation
from genesis.lab.metrics import measure


def test_same_seed_same_trajectory_and_chunked_advance():
    config = Config(world=WorldConfig(width=27, height=19))
    a, b = Simulation(config), Simulation(config)
    assert a.state.digest() == b.state.digest()
    a.advance(17)
    b.advance(10)
    b.advance(7)
    assert a.state.digest() == b.state.digest()
    c = Simulation(replace(config, seed=43))
    c.advance(17)
    assert c.state.digest() != a.state.digest()


def test_agent_rng_stream_cannot_change_environment():
    a, b = RandomStreams.from_seed(42), RandomStreams.from_seed(42)
    a.agents.random(10000)
    np.testing.assert_array_equal(a.environment.random(100), b.environment.random(100))


def test_no_shared_arrays_and_no_global_numpy_rng_dependency():
    config = Config()
    a = Simulation(config)
    np.random.seed(1234)
    np.random.random(100)
    b = Simulation(config)
    assert a.state.digest() == b.state.digest()
    a.state.resource[:] = 0
    assert b.state.resource.sum() > 0
    with pytest.raises(ValueError):
        b.state.conditions.light[:] = 0


@pytest.mark.parametrize("boundary", ["closed", "periodic"])
@pytest.mark.parametrize("seed", [0, 1, 42, 2**64 - 1])
def test_long_run_invariants_and_ledger(boundary, seed):
    sim = Simulation(Config(seed=seed, world=WorldConfig(23, 17, boundary)))
    digest_fields = sim.state.conditions.temperature.copy()
    sim.advance(300)
    metrics = measure(sim.state)
    assert abs(metrics["balance_error"]) < 1e-9
    assert sim.state.tick == 300
    assert metrics["source_total"] >= 0 and metrics["sink_total"] >= 0
    np.testing.assert_array_equal(sim.state.conditions.temperature, digest_fields)


def test_one_cell_analytic_source_and_sink():
    sim = Simulation(
        Config(
            world=WorldConfig(1, 1),
            terrain=TerrainConfig(kind="uniform"),
            conditions=ConditionsConfig(
                humidity_min=0.5, humidity_max=0.5, light_min=1, light_max=1
            ),
            resource=ResourceConfig(initial_min=2, initial_max=2, source_rate=4, decay=0.2),
        )
    )
    # R[n+1] = 0.8*(R[n]+2), fixed point 8; R[n] = 8 + (2-8)*0.8**n.
    sim.advance(20)
    assert sim.state.resource[0, 0] == pytest.approx(8 - 6 * 0.8**20)
    assert sim.state.source_total == 40
    assert measure(sim.state)["balance_error"] == pytest.approx(0, abs=1e-13)


def test_no_hidden_source_and_complete_decay():
    base = Config(terrain=TerrainConfig(kind="uniform"))
    closed = Simulation(replace(base, resource=replace(base.resource, source_rate=0, decay=0)))
    total = closed.state.resource.sum()
    closed.advance(500)
    assert closed.state.resource.sum() == pytest.approx(total, abs=1e-10)
    exhausted = Simulation(replace(base, resource=replace(base.resource, source_rate=0, decay=1)))
    exhausted.advance(1)
    assert exhausted.state.resource.sum() == 0
    assert exhausted.state.sink_total == pytest.approx(exhausted.state.initial_total)


def test_empty_world_is_valid_and_has_no_source():
    sim = Simulation(
        Config(
            world=WorldConfig(1, 1),
            terrain=TerrainConfig(islands=1, radius=0.000001, sea_level=0.99, noise=0),
        )
    )
    sim.advance(5)
    assert not sim.state.conditions.land.any()
    assert sim.state.resource.sum() == sim.state.source_total == sim.state.sink_total == 0


@pytest.mark.parametrize("steps", [-1, 1.5, True])
def test_invalid_advance_rejected(steps):
    with pytest.raises(ValueError):
        Simulation(Config()).advance(steps)
