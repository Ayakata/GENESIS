"""Reproduce S01-3 determinism and energy-accounting acceptance evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from genesis.config import (
    AgentConfig,
    Config,
    EvolutionConfig,
    RunConfig,
    WorldConfig,
    dump_config,
)


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
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "configs").mkdir()

    base = Config(
        world=WorldConfig(width=64, height=48),
        agents=AgentConfig(initial_count=128, max_population=4096, max_age=240),
        evolution=EvolutionConfig(
            initial_mean=0.5,
            initial_std=0.0,
            mutation_rate=0.0,
            mutation_sigma=0.0,
            sensing_cost=0.0,
            efficiency_cost=0.0,
        ),
        run=RunConfig(steps=300, metrics_interval=25),
    )
    results: dict[str, dict[str, Any]] = {}
    pairs: list[dict[str, Any]] = []
    for boundary in ("closed", "periodic"):
        for seed in (0, 42, 2026):
            config = replace(base, seed=seed, world=replace(base.world, boundary=boundary))
            names = [f"agents_{boundary}_{seed}_{suffix}" for suffix in ("a", "b")]
            for name, hash_seed in zip(names, ("1", "789"), strict=True):
                results[name] = execute(args.output, name, config, hash_seed)
            left, right = (results[name] for name in names)
            deterministic = (
                left["state_digest"] == right["state_digest"]
                and left["metrics"] == right["metrics"]
            )
            pairs.append(
                {
                    "boundary": boundary,
                    "seed": seed,
                    "runs": names,
                    "deterministic": deterministic,
                    "state_digest": left["state_digest"],
                    "population": left["metrics"]["population"],
                }
            )

    metric_rows = [result["metrics"] for result in results.values()]
    report = {
        "runs": len(results),
        "pairs": pairs,
        "all_pairs_deterministic": all(pair["deterministic"] for pair in pairs),
        "max_abs_resource_balance_error": max(abs(row["balance_error"]) for row in metric_rows),
        "max_abs_agent_balance_error": max(abs(row["agent_balance_error"]) for row in metric_rows),
        "max_abs_combined_balance_error": max(
            abs(row["combined_balance_error"]) for row in metric_rows
        ),
        "total_births": sum(row["births"] for row in metric_rows),
        "total_deaths": sum(row["deaths"] for row in metric_rows),
        "limitations": [
            "The temporary agents are predefined mechanisms, not emergent life.",
            "Genetic variation is explicitly disabled to preserve the S01-3 scenario.",
            "Terminal NPZ files are evidence artifacts, not resumable checkpoints.",
        ],
    }
    if not report["all_pairs_deterministic"]:
        raise RuntimeError("Repeated runs diverged")
    if (
        max(
            report["max_abs_resource_balance_error"],
            report["max_abs_agent_balance_error"],
            report["max_abs_combined_balance_error"],
        )
        >= 1e-8
    ):
        raise RuntimeError("Energy ledger tolerance exceeded")
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# S01-3 acceptance report",
        "",
        f"- Independent processes: {report['runs']}",
        f"- Deterministic repeat pairs: {len(pairs)}/{len(pairs)}",
        f"- Maximum resource balance error: {report['max_abs_resource_balance_error']:.3g}",
        f"- Maximum agent balance error: {report['max_abs_agent_balance_error']:.3g}",
        f"- Maximum combined balance error: {report['max_abs_combined_balance_error']:.3g}",
        f"- Births observed across terminal states: {report['total_births']}",
        f"- Deaths observed across terminal states: {report['total_deaths']}",
        "",
        "This verifies deterministic mechanics and accounting, not evolution or emergence.",
    ]
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
