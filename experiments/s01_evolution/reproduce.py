"""Reproduce S01-4 inheritance, mutation and bounded-variation evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from genesis.config import AgentConfig, Config, EvolutionConfig, RunConfig, WorldConfig, dump_config
from genesis.evolution.genome import GENE_COUNT


def execute(root: Path, name: str, config: Config, hash_seed: str) -> dict[str, Any]:
    config_path = root / "configs" / f"{name}.yaml"
    config_path.write_text(dump_config(config), encoding="utf-8")
    output = root / name
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "genesis",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{name} failed:\n{result.stdout}\n{result.stderr}")
    summary: dict[str, Any] = json.loads(result.stdout)
    with np.load(output / "final_state.npz", allow_pickle=False) as state:
        genome = state["agent_genome"]
        summary["genome_min"] = float(genome.min()) if genome.size else 0.0
        summary["genome_max"] = float(genome.max()) if genome.size else 0.0
        summary["final_unique_genomes"] = int(np.unique(genome, axis=0).shape[0])
    rows = [json.loads(line) for line in (output / "metrics.jsonl").read_text().splitlines()]
    summary["max_population"] = max(row["population"] for row in rows)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "configs").mkdir()

    base = Config(
        world=WorldConfig(width=64, height=48, boundary="periodic"),
        agents=AgentConfig(initial_count=128, max_population=4096, max_age=300),
        evolution=EvolutionConfig(
            initial_mean=0.5,
            initial_std=0.0,
            mutation_rate=0.0,
            mutation_sigma=0.12,
        ),
        run=RunConfig(steps=300, metrics_interval=25),
    )
    scenarios = {
        "control": base,
        "mutation": replace(
            base,
            evolution=replace(base.evolution, mutation_rate=0.15),
        ),
    }
    results: dict[str, dict[str, Any]] = {}
    pairs: list[dict[str, Any]] = []
    for scenario, template in scenarios.items():
        for seed in (0, 42, 2026):
            config = replace(template, seed=seed)
            names = [f"{scenario}_{seed}_{suffix}" for suffix in ("a", "b")]
            for name, hash_seed in zip(names, ("1", "789"), strict=True):
                results[name] = execute(args.output, name, config, hash_seed)
            left, right = (results[name] for name in names)
            deterministic = (
                left["state_digest"] == right["state_digest"]
                and left["metrics"] == right["metrics"]
            )
            pairs.append(
                {
                    "scenario": scenario,
                    "seed": seed,
                    "runs": names,
                    "deterministic": deterministic,
                    "state_digest": left["state_digest"],
                    "population": left["metrics"]["population"],
                    "births": left["metrics"]["births"],
                    "mutated_loci": left["metrics"]["mutated_loci"],
                    "genetic_variance_mean": left["metrics"]["genetic_variance_mean"],
                    "final_unique_genomes": left["final_unique_genomes"],
                }
            )

    primary = [results[f"{scenario}_{seed}_a"] for scenario in scenarios for seed in (0, 42, 2026)]
    controls = [results[f"control_{seed}_a"] for seed in (0, 42, 2026)]
    mutations = [results[f"mutation_{seed}_a"] for seed in (0, 42, 2026)]
    report = {
        "runs": len(results),
        "pairs": pairs,
        "all_pairs_deterministic": all(pair["deterministic"] for pair in pairs),
        "control_exact_inheritance": all(
            row["metrics"]["mutated_loci"] == 0
            and row["metrics"]["genetic_variance_mean"] == 0
            and row["final_unique_genomes"] <= 1
            for row in controls
        ),
        "mutation_created_bounded_variation": all(
            row["metrics"]["mutated_loci"] > 0
            and row["metrics"]["genetic_variance_mean"] > 0
            and row["final_unique_genomes"] > 1
            and 0 <= row["genome_min"] <= row["genome_max"] <= 1
            for row in mutations
        ),
        "population_cap_not_reached": all(
            row["max_population"] < base.agents.max_population for row in primary
        ),
        "max_abs_combined_balance_error": max(
            abs(row["metrics"]["combined_balance_error"]) for row in primary
        ),
        "total_primary_births": sum(row["metrics"]["births"] for row in primary),
        "total_primary_mutated_loci": sum(row["metrics"]["mutated_loci"] for row in primary),
        "gene_count": GENE_COUNT,
        "limitations": [
            "This validates inheritance mechanics, not adaptive evolution.",
            "Trait distributions are not compared between selective environments until S01-8.",
            "The agents and reproduction operation remain predefined sandbox mechanisms.",
        ],
    }
    required = (
        report["all_pairs_deterministic"],
        report["control_exact_inheritance"],
        report["mutation_created_bounded_variation"],
        report["population_cap_not_reached"],
        report["max_abs_combined_balance_error"] < 1e-8,
        report["total_primary_births"] > 0,
    )
    if not all(required):
        raise RuntimeError(f"S01-4 acceptance failed: {report}")
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# S01-4 acceptance report",
        "",
        f"- Independent processes: {report['runs']}",
        f"- Deterministic repeat pairs: {len(pairs)}/{len(pairs)}",
        f"- Exact no-mutation inheritance: {report['control_exact_inheritance']}",
        f"- Bounded mutation variation: {report['mutation_created_bounded_variation']}",
        f"- Population cap untouched: {report['population_cap_not_reached']}",
        f"- Maximum combined balance error: {report['max_abs_combined_balance_error']:.3g}",
        f"- Births across primary runs: {report['total_primary_births']}",
        f"- Mutated loci across primary runs: {report['total_primary_mutated_loci']}",
        "",
        "This verifies inheritance and mutation mechanics, not adaptation or emergence.",
    ]
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
