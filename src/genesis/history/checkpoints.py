"""Versioned, integrity-checked, resumable sandbox checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.lib.npyio import NpzFile

import genesis
from genesis.agents.simulation import SandboxSimulation
from genesis.agents.state import AgentLedger, AgentState
from genesis.config import Config, dump_config, parse_config
from genesis.core.rng import RandomStreams
from genesis.core.state import Conditions, WorldState
from genesis.evolution.genome import GENE_COUNT
from genesis.evolution.state import EvolutionLedger
from genesis.history.artifacts import write_json

_MAX_CHECKPOINT_BYTES = 4 * 1024**3
_EXPECTED_KEYS = {
    "checkpoint_schema_version",
    "state_schema_version",
    "ruleset_version",
    "config_yaml",
    "state_digest",
    "tick",
    "elevation",
    "land",
    "temperature",
    "humidity",
    "light",
    "resource",
    "resource_ledger",
    "agent_ids",
    "agent_parent_ids",
    "agent_x",
    "agent_y",
    "agent_energy",
    "agent_age",
    "agent_genome",
    "agent_count",
    "agent_next_id",
    "agent_ledger_float",
    "agent_births",
    "agent_deaths",
    "evolution_ledger",
    "rng_environment_json",
    "rng_agents_json",
}


class CheckpointError(ValueError):
    """Checkpoint is corrupt, incompatible or internally inconsistent."""


@dataclass(frozen=True)
class LoadedCheckpoint:
    config: Config
    world: WorldState
    agents: AgentState
    agent_ledger: AgentLedger
    evolution_ledger: EvolutionLedger
    rng: RandomStreams
    path: Path
    file_sha256: str
    state_digest: str

    def simulation(self, config: Config | None = None) -> SandboxSimulation:
        """Build a simulation, optionally changing only run-control parameters."""
        effective = self.config if config is None else config
        if effective != self.config:
            embedded = self.config
            if effective != Config(
                schema_version=embedded.schema_version,
                seed=embedded.seed,
                world=embedded.world,
                terrain=embedded.terrain,
                conditions=embedded.conditions,
                resource=embedded.resource,
                agents=embedded.agents,
                evolution=embedded.evolution,
                run=effective.run,
            ):
                raise CheckpointError("resume may change run controls only")
        return SandboxSimulation.restore(
            effective,
            self.world,
            self.agents,
            self.agent_ledger,
            self.evolution_ledger,
            self.rng,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rng_json(generator: np.random.Generator) -> str:
    return json.dumps(generator.bit_generator.state, sort_keys=True, separators=(",", ":"))


def write_checkpoint(path: Path, simulation: SandboxSimulation) -> dict[str, Any]:
    """Atomically write an NPZ payload and its integrity sidecar without overwriting."""
    if path.suffix.lower() != ".npz":
        raise ValueError("checkpoint path must end in .npz")
    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = path.with_suffix(".json")
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"checkpoint already exists: {path}")

    sim = simulation
    config_yaml = dump_config(sim.config)
    count = sim.agents.count
    payload: dict[str, Any] = {
        "checkpoint_schema_version": np.array(genesis.CHECKPOINT_SCHEMA_VERSION),
        "state_schema_version": np.array(genesis.STATE_SCHEMA_VERSION),
        "ruleset_version": np.array(genesis.RULESET_VERSION),
        "config_yaml": np.array(config_yaml),
        "state_digest": np.array(sim.digest()),
        "tick": np.array(sim.world.tick, dtype=np.int64),
        "elevation": sim.world.conditions.elevation,
        "land": sim.world.conditions.land,
        "temperature": sim.world.conditions.temperature,
        "humidity": sim.world.conditions.humidity,
        "light": sim.world.conditions.light,
        "resource": sim.world.resource,
        "resource_ledger": np.array(
            [
                sim.world.initial_total,
                sim.world.source_total,
                sim.world.sink_total,
                sim.world.transfer_in_total,
                sim.world.transfer_out_total,
            ],
            dtype=np.float64,
        ),
        "agent_ids": sim.agents.ids[:count],
        "agent_parent_ids": sim.agents.parent_ids[:count],
        "agent_x": sim.agents.x[:count],
        "agent_y": sim.agents.y[:count],
        "agent_energy": sim.agents.energy[:count],
        "agent_age": sim.agents.age[:count],
        "agent_genome": sim.agents.genome[:count],
        "agent_count": np.array(count, dtype=np.int64),
        "agent_next_id": np.array(sim.agents.next_id, dtype=np.int64),
        "agent_ledger_float": np.array(
            [
                sim.agent_ledger.initial_energy,
                sim.agent_ledger.consumed,
                sim.agent_ledger.assimilated,
                sim.agent_ledger.assimilation_loss,
                sim.agent_ledger.basal_loss,
                sim.agent_ledger.movement_loss,
                sim.agent_ledger.reproduction_loss,
                sim.agent_ledger.death_recycled,
                sim.agent_ledger.death_loss,
            ],
            dtype=np.float64,
        ),
        "agent_births": np.array(sim.agent_ledger.births, dtype=np.int64),
        "agent_deaths": np.array(sim.agent_ledger.deaths, dtype=np.int64),
        "evolution_ledger": np.array(
            [
                sim.evolution_ledger.mutated_loci,
                sim.evolution_ledger.clipped_loci,
                sim.evolution_ledger.mutated_offspring,
            ],
            dtype=np.int64,
        ),
        "rng_environment_json": np.array(_rng_json(sim.environment.rng.environment)),
        "rng_agents_json": np.array(_rng_json(sim.environment.rng.agents)),
    }
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("xb") as stream:
            np.savez_compressed(stream, **payload)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    file_sha256 = _sha256(path)
    metadata = {
        "checkpoint_schema_version": genesis.CHECKPOINT_SCHEMA_VERSION,
        "state_schema_version": genesis.STATE_SCHEMA_VERSION,
        "ruleset_version": genesis.RULESET_VERSION,
        "tick": sim.world.tick,
        "state_digest": sim.digest(),
        "file": path.name,
        "file_sha256": file_sha256,
        "config_sha256": hashlib.sha256(config_yaml.encode()).hexdigest(),
    }
    sidecar_temporary = sidecar.with_name(f".{sidecar.name}.tmp")
    try:
        write_json(sidecar_temporary, metadata)
        os.replace(sidecar_temporary, sidecar)
    except BaseException:
        sidecar_temporary.unlink(missing_ok=True)
        raise
    return metadata


def _scalar(archive: NpzFile, name: str) -> Any:
    value = archive[name]
    if value.shape != ():
        raise CheckpointError(f"checkpoint field {name} must be scalar")
    return value.item()


def _array(
    archive: NpzFile, name: str, dtype: np.dtype[Any], shape: tuple[int, ...]
) -> np.ndarray[Any, Any]:
    value = archive[name]
    if value.dtype != dtype or value.shape != shape:
        raise CheckpointError(f"checkpoint field {name} must have dtype {dtype} and shape {shape}")
    return value.copy()


def load_checkpoint(path: Path) -> LoadedCheckpoint:
    """Validate integrity, schemas, arrays and RNG state before restoring ownership."""
    sidecar = path.with_suffix(".json")
    try:
        if path.stat().st_size > _MAX_CHECKPOINT_BYTES:
            raise CheckpointError("checkpoint exceeds 4 GiB safety limit")
        metadata_raw = sidecar.read_text(encoding="utf-8")
        if len(metadata_raw.encode()) > 1_048_576:
            raise CheckpointError("checkpoint sidecar exceeds 1 MiB")
        metadata = json.loads(metadata_raw)
    except CheckpointError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"cannot read checkpoint sidecar: {exc}") from exc
    if not isinstance(metadata, dict):
        raise CheckpointError("checkpoint sidecar must be a JSON object")
    if metadata.get("checkpoint_schema_version") != genesis.CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointError("unsupported checkpoint schema version")
    if metadata.get("state_schema_version") != genesis.STATE_SCHEMA_VERSION:
        raise CheckpointError("unsupported checkpoint state schema version")
    if metadata.get("ruleset_version") != genesis.RULESET_VERSION:
        raise CheckpointError("checkpoint sidecar ruleset is incompatible")
    if metadata.get("file") != path.name:
        raise CheckpointError("checkpoint sidecar file name mismatch")
    actual_sha256 = _sha256(path)
    if metadata.get("file_sha256") != actual_sha256:
        raise CheckpointError("checkpoint SHA-256 mismatch")

    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != _EXPECTED_KEYS:
                raise CheckpointError("checkpoint fields do not match schema")
            if _scalar(archive, "checkpoint_schema_version") != genesis.CHECKPOINT_SCHEMA_VERSION:
                raise CheckpointError("unsupported checkpoint payload schema version")
            if _scalar(archive, "state_schema_version") != genesis.STATE_SCHEMA_VERSION:
                raise CheckpointError("unsupported checkpoint state schema version")
            if _scalar(archive, "ruleset_version") != genesis.RULESET_VERSION:
                raise CheckpointError("checkpoint ruleset is incompatible")
            config_yaml = str(_scalar(archive, "config_yaml"))
            config = parse_config(config_yaml)
            if metadata.get("config_sha256") != hashlib.sha256(config_yaml.encode()).hexdigest():
                raise CheckpointError("checkpoint config digest mismatch")
            shape = (config.world.height, config.world.width)
            conditions = Conditions(
                elevation=_array(archive, "elevation", np.dtype(np.float64), shape),
                land=_array(archive, "land", np.dtype(np.bool_), shape),
                temperature=_array(archive, "temperature", np.dtype(np.float64), shape),
                humidity=_array(archive, "humidity", np.dtype(np.float64), shape),
                light=_array(archive, "light", np.dtype(np.float64), shape),
            )
            resource = _array(archive, "resource", np.dtype(np.float64), shape)
            resource_ledger = _array(archive, "resource_ledger", np.dtype(np.float64), (5,))
            tick = int(_scalar(archive, "tick"))
            world = WorldState(
                conditions=conditions,
                resource=resource,
                tick=tick,
                initial_total=float(resource_ledger[0]),
                source_total=float(resource_ledger[1]),
                sink_total=float(resource_ledger[2]),
                transfer_in_total=float(resource_ledger[3]),
                transfer_out_total=float(resource_ledger[4]),
            )
            count = int(_scalar(archive, "agent_count"))
            if not 0 <= count <= config.agents.max_population:
                raise CheckpointError("checkpoint agent count exceeds configured capacity")
            agents = AgentState.empty(config.agents.max_population)
            agents.ids[:count] = _array(archive, "agent_ids", np.dtype(np.int64), (count,))
            agents.parent_ids[:count] = _array(
                archive, "agent_parent_ids", np.dtype(np.int64), (count,)
            )
            agents.x[:count] = _array(archive, "agent_x", np.dtype(np.int32), (count,))
            agents.y[:count] = _array(archive, "agent_y", np.dtype(np.int32), (count,))
            agents.energy[:count] = _array(archive, "agent_energy", np.dtype(np.float64), (count,))
            agents.age[:count] = _array(archive, "agent_age", np.dtype(np.uint32), (count,))
            agents.genome[:count] = _array(
                archive, "agent_genome", np.dtype(np.float64), (count, GENE_COUNT)
            )
            agents.count = count
            agents.next_id = int(_scalar(archive, "agent_next_id"))
            ledger_values = _array(archive, "agent_ledger_float", np.dtype(np.float64), (9,))
            agent_ledger = AgentLedger(
                initial_energy=float(ledger_values[0]),
                consumed=float(ledger_values[1]),
                assimilated=float(ledger_values[2]),
                assimilation_loss=float(ledger_values[3]),
                basal_loss=float(ledger_values[4]),
                movement_loss=float(ledger_values[5]),
                reproduction_loss=float(ledger_values[6]),
                death_recycled=float(ledger_values[7]),
                death_loss=float(ledger_values[8]),
                births=int(_scalar(archive, "agent_births")),
                deaths=int(_scalar(archive, "agent_deaths")),
            )
            evolution_values = _array(archive, "evolution_ledger", np.dtype(np.int64), (3,))
            evolution_ledger = EvolutionLedger(*(int(value) for value in evolution_values))
            rng = RandomStreams.from_seed(config.seed)
            rng.environment.bit_generator.state = json.loads(
                str(_scalar(archive, "rng_environment_json"))
            )
            rng.agents.bit_generator.state = json.loads(str(_scalar(archive, "rng_agents_json")))
            stored_digest = str(_scalar(archive, "state_digest"))
    except CheckpointError:
        raise
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"invalid checkpoint payload: {exc}") from exc

    simulation = SandboxSimulation.restore(
        config, world, agents, agent_ledger, evolution_ledger, rng
    )
    if metadata.get("tick") != world.tick:
        raise CheckpointError("checkpoint tick does not match sidecar")
    if metadata.get("state_digest") != stored_digest or simulation.digest() != stored_digest:
        raise CheckpointError("checkpoint scientific state digest mismatch")
    return LoadedCheckpoint(
        config=config,
        world=world,
        agents=agents,
        agent_ledger=agent_ledger,
        evolution_ledger=evolution_ledger,
        rng=rng,
        path=path.resolve(),
        file_sha256=actual_sha256,
        state_digest=stored_digest,
    )
