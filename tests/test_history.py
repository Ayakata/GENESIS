import json
from dataclasses import replace

import numpy as np
import pytest

from genesis.agents.metrics import measure_sandbox
from genesis.config import AgentConfig, Config, RunConfig, TerrainConfig, WorldConfig
from genesis.history.checkpoints import CheckpointError, load_checkpoint
from genesis.lab.runner import resume_artifact, run_artifact


def history_config(*, steps: int, checkpoint_interval: int) -> Config:
    return Config(
        seed=2026,
        world=WorldConfig(width=12, height=8, boundary="periodic"),
        terrain=TerrainConfig(kind="uniform"),
        agents=AgentConfig(initial_count=12, max_population=128, max_age=80),
        run=RunConfig(
            steps=steps,
            metrics_interval=3,
            checkpoint_interval=checkpoint_interval,
        ),
    )


def test_checkpoint_roundtrip_restores_complete_scientific_state(tmp_path):
    config = history_config(steps=12, checkpoint_interval=5)
    summary = run_artifact(config, tmp_path / "run")
    checkpoints = sorted((tmp_path / "run" / "checkpoints").glob("*.npz"))
    assert [path.stem for path in checkpoints] == [
        "tick-000000000005",
        "tick-000000000010",
        "tick-000000000012",
    ]

    loaded = load_checkpoint(checkpoints[-1])
    restored = loaded.simulation()
    assert restored.world.tick == 12
    assert restored.digest() == summary["state_digest"] == loaded.state_digest
    assert (
        measure_sandbox(
            restored.world,
            restored.agents,
            restored.agent_ledger,
            restored.evolution_ledger,
        )
        == summary["metrics"]
    )
    assert not restored.world.conditions.land.flags.writeable
    assert restored.world.resource.flags.writeable

    events = [
        json.loads(line) for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()
    ]
    assert [event["type"] for event in events].count("tick") == 12
    assert [event["type"] for event in events].count("checkpoint") == 3
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"
    assert all(event["event_schema_version"] == 1 for event in events)


def test_resume_matches_uninterrupted_run_exactly(tmp_path):
    continuous = run_artifact(history_config(steps=12, checkpoint_interval=4), tmp_path / "whole")
    first = run_artifact(history_config(steps=5, checkpoint_interval=4), tmp_path / "first")
    checkpoint = tmp_path / "first" / "checkpoints" / "tick-000000000005.npz"
    resumed = resume_artifact(checkpoint, tmp_path / "resumed", steps=7)

    assert first["end_tick"] == resumed["start_tick"] == 5
    assert resumed["end_tick"] == 12
    assert resumed["state_digest"] == continuous["state_digest"]
    assert resumed["metrics"] == continuous["metrics"]
    with (
        np.load(tmp_path / "whole" / "final_state.npz", allow_pickle=False) as whole,
        np.load(tmp_path / "resumed" / "final_state.npz", allow_pickle=False) as split,
    ):
        assert set(whole.files) == set(split.files)
        for name in whole.files:
            np.testing.assert_array_equal(whole[name], split[name])
    manifest = json.loads((tmp_path / "resumed" / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["resumed_from"]["tick"] == 5
    assert manifest["resumed_from"]["state_digest"] == first["state_digest"]
    whole_events = [
        json.loads(line) for line in (tmp_path / "whole" / "events.jsonl").read_text().splitlines()
    ]
    first_events = [
        json.loads(line) for line in (tmp_path / "first" / "events.jsonl").read_text().splitlines()
    ]
    resumed_events = [
        json.loads(line)
        for line in (tmp_path / "resumed" / "events.jsonl").read_text().splitlines()
    ]
    whole_ticks = [event for event in whole_events if event["type"] == "tick"]
    split_ticks = [event for event in (*first_events, *resumed_events) if event["type"] == "tick"]
    assert split_ticks == whole_ticks


def test_checkpoint_integrity_and_schema_are_enforced(tmp_path):
    run_artifact(history_config(steps=2, checkpoint_interval=0), tmp_path / "source")
    original = tmp_path / "source" / "checkpoints" / "tick-000000000002.npz"
    original_sidecar = original.with_suffix(".json")

    corrupt_dir = tmp_path / "corrupt"
    corrupt_dir.mkdir()
    corrupt = corrupt_dir / original.name
    corrupt.write_bytes(original.read_bytes())
    corrupt.with_suffix(".json").write_bytes(original_sidecar.read_bytes())
    data = bytearray(corrupt.read_bytes())
    data[len(data) // 2] ^= 1
    corrupt.write_bytes(data)
    with pytest.raises(CheckpointError, match="SHA-256"):
        load_checkpoint(corrupt)

    incompatible_dir = tmp_path / "incompatible"
    incompatible_dir.mkdir()
    incompatible = incompatible_dir / original.name
    incompatible.write_bytes(original.read_bytes())
    metadata = json.loads(original_sidecar.read_text())
    metadata["checkpoint_schema_version"] = 999
    incompatible.with_suffix(".json").write_text(json.dumps(metadata))
    with pytest.raises(CheckpointError, match="schema"):
        load_checkpoint(incompatible)


def test_resume_rejects_scientific_config_change(tmp_path):
    run_artifact(history_config(steps=1, checkpoint_interval=0), tmp_path / "source")
    loaded = load_checkpoint(tmp_path / "source" / "checkpoints" / "tick-000000000001.npz")
    changed = replace(loaded.config, seed=loaded.config.seed + 1)
    with pytest.raises(CheckpointError, match="run controls"):
        loaded.simulation(changed)
