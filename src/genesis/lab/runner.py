"""Headless single-run and benchmark orchestration outside the simulation core."""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO

import genesis
from genesis.agents.metrics import measure_sandbox
from genesis.agents.simulation import SandboxSimulation
from genesis.config import Config, dump_config
from genesis.history.artifacts import (
    provenance,
    start_run,
    write_json,
    write_sandbox_final_state,
)
from genesis.history.checkpoints import load_checkpoint, write_checkpoint

LOG = logging.getLogger("genesis")
BENCHMARK_SCHEMA_VERSION = 1


def _event(stream: TextIO, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _checkpoint(
    simulation: SandboxSimulation, output: Path, records: list[dict[str, Any]]
) -> dict[str, Any]:
    relative = Path("checkpoints") / f"tick-{simulation.world.tick:012d}.npz"
    metadata = write_checkpoint(output / relative, simulation)
    record = {
        "tick": simulation.world.tick,
        "path": relative.as_posix(),
        "sidecar": relative.with_suffix(".json").as_posix(),
        "file_sha256": metadata["file_sha256"],
        "state_digest": metadata["state_digest"],
    }
    records.append(record)
    return record


def run_artifact(
    config: Config,
    output: Path,
    *,
    simulation: SandboxSimulation | None = None,
    resumed_from: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a simulation without a GUI and persist its inspectable artifacts."""
    manifest = start_run(output, config)
    if resumed_from is not None:
        manifest["resumed_from"] = resumed_from
        write_json(output / "manifest.json", manifest)
    handler = logging.FileHandler(output / "run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    file_log = logging.Logger("genesis.run", logging.INFO)
    file_log.addHandler(handler)
    started = perf_counter()
    checkpoints: list[dict[str, Any]] = []
    start_tick = 0
    sim: SandboxSimulation | None = None
    try:
        sim = SandboxSimulation(config) if simulation is None else simulation
        if sim.config != config:
            raise ValueError("simulation config does not match artifact config")
        start_tick = sim.world.tick
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
        with (
            (output / "metrics.jsonl").open("w", encoding="utf-8") as metrics_stream,
            (output / "events.jsonl").open("w", encoding="utf-8") as event_stream,
        ):
            _event(
                event_stream,
                {
                    "event_schema_version": genesis.EVENT_SCHEMA_VERSION,
                    "type": "run_started",
                    "tick": start_tick,
                    "resumed": resumed_from is not None,
                    "state_digest": sim.digest(),
                },
            )
            metrics_stream.write(
                json.dumps(
                    measure_sandbox(sim.world, sim.agents, sim.agent_ledger, sim.evolution_ledger),
                    allow_nan=False,
                )
                + "\n"
            )
            for step_index in range(config.run.steps):
                flux = sim.step()
                _event(
                    event_stream,
                    {
                        "event_schema_version": genesis.EVENT_SCHEMA_VERSION,
                        "type": "tick",
                        "tick": sim.world.tick,
                        "environment": asdict(flux.environment),
                        "agents": asdict(flux.agents),
                    },
                )
                if (
                    sim.world.tick % config.run.metrics_interval == 0
                    or step_index + 1 == config.run.steps
                ):
                    metrics_stream.write(
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
                if (
                    config.run.checkpoint_interval
                    and sim.world.tick % config.run.checkpoint_interval == 0
                ):
                    checkpoint = _checkpoint(sim, output, checkpoints)
                    _event(
                        event_stream,
                        {
                            "event_schema_version": genesis.EVENT_SCHEMA_VERSION,
                            "type": "checkpoint",
                            **checkpoint,
                        },
                    )
            if not checkpoints or checkpoints[-1]["tick"] != sim.world.tick:
                checkpoint = _checkpoint(sim, output, checkpoints)
                _event(
                    event_stream,
                    {
                        "event_schema_version": genesis.EVENT_SCHEMA_VERSION,
                        "type": "checkpoint",
                        **checkpoint,
                    },
                )
            _event(
                event_stream,
                {
                    "event_schema_version": genesis.EVENT_SCHEMA_VERSION,
                    "type": "run_completed",
                    "tick": sim.world.tick,
                    "state_digest": sim.digest(),
                },
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
            "start_tick": start_tick,
            "end_tick": sim.world.tick,
            "steps_executed": config.run.steps,
            "checkpoint_count": len(checkpoints),
        }
        write_json(output / "summary.json", summary)
        manifest.update(
            status="completed",
            state_digest=sim.digest(),
            start_tick=start_tick,
            end_tick=sim.world.tick,
            checkpoints=checkpoints,
            event_schema_version=genesis.EVENT_SCHEMA_VERSION,
        )
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
        try:
            with (output / "events.jsonl").open("a", encoding="utf-8") as event_stream:
                _event(
                    event_stream,
                    {
                        "event_schema_version": genesis.EVENT_SCHEMA_VERSION,
                        "type": "run_failed",
                        "tick": sim.world.tick if sim is not None else start_tick,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
        except OSError:
            pass
        manifest.update(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            start_tick=start_tick,
            end_tick=sim.world.tick if sim is not None else start_tick,
            checkpoints=checkpoints,
            event_schema_version=genesis.EVENT_SCHEMA_VERSION,
        )
        write_json(output / "manifest.json", manifest)
        raise
    finally:
        file_log.removeHandler(handler)
        handler.close()


def resume_artifact(
    checkpoint_path: Path,
    output: Path,
    *,
    steps: int,
    checkpoint_interval: int | None = None,
) -> dict[str, Any]:
    """Resume a checkpoint for an explicit number of additional steps."""
    if type(steps) is not int or steps < 0:
        raise ValueError("resume steps must be a nonnegative integer")
    loaded = load_checkpoint(checkpoint_path)
    interval = (
        loaded.config.run.checkpoint_interval
        if checkpoint_interval is None
        else checkpoint_interval
    )
    run_config = replace(loaded.config.run, steps=steps, checkpoint_interval=interval)
    config = replace(loaded.config, run=run_config)
    simulation = loaded.simulation(config)
    lineage = {
        "checkpoint": str(loaded.path),
        "tick": loaded.world.tick,
        "state_digest": loaded.state_digest,
        "file_sha256": loaded.file_sha256,
    }
    return run_artifact(
        config,
        output,
        simulation=simulation,
        resumed_from=lineage,
    )


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
