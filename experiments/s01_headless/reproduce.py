"""Reproduce S01-5 batch determinism and headless throughput evidence."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from genesis.config import AgentConfig, Config, RunConfig, TerrainConfig, WorldConfig, dump_config


def invoke(arguments: list[str], *, timeout: int = 300) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "genesis", *arguments],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"genesis {' '.join(arguments)} failed:\n{result.stdout}\n{result.stderr}"
        )
    value: dict[str, Any] = json.loads(result.stdout)
    return value


def scientific_signature(report: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (item["index"], item["scenario"], item["seed"], item["state_digest"], item["metrics"])
        for item in report["results"]
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configs = args.output / "configs"
    configs.mkdir()

    base = Config(
        world=WorldConfig(width=48, height=32, boundary="closed"),
        terrain=TerrainConfig(kind="uniform"),
        agents=AgentConfig(initial_count=96, max_population=2048, max_age=250),
        run=RunConfig(steps=120, metrics_interval=20),
    )
    scenarios = {
        "closed": base,
        "periodic": replace(base, world=replace(base.world, boundary="periodic")),
    }
    scenario_arguments: list[str] = []
    for name, config in scenarios.items():
        path = configs / f"{name}.yaml"
        path.write_text(dump_config(config), encoding="utf-8")
        scenario_arguments.extend(("--scenario", f"{name}={path}"))

    common = [*scenario_arguments, "--seeds", "0", "42", "2026"]
    serial = invoke(["batch", *common, "--jobs", "1", "--output", str(args.output / "serial")])
    parallel = invoke(["batch", *common, "--jobs", "2", "--output", str(args.output / "parallel")])
    performance = invoke(
        [
            "benchmark",
            "--config",
            str(configs / "periodic.yaml"),
            "--steps",
            "200",
            "--warmup",
            "20",
            "--repeats",
            "3",
            "--output",
            str(args.output / "benchmark"),
        ]
    )

    parallel_match = scientific_signature(serial) == scientific_signature(parallel)
    results = serial["results"]
    max_balance = max(abs(item["metrics"]["combined_balance_error"]) for item in results)
    manifests_complete = all(
        json.loads(
            (
                args.output
                / "serial"
                / "runs"
                / item["scenario"]
                / f"seed-{item['seed']}"
                / "manifest.json"
            ).read_text()
        )["status"]
        == "completed"
        for item in results
    )
    report = {
        "tasks_per_batch": serial["task_count"],
        "scenario_count": len(scenarios),
        "seeds": [0, 42, 2026],
        "serial_parallel_scientific_match": parallel_match,
        "stable_result_order": [item["index"] for item in parallel["results"]]
        == list(range(parallel["task_count"])),
        "all_run_manifests_complete": manifests_complete,
        "max_abs_combined_balance_error": max_balance,
        "serial_elapsed_seconds": serial["elapsed_seconds"],
        "parallel_elapsed_seconds": parallel["elapsed_seconds"],
        "parallel_speedup": serial["elapsed_seconds"] / parallel["elapsed_seconds"],
        "serial_aggregate_ticks_per_second": serial["aggregate_ticks_per_second"],
        "parallel_aggregate_ticks_per_second": parallel["aggregate_ticks_per_second"],
        "benchmark_median_ticks_per_second": performance["median_ticks_per_second"],
        "benchmark_min_ticks_per_second": performance["min_ticks_per_second"],
        "benchmark_max_ticks_per_second": performance["max_ticks_per_second"],
        "benchmark_repeats_same_digest": len(
            {sample["state_digest"] for sample in performance["samples"]}
        )
        == 1,
        "limitations": [
            "Wall-clock throughput is machine-specific and is not part of scientific state.",
            "Process parallelism is accepted for isolation and capacity; speedup is "
            "measured, not assumed.",
            "Each batch task currently writes full artifacts; resumable checkpoints remain S01-6.",
        ],
    }
    required = (
        report["tasks_per_batch"] == 6,
        report["serial_parallel_scientific_match"],
        report["stable_result_order"],
        report["all_run_manifests_complete"],
        report["max_abs_combined_balance_error"] < 1e-8,
        report["benchmark_repeats_same_digest"],
        math.isfinite(report["benchmark_median_ticks_per_second"]),
        report["benchmark_median_ticks_per_second"] > 0,
    )
    if not all(required):
        raise RuntimeError(f"S01-5 acceptance failed: {report}")

    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# S01-5 acceptance report",
        "",
        f"- Tasks per batch: {report['tasks_per_batch']}",
        f"- Serial/parallel scientific match: {report['serial_parallel_scientific_match']}",
        f"- Stable result order: {report['stable_result_order']}",
        f"- Maximum combined balance error: {report['max_abs_combined_balance_error']:.3g}",
        f"- Serial aggregate throughput: {report['serial_aggregate_ticks_per_second']:.3f} ticks/s",
        "- Parallel aggregate throughput: "
        f"{report['parallel_aggregate_ticks_per_second']:.3f} ticks/s",
        f"- Observed two-process speedup: {report['parallel_speedup']:.3f}x",
        f"- In-memory benchmark median: {report['benchmark_median_ticks_per_second']:.3f} ticks/s",
        "",
        "Throughput is a platform baseline, not a scientific invariant or acceptance threshold.",
    ]
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
