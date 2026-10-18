"""Versioned eight-locus quantitative genome and vectorized phenotype mapping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np
from numpy.typing import NDArray

from genesis.config import EvolutionConfig

GenomeArray = NDArray[np.float64]


class Gene(IntEnum):
    BODY_SIZE = 0
    SPEED = 1
    SENSING = 2
    METABOLISM = 3
    EXPLORATION = 4
    CAUTION = 5
    REPRODUCTION = 6
    EFFICIENCY = 7


GENE_NAMES = tuple(gene.name.lower() for gene in Gene)
GENE_COUNT = len(GENE_NAMES)


@dataclass(frozen=True)
class Phenotype:
    body: GenomeArray
    speed: GenomeArray
    sensing: GenomeArray
    metabolism: GenomeArray
    exploration: GenomeArray
    caution: GenomeArray
    reproduction: GenomeArray
    efficiency: GenomeArray


@dataclass(frozen=True)
class MutationResult:
    genomes: GenomeArray
    mutated_loci: int
    clipped_loci: int
    mutated_offspring: int


def initialize_genomes(
    count: int, config: EvolutionConfig, rng: np.random.Generator
) -> GenomeArray:
    if count < 0:
        raise ValueError("genome count must be nonnegative")
    if config.initial_std == 0:
        return np.full((count, GENE_COUNT), config.initial_mean, dtype=np.float64)
    values = rng.normal(config.initial_mean, config.initial_std, (count, GENE_COUNT))
    return np.clip(values, 0.0, 1.0).astype(np.float64, copy=False)


def express(genomes: GenomeArray) -> Phenotype:
    if genomes.ndim != 2 or genomes.shape[1] != GENE_COUNT:
        raise ValueError(f"genomes must have shape [n,{GENE_COUNT}]")
    # Neutral value 0.5 maps body/metabolism/reproduction/efficiency factors to 1.
    return Phenotype(
        body=0.5 + genomes[:, Gene.BODY_SIZE],
        speed=genomes[:, Gene.SPEED],
        sensing=genomes[:, Gene.SENSING],
        metabolism=0.5 + genomes[:, Gene.METABOLISM],
        exploration=genomes[:, Gene.EXPLORATION],
        caution=genomes[:, Gene.CAUTION],
        reproduction=0.75 + 0.5 * genomes[:, Gene.REPRODUCTION],
        efficiency=0.75 + 0.5 * genomes[:, Gene.EFFICIENCY],
    )


def mutate(
    parent_genomes: GenomeArray,
    config: EvolutionConfig,
    rng: np.random.Generator,
) -> MutationResult:
    if parent_genomes.ndim != 2 or parent_genomes.shape[1] != GENE_COUNT:
        raise ValueError(f"parent genomes must have shape [n,{GENE_COUNT}]")
    children = parent_genomes.copy()
    if not children.size or config.mutation_rate == 0 or config.mutation_sigma == 0:
        return MutationResult(children, 0, 0, 0)
    mask = rng.random(children.shape) < config.mutation_rate
    noise = rng.normal(0.0, config.mutation_sigma, children.shape)
    raw = children + np.where(mask, noise, 0.0)
    clipped = mask & ((raw < 0.0) | (raw > 1.0))
    np.clip(raw, 0.0, 1.0, out=children)
    return MutationResult(
        children,
        mutated_loci=int(mask.sum()),
        clipped_loci=int(clipped.sum()),
        mutated_offspring=int(mask.any(axis=1).sum()),
    )
