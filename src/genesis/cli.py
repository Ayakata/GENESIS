"""Portable command-line entry point. Logs go to stderr, results to stdout."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from genesis import __version__
from genesis.config import Config, ConfigError, dump_config, load_config
from genesis.lab.batch import BatchScenario, run_batch
from genesis.lab.runner import benchmark_artifact, resume_artifact, run_artifact

LOG = logging.getLogger("genesis")


def run(config: Config, output: Path) -> dict[str, Any]:
    """Backward-compatible public entry point for one artifact-producing run."""
    return run_artifact(config, output)


def _scenario(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name or not raw_path:
        raise argparse.ArgumentTypeError("scenario must have the form NAME=CONFIG_PATH")
    return name, Path(raw_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="genesis", description="Genesis evolution sandbox")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write a complete default YAML without overwriting")
    init.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate", help="validate config and print resolved YAML")
    validate.add_argument("--config", type=Path, required=True)
    execute = sub.add_parser("run", help="run the configured headless sandbox")
    execute.add_argument("--config", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--steps", type=int)
    execute.add_argument("--seed", type=int)
    execute.add_argument("--checkpoint-interval", type=int)
    resume = sub.add_parser("resume", help="continue from an integrity-checked checkpoint")
    resume.add_argument("--checkpoint", type=Path, required=True)
    resume.add_argument("--output", type=Path, required=True)
    resume.add_argument("--steps", type=int, required=True)
    resume.add_argument("--checkpoint-interval", type=int)
    batch = sub.add_parser("batch", help="run a scenario/seed matrix without a GUI")
    batch.add_argument("--scenario", action="append", type=_scenario, required=True)
    batch.add_argument("--seeds", nargs="+", type=int, required=True)
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--jobs", type=int, default=1)
    batch.add_argument("--steps", type=int)
    benchmark = sub.add_parser("benchmark", help="measure in-memory headless throughput")
    benchmark.add_argument("--config", type=Path, required=True)
    benchmark.add_argument("--output", type=Path, required=True)
    benchmark.add_argument("--steps", type=int, default=200)
    benchmark.add_argument("--warmup", type=int, default=20)
    benchmark.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "init":
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(dump_config(Config()))
        elif args.command in ("validate", "run", "benchmark"):
            config = load_config(args.config)
            if args.command == "validate":
                print(dump_config(config), end="")
            elif args.command == "run":
                if args.seed is not None:
                    config = replace(config, seed=args.seed)
                if args.steps is not None:
                    config = replace(config, run=replace(config.run, steps=args.steps))
                if args.checkpoint_interval is not None:
                    config = replace(
                        config,
                        run=replace(config.run, checkpoint_interval=args.checkpoint_interval),
                    )
                print(json.dumps(run(config, args.output), indent=2, allow_nan=False))
            else:
                print(
                    json.dumps(
                        benchmark_artifact(
                            config,
                            args.output,
                            steps=args.steps,
                            warmup=args.warmup,
                            repeats=args.repeats,
                        ),
                        indent=2,
                        allow_nan=False,
                    )
                )
        elif args.command == "batch":
            scenarios = []
            for name, path in args.scenario:
                config = load_config(path)
                if args.steps is not None:
                    config = replace(config, run=replace(config.run, steps=args.steps))
                scenarios.append(BatchScenario(name, config))
            print(
                json.dumps(
                    run_batch(scenarios, args.seeds, args.output, jobs=args.jobs),
                    indent=2,
                    allow_nan=False,
                )
            )
        else:
            print(
                json.dumps(
                    resume_artifact(
                        args.checkpoint,
                        args.output,
                        steps=args.steps,
                        checkpoint_interval=args.checkpoint_interval,
                    ),
                    indent=2,
                    allow_nan=False,
                )
            )
    except (ConfigError, OSError, RuntimeError, ValueError) as exc:
        LOG.error("%s", exc)
        return 2
    return 0
