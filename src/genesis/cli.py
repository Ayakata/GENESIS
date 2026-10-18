"""Portable command-line entry point. Logs go to stderr, results to stdout."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any

from genesis import __version__
from genesis.config import Config, ConfigError, dump_config, load_config
from genesis.core.simulation import Simulation
from genesis.history.artifacts import start_run, write_final_state, write_json
from genesis.lab.metrics import measure

LOG = logging.getLogger("genesis")


def run(config: Config, output: Path) -> dict[str, Any]:
    manifest = start_run(output, config)
    handler = logging.FileHandler(output / "run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    LOG.addHandler(handler)
    started = perf_counter()
    try:
        sim = Simulation(config)
        LOG.info(
            "Started seed=%d shape=%s steps=%d",
            config.seed,
            sim.state.resource.shape,
            config.run.steps,
        )
        with (output / "metrics.jsonl").open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(measure(sim.state), allow_nan=False) + "\n")
            for _ in range(config.run.steps):
                sim.step()
                if (
                    sim.state.tick % config.run.metrics_interval == 0
                    or sim.state.tick == config.run.steps
                ):
                    stream.write(json.dumps(measure(sim.state), allow_nan=False) + "\n")
        write_final_state(output / "final_state.npz", sim.state)
        summary: dict[str, Any] = {
            "state_digest": sim.state.digest(),
            "metrics": measure(sim.state),
            "elapsed_seconds": perf_counter() - started,
        }
        write_json(output / "summary.json", summary)
        manifest.update(status="completed", state_digest=sim.state.digest())
        write_json(output / "manifest.json", manifest)
        LOG.info(
            "Completed tick=%d balance_error=%.3g",
            sim.state.tick,
            summary["metrics"]["balance_error"],
        )
        return summary
    except BaseException as exc:
        LOG.exception("Run failed")
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(output / "manifest.json", manifest)
        raise
    finally:
        LOG.removeHandler(handler)
        handler.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="genesis", description="Genesis environment sandbox")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write a complete default YAML without overwriting")
    init.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate", help="validate config and print resolved YAML")
    validate.add_argument("--config", type=Path, required=True)
    execute = sub.add_parser("run", help="run the environment-only verification harness")
    execute.add_argument("--config", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--steps", type=int)
    execute.add_argument("--seed", type=int)
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "init":
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(dump_config(Config()))
        else:
            config = load_config(args.config)
            if args.command == "validate":
                print(dump_config(config), end="")
            else:
                if args.seed is not None:
                    config = replace(config, seed=args.seed)
                if args.steps is not None:
                    config = replace(config, run=replace(config.run, steps=args.steps))
                print(json.dumps(run(config, args.output), indent=2, allow_nan=False))
    except (ConfigError, OSError, RuntimeError) as exc:
        LOG.error("%s", exc)
        return 2
    return 0
