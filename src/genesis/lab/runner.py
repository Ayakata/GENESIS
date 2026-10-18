"""Headless single-run and benchmark orchestration outside the simulation core."""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

from genesis.agents.metrics import measure_sandbox
from genesis.agents.simulation import SandboxSimulation
from genesis.config import Config, dump_config
from genesis.history.artifacts import (
    provenance,
    start_run,
    write_json,
    write_sandbox_final_state,
)

LOG = logging.getLogger("genesis")
BENCHMARK_SCHEMA_VERSION = 1


def run_artifact(config: Config, output: Path) -> dict[str, Any]:
    """Run a simulation without a GUI and persist its inspectable artifacts."""
    manifest = start_run(output, config)
    handler = logging.FileHandler(output / "run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    file_log = logging.Logger("genesis.run", logging.INFO)
    file_log.addHandler(handler)
    started = perf_counter()
    try:
        sim = SandboxSimulation(config)
        LOG.info(
            "Started seed=%d shape=%s agents=%d steps=%d",
            config.seed,
            sim.world.resource.shape,
            sim.agents.count,
            config.run.steps,
        )
        file_log.info(
            "Started seed=%d shape=%s agents=%d steps=%d",
            config.seed,
            sim.world.resource.shape,
            sim.agents.count,
            config.run.steps,
        )
        with (output / "metrics.jsonl").open("w", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    measure_sandbox(sim.world, sim.agents, sim.agent_ledger, sim.evolution_ledger),
                    allow_nan=False,
                )
                + "\n"
            )
            for _ in range(config.run.steps):
                sim.step()
                if (
                    sim.world.tick % config.run.metrics_interval == 0
                    or sim.world.tick == config.run.steps
                ):
                    stream.write(
                        json.dumps(
                            measure_sandbox(
                                sim.world,
                                sim.agents,
                                sim.agent_ledger,
                                sim.evolution_ledger,
                            ),
                            allow_nan=False,
                        )
                        + "\n"
                    )
        write_sandbox_final_state(
            output / "final_state.npz",
            sim.world,
            sim.agents,
            sim.agent_ledger,
            sim.evolution_ledger,
        )
        summary: dict[str, Any] = {
            "state_digest": sim.digest(),
            "metrics": measure_sandbox(
                sim.world, sim.agents, sim.agent_ledger, sim.evolution_ledger
            ),
            "elapsed_seconds": perf_counter() - started,
        }
        write_json(output / "summary.json", summary)
        manifest.update(status="completed", state_digest=sim.digest())
        write_json(output / "manifest.json", manifest)
        LOG.info(
            "Completed tick=%d balance_error=%.3g",
            sim.world.tick,
            summary["metrics"]["balance_error"],
        )
        file_log.info(
            "Completed tick=%d balance_error=%.3g",
            sim.world.tick,
            summary["metrics"]["balance_error"],
        )
        return summary
    except BaseException as exc:
        LOG.exception("Run failed")
        file_log.exception("Run failed")
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(output / "manifest.json", manifest)
        raise
    finally:
        file_log.removeHandler(handler)
        handler.close()


def benchmark(config: Config, *, steps: int, warmup: int, repeats: int) -> dict[str, Any]:
    """Measure in-memory headless throughput with a fresh simulation per repeat."""
    if type(steps) is not int or steps < 1:
        raise ValueError("benchmark steps must be a positive integer")
    if type(warmup) is not int or warmup < 0:
        raise ValueError("benchmark warmup must be a nonnegative integer")
    if type(repeats) is not int or not 1 <= repeats <= 100:
        raise ValueError("benchmark repeats must be an integer in [1,100]")

    samples: list[dict[str, int | float | str]] = []
    expected_digest: str | None = None
    for repeat in range(repeats):
        sim = SandboxSimulation(config)
        sim.advance(warmup)
        agent_updates = 0
        started = perf_counter()
        for _ in range(steps):
            agent_updates += sim.agents.count
            sim.step()
        elapsed = perf_counter() - started
        digest = sim.digest()
        if expected_digest is None:
            expected_digest = digest
        elif digest != expected_digest:
            raise RuntimeError("benchmark repeats produced different scientific states")
        samples.append(
            {
                "repeat": repeat,
                "elapsed_seconds": elapsed,
                "ticks_per_second": steps / elapsed,
                "cell_updates_per_second": steps
                * config.world.width
                * config.world.height
                / elapsed,
                "agent_updates": agent_updates,
                "agent_updates_per_second": agent_updates / elapsed,
                "final_population": sim.agents.count,
                "state_digest": digest,
            }
        )

    elapsed_values = [float(sample["elapsed_seconds"]) for sample in samples]
    tick_rates = [float(sample["ticks_per_second"]) for sample in samples]
    return {
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "seed": config.seed,
        "steps": steps,
        "warmup_steps": warmup,
        "repeats": repeats,
        "samples": samples,
        "median_elapsed_seconds": statistics.median(elapsed_values),
        "median_ticks_per_second": statistics.median(tick_rates),
        "min_ticks_per_second": min(tick_rates),
        "max_ticks_per_second": max(tick_rates),
        "state_digest": expected_digest,
    }


def benchmark_artifact(
    config: Config, output: Path, *, steps: int, warmup: int, repeats: int
) -> dict[str, Any]:
    """Run a benchmark and persist enough context to repeat it."""
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.resolved.yaml").write_text(dump_config(config), encoding="utf-8")
    manifest = {
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "config": asdict(config),
        "provenance": provenance(),
        "parameters": {"steps": steps, "warmup_steps": warmup, "repeats": repeats},
        "status": "running",
    }
    write_json(output / "manifest.json", manifest)
    try:
        report = benchmark(config, steps=steps, warmup=warmup, repeats=repeats)
        write_json(output / "benchmark.json", report)
        manifest.update(status="completed", state_digest=report["state_digest"])
        write_json(output / "manifest.json", manifest)
        return report
    except BaseException as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(output / "manifest.json", manifest)
        raise
