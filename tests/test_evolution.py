from dataclasses import replace

import numpy as np

from genesis.agents.simulation import SandboxSimulation
from genesis.config import (
    AgentConfig,
    Config,
    EvolutionConfig,
    ResourceConfig,
    TerrainConfig,
    WorldConfig,
)
from genesis.evolution.genome import (
    GENE_COUNT,
    GENE_NAMES,
    Gene,
    express,
    initialize_genomes,
    mutate,
)


def sandbox_config(
    *,
    count: int = 1,
    width: int = 1,
    height: int = 1,
    energy: float = 10.0,
    basal: float = 0.0,
    move: float = 0.0,
    intake: float = 0.0,
    assimilation: float = 1.0,
    reproduction_threshold: float = 100.0,
    offspring_energy: float = 1.0,
    reproduction_cost: float = 0.0,
    evolution: EvolutionConfig | None = None,
) -> Config:
    return Config(
        seed=17,
        world=WorldConfig(width, height, "periodic"),
        terrain=TerrainConfig(kind="uniform"),
        resource=ResourceConfig(
            initial_min=100.0,
            initial_max=100.0,
            source_rate=0.0,
            diffusion=0.0,
            decay=0.0,
        ),
        agents=AgentConfig(
            initial_count=count,
            max_population=max(2 * count, 4),
            initial_energy=energy,
            basal_cost=basal,
            move_cost=move,
            intake_rate=intake,
            assimilation_efficiency=assimilation,
            reproduction_threshold=reproduction_threshold,
            offspring_energy=offspring_energy,
            reproduction_cost=reproduction_cost,
            max_age=1000,
        ),
        evolution=evolution
        or EvolutionConfig(
            initial_mean=0.5,
            initial_std=0.0,
            mutation_rate=0.0,
            mutation_sigma=0.0,
            sensing_cost=0.0,
            efficiency_cost=0.0,
        ),
    )


def set_genes(sim: SandboxSimulation, **values: float) -> None:
    for name, value in values.items():
        sim.agents.genome[: sim.agents.count, Gene[name.upper()]] = value


def test_genome_schema_and_phenotype_bounds():
    assert GENE_COUNT == 8
    assert GENE_NAMES == (
        "body_size",
        "speed",
        "sensing",
        "metabolism",
        "exploration",
        "caution",
        "reproduction",
        "efficiency",
    )
    genomes = np.vstack((np.zeros(GENE_COUNT), np.full(GENE_COUNT, 0.5), np.ones(GENE_COUNT)))
    traits = express(genomes)
    np.testing.assert_allclose(traits.body, [0.5, 1.0, 1.5])
    np.testing.assert_allclose(traits.metabolism, [0.5, 1.0, 1.5])
    np.testing.assert_allclose(traits.reproduction, [0.75, 1.0, 1.25])
    np.testing.assert_allclose(traits.efficiency, [0.75, 1.0, 1.25])


def test_seeded_initial_genomes_are_bounded_and_reproducible():
    config = EvolutionConfig(initial_mean=0.5, initial_std=0.3)
    a = initialize_genomes(1000, config, np.random.default_rng(42))
    b = initialize_genomes(1000, config, np.random.default_rng(42))
    np.testing.assert_array_equal(a, b)
    assert a.shape == (1000, GENE_COUNT)
    assert a.dtype == np.float64
    assert a.min() == 0.0 and a.max() == 1.0


def test_zero_mutation_is_exact_inheritance_and_consumes_no_rng():
    parents = np.random.default_rng(1).random((20, GENE_COUNT))
    config = EvolutionConfig(mutation_rate=0.0, mutation_sigma=0.5)
    a, b = np.random.default_rng(9), np.random.default_rng(9)
    result = mutate(parents, config, a)
    np.testing.assert_array_equal(result.genomes, parents)
    assert result.mutated_loci == result.clipped_loci == result.mutated_offspring == 0
    np.testing.assert_array_equal(a.random(20), b.random(20))


def test_mutation_is_per_locus_bounded_and_counted():
    parents = np.vstack((np.zeros((10, GENE_COUNT)), np.ones((10, GENE_COUNT))))
    result = mutate(
        parents,
        EvolutionConfig(mutation_rate=1.0, mutation_sigma=4.0),
        np.random.default_rng(2026),
    )
    assert result.mutated_loci == parents.size
    assert result.mutated_offspring == parents.shape[0]
    assert 0 < result.clipped_loci <= result.mutated_loci
    assert np.isfinite(result.genomes).all()
    assert result.genomes.min() >= 0 and result.genomes.max() <= 1


def test_reproduction_preserves_parent_genome_when_mutation_disabled():
    sim = SandboxSimulation(
        sandbox_config(
            energy=20,
            reproduction_threshold=10,
            offspring_energy=3,
            reproduction_cost=1,
            evolution=EvolutionConfig(
                initial_std=0.2,
                mutation_rate=0.0,
                sensing_cost=0.0,
                efficiency_cost=0.0,
            ),
        )
    )
    parent = sim.agents.genome[0].copy()
    flux = sim.step().agents
    assert flux.births == 1 and sim.agents.count == 2
    assert sim.agents.parent_ids[1] == sim.agents.ids[0]
    np.testing.assert_array_equal(sim.agents.genome[1], parent)
    assert flux.mutated_loci == 0


def test_reproduction_mutates_child_and_updates_ledger():
    sim = SandboxSimulation(
        sandbox_config(
            energy=10,
            reproduction_threshold=10,
            offspring_energy=3,
            reproduction_cost=1,
            evolution=EvolutionConfig(
                initial_mean=0.5,
                initial_std=0.0,
                mutation_rate=1.0,
                mutation_sigma=0.2,
                sensing_cost=0.0,
                efficiency_cost=0.0,
            ),
        )
    )
    flux = sim.step().agents
    assert flux.births == 1 and flux.mutated_loci == GENE_COUNT
    assert flux.mutated_offspring == 1
    assert sim.evolution_ledger.mutated_loci == GENE_COUNT
    assert not np.array_equal(sim.agents.genome[0], sim.agents.genome[1])
    assert (sim.agents.genome[:2] >= 0).all() and (sim.agents.genome[:2] <= 1).all()


def test_metabolism_increases_intake_and_maintenance_cost():
    low = SandboxSimulation(sandbox_config(basal=0.1, intake=1.0))
    high = SandboxSimulation(sandbox_config(basal=0.1, intake=1.0))
    set_genes(low, metabolism=0.0)
    set_genes(high, metabolism=1.0)
    low_flux, high_flux = low.step().agents, high.step().agents
    assert high_flux.basal_loss > low_flux.basal_loss
    assert high_flux.consumed > low_flux.consumed
    assert high.agents.energy[0] > low.agents.energy[0]


def test_efficiency_increases_assimilation_but_has_quadratic_cost():
    evolution = EvolutionConfig(
        initial_std=0.0,
        mutation_rate=0.0,
        sensing_cost=0.0,
        efficiency_cost=0.2,
    )
    low = SandboxSimulation(sandbox_config(intake=1.0, assimilation=0.5, evolution=evolution))
    high = SandboxSimulation(sandbox_config(intake=1.0, assimilation=0.5, evolution=evolution))
    set_genes(low, efficiency=0.0)
    set_genes(high, efficiency=1.0)
    low_flux, high_flux = low.step().agents, high.step().agents
    assert high_flux.assimilated > low_flux.assimilated
    assert high_flux.basal_loss > low_flux.basal_loss


def test_speed_and_exploration_increase_movement_and_speed_cost():
    config = sandbox_config(count=1000, width=20, height=20, move=1.0, energy=100.0)
    slow = SandboxSimulation(config)
    fast = SandboxSimulation(config)
    set_genes(slow, speed=0.0, exploration=0.0, sensing=0.0, caution=0.0)
    set_genes(fast, speed=1.0, exploration=1.0, sensing=0.0, caution=0.0)
    slow_x, slow_y = slow.agents.x[:1000].copy(), slow.agents.y[:1000].copy()
    fast_x, fast_y = fast.agents.x[:1000].copy(), fast.agents.y[:1000].copy()
    slow.step()
    fast.step()
    slow_moved = ((slow.agents.x[:1000] != slow_x) | (slow.agents.y[:1000] != slow_y)).sum()
    fast_moved = ((fast.agents.x[:1000] != fast_x) | (fast.agents.y[:1000] != fast_y)).sum()
    assert fast_moved > 5 * slow_moved
    assert fast.agent_ledger.movement_loss > slow.agent_ledger.movement_loss


def test_sensing_finds_richer_neighbour_and_has_maintenance_cost():
    evolution = EvolutionConfig(
        initial_std=0.0,
        mutation_rate=0.0,
        sensing_cost=0.2,
        efficiency_cost=0.0,
    )
    config = sandbox_config(count=200, width=5, height=5, evolution=evolution)
    blind, sensing = SandboxSimulation(config), SandboxSimulation(config)
    for sim in (blind, sensing):
        sim.agents.x[:200] = 2
        sim.agents.y[:200] = 2
        sim.world.resource[:] = 0
        sim.world.resource[2, 3] = 100
        set_genes(sim, speed=1.0, exploration=1.0, caution=0.0)
    set_genes(blind, sensing=0.0)
    set_genes(sensing, sensing=1.0)
    blind.step()
    sensing.step()
    assert (sensing.agents.x[:200] == 3).all() and (sensing.agents.y[:200] == 2).all()
    assert (blind.agents.x[:200] == 3).sum() < 100
    assert sensing.agent_ledger.basal_loss > blind.agent_ledger.basal_loss


def test_caution_conserves_low_energy_by_reducing_movement():
    config = sandbox_config(count=1000, width=20, height=20, move=0.1, energy=1.0)
    bold, cautious = SandboxSimulation(config), SandboxSimulation(config)
    set_genes(bold, speed=1.0, exploration=1.0, sensing=0.0, caution=0.0)
    set_genes(cautious, speed=1.0, exploration=1.0, sensing=0.0, caution=1.0)
    bold.step()
    cautious.step()
    assert bold.agent_ledger.movement_loss > 3 * cautious.agent_ledger.movement_loss


def test_reproduction_gene_trades_early_birth_against_parent_reserve():
    config = sandbox_config(
        energy=9.0,
        reproduction_threshold=10.0,
        offspring_energy=3.0,
        reproduction_cost=1.0,
    )
    early, delayed = SandboxSimulation(config), SandboxSimulation(config)
    set_genes(early, reproduction=0.0)
    set_genes(delayed, reproduction=1.0)
    assert early.step().agents.births == 1
    assert delayed.step().agents.births == 0
    assert delayed.agents.energy[0] > early.agents.energy[0]


def test_body_size_increases_intake_maintenance_and_offspring_investment():
    config = sandbox_config(
        energy=100,
        basal=0.1,
        intake=1.0,
        reproduction_threshold=10,
        offspring_energy=4,
        reproduction_cost=1,
    )
    small, large = SandboxSimulation(config), SandboxSimulation(config)
    set_genes(small, body_size=0.0)
    set_genes(large, body_size=1.0)
    small_flux, large_flux = small.step().agents, large.step().agents
    assert large_flux.consumed > small_flux.consumed
    assert large_flux.basal_loss > small_flux.basal_loss
    assert large.agents.energy[1] > small.agents.energy[1]
    assert large_flux.reproduction_loss > small_flux.reproduction_loss


def test_evolutionary_trajectory_is_seeded_and_hash_independent():
    config = replace(
        sandbox_config(count=50, width=13, height=11, intake=0.4, basal=0.02),
        evolution=EvolutionConfig(
            initial_mean=0.5,
            initial_std=0.1,
            mutation_rate=0.2,
            mutation_sigma=0.15,
        ),
    )
    a, b = SandboxSimulation(config), SandboxSimulation(config)
    np.random.seed(12345)
    np.random.random(1000)
    a.advance(100)
    b.advance(40)
    b.advance(60)
    assert a.digest() == b.digest()
    np.testing.assert_array_equal(
        a.agents.genome[: a.agents.count], b.agents.genome[: b.agents.count]
    )
    assert a.evolution_ledger == b.evolution_ledger
