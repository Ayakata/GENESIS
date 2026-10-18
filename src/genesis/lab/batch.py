"""Deterministic scenario/seed matrices with optional process parallelism."""

from __future__ import annotations

import multiprocessing
import re
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any

from genesis.config import Config
from genesis.history.artifacts import provenance, write_json
from genesis.lab.runner import run_artifact

BATCH_SCHEMA_VERSION = 1
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class BatchScenario:
    """A named base configuration to execute for every requested seed."""

    name: str
    config: Config


@dataclass(frozen=True)
class _BatchTask:
    index: int
    scenario: str
    seed: int
    config: Config
    relative_output: str


def _validate(
    scenarios: Sequence[BatchScenario], seeds: Sequence[int], jobs: int
) -> tuple[_BatchTask, ...]:
    if not scenarios:
        raise ValueError("at least one batch scenario is required")
    if not seeds:
        raise ValueError("at least one batch seed is required")
    if type(jobs) is not int or not 1 <= jobs <= 64:
        raise ValueError("jobs must be an integer in [1,64]")
    names = [scenario.name for scenario in scenarios]
    if len(set(names)) != len(names):
        raise ValueError("batch scenario names must be unique")
    invalid_names = [name for name in names if _SAFE_NAME.fullmatch(name) is None]
    if invalid_names:
        raise ValueError(f"unsafe batch scenario name: {invalid_names[0]!r}")
    if any(type(seed) is not int or not 0 <= seed < 2**64 for seed in seeds):
        raise ValueError("batch seeds must be integers in [0,2**64)")
    if len(set(seeds)) != len(seeds):
        raise ValueError("batch seeds must be unique")
    if len(scenarios) * len(seeds) > 10_000:
        raise ValueError("batch is limited to 10000 tasks")

    tasks: list[_BatchTask] = []
    for scenario in scenarios:
        for seed in seeds:
            tasks.append(
                _BatchTask(
                    index=len(tasks),
                    scenario=scenario.name,
                    seed=seed,
                    config=replace(scenario.config, seed=seed),
                    relative_output=f"runs/{scenario.name}/seed-{seed}",
                )
            )
    return tuple(tasks)


def _execute_task(task: _BatchTask, output: Path) -> dict[str, Any]:
    summary = run_artifact(task.config, output / task.relative_output)
    elapsed = float(summary["elapsed_seconds"])
    return {
        "index": task.index,
        "scenario": task.scenario,
        "seed": task.seed,
        "output": task.relative_output,
        "steps": task.config.run.steps,
        "elapsed_seconds": elapsed,
        "ticks_per_second": task.config.run.steps / elapsed,
        "state_digest": summary["state_digest"],
        "metrics": summary["metrics"],
    }


def run_batch(
    scenarios: Sequence[BatchScenario],
    seeds: Sequence[int],
    output: Path,
    *,
    jobs: int = 1,
) -> dict[str, Any]:
    """Execute a validated matrix and preserve results in stable task order."""
    tasks = _validate(scenarios, seeds, jobs)
    output.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "batch_schema_version": BATCH_SCHEMA_VERSION,
        "status": "running",
        "jobs": jobs,
        "task_count": len(tasks),
        "seeds": list(seeds),
        "scenarios": [
            {"name": scenario.name, "config": asdict(scenario.config)} for scenario in scenarios
        ],
        "tasks": [
            {
                "index": task.index,
                "scenario": task.scenario,
                "seed": task.seed,
                "output": task.relative_output,
            }
            for task in tasks
        ],
        "provenance": provenance(),
    }
    write_json(output / "batch_manifest.json", manifest)
    started = perf_counter()
    try:
        if jobs == 1:
            results = [_execute_task(task, output) for task in tasks]
        else:
            context = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(max_workers=jobs, mp_context=context) as executor:
                futures = [executor.submit(_execute_task, task, output) for task in tasks]
                results = [future.result() for future in futures]
        elapsed = perf_counter() - started
        total_steps = sum(task.config.run.steps for task in tasks)
        report = {
            "batch_schema_version": BATCH_SCHEMA_VERSION,
            "task_count": len(tasks),
            "jobs": jobs,
            "elapsed_seconds": elapsed,
            "total_simulated_steps": total_steps,
            "aggregate_ticks_per_second": total_steps / elapsed,
            "results": results,
        }
        write_json(output / "batch_summary.json", report)
        manifest.update(status="completed")
        write_json(output / "batch_manifest.json", manifest)
        return report
    except BaseException as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(output / "batch_manifest.json", manifest)
        raise
