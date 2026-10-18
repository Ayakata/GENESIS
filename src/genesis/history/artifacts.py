"""Versioned run manifests and inspectable terminal artifacts."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np

import genesis
from genesis.agents.state import AgentLedger, AgentState
from genesis.config import Config, dump_config
from genesis.core.state import WorldState
from genesis.evolution.genome import GENE_NAMES
from genesis.evolution.state import EvolutionLedger


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def provenance() -> dict[str, Any]:
    package_dir = Path(genesis.__file__).resolve().parent
    code_hash = hashlib.sha256()
    for path in sorted(package_dir.rglob("*.py")):
        code_hash.update(path.relative_to(package_dir).as_posix().encode())
        code_hash.update(path.read_bytes())
    commit = None
    dirty = None
    repository = package_dir.parent.parent
    if (repository / ".git").exists():
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
            dirty = bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"],
                    cwd=repository,
                    text=True,
                    timeout=5,
                ).strip()
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return {
        "package_version": genesis.__version__,
        "git_commit": commit,
        "git_dirty": dirty,
        "source_sha256": code_hash.hexdigest(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "dependencies": {name: version(name) for name in ("numpy", "PyYAML")},
        "backend": "numpy-cpu-float64",
        "rng": "PCG64/SeedSequence.spawn-v1",
    }


def start_run(directory: Path, config: Config) -> dict[str, Any]:
    # Fail on collisions; no silent overwrites or merging evidence from two runs.
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "config.resolved.yaml").write_text(dump_config(config), encoding="utf-8")
    manifest = {
        "artifact_schema_version": genesis.ARTIFACT_SCHEMA_VERSION,
        "state_schema_version": genesis.STATE_SCHEMA_VERSION,
        "ruleset_version": genesis.RULESET_VERSION,
        "config": asdict(config),
        "provenance": provenance(),
        "status": "running",
    }
    write_json(directory / "manifest.json", manifest)
    return manifest


def write_final_state(path: Path, state: WorldState) -> None:
    np.savez_compressed(
        path,
        state_schema_version=np.array(genesis.STATE_SCHEMA_VERSION),
        ruleset_version=np.array(genesis.RULESET_VERSION),
        tick=np.array(state.tick),
        elevation=state.conditions.elevation,
        land=state.conditions.land,
        temperature=state.conditions.temperature,
        humidity=state.conditions.humidity,
        light=state.conditions.light,
        resource=state.resource,
        ledger=np.array(
            [
                state.initial_total,
                state.source_total,
                state.sink_total,
                state.transfer_in_total,
                state.transfer_out_total,
            ]
        ),
    )


def write_sandbox_final_state(
    path: Path,
    state: WorldState,
    population: AgentState,
    ledger: AgentLedger,
    evolution: EvolutionLedger,
) -> None:
    """Write a compact terminal inspection copy; resumable state lives in checkpoints."""
    np.savez_compressed(
        path,
        state_schema_version=np.array(genesis.STATE_SCHEMA_VERSION),
        ruleset_version=np.array(genesis.RULESET_VERSION),
        tick=np.array(state.tick),
        elevation=state.conditions.elevation,
        land=state.conditions.land,
        temperature=state.conditions.temperature,
        humidity=state.conditions.humidity,
        light=state.conditions.light,
        resource=state.resource,
        resource_ledger=np.array(
            [
                state.initial_total,
                state.source_total,
                state.sink_total,
                state.transfer_in_total,
                state.transfer_out_total,
            ]
        ),
        agent_ids=population.ids[: population.count],
        agent_parent_ids=population.parent_ids[: population.count],
        agent_x=population.x[: population.count],
        agent_y=population.y[: population.count],
        agent_energy=population.energy[: population.count],
        agent_age=population.age[: population.count],
        agent_genome=population.genome[: population.count],
        gene_names=np.array(GENE_NAMES),
        agent_next_id=np.array(population.next_id),
        agent_ledger_names=np.array(tuple(asdict(ledger))),
        agent_ledger_values=np.array(tuple(asdict(ledger).values()), dtype=np.float64),
        evolution_ledger_names=np.array(tuple(asdict(evolution))),
        evolution_ledger_values=np.array(tuple(asdict(evolution).values()), dtype=np.int64),
    )
