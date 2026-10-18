import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from genesis.cli import LOG, run
from genesis.config import Config


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-m", "genesis", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_end_to_end_separate_processes(tmp_path):
    config = tmp_path / "world.yaml"
    assert invoke("init", "--output", config).returncode == 0
    assert invoke("validate", "--config", config).returncode == 0
    summaries = []
    for name in ("a", "b"):
        directory = tmp_path / name
        result = invoke("run", "--config", config, "--steps", 11, "--output", directory)
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        summaries.append(summary)
        manifest = json.loads((directory / "manifest.json").read_text())
        assert manifest["status"] == "completed"
        assert "Completed" in (directory / "run.log").read_text()
        assert manifest["provenance"]["source_sha256"]
        assert manifest["config"]["run"]["steps"] == 11
        metrics = [
            json.loads(row) for row in (directory / "metrics.jsonl").read_text().splitlines()
        ]
        assert [row["tick"] for row in metrics] == [0, 10, 11]
        with np.load(directory / "final_state.npz", allow_pickle=False) as state:
            assert state["tick"].item() == 11
            assert state["resource"].shape == (64, 96)
            assert "agent_ids" in state
            assert state["agent_genome"].shape[1] == 8
            assert state["gene_names"].size == 8
    assert summaries[0]["state_digest"] == summaries[1]["state_digest"]
    for name in ("metrics.jsonl", "config.resolved.yaml"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert invoke("run", "--config", config, "--output", tmp_path / "a").returncode == 2
    assert invoke("init", "--output", config).returncode == 2


def test_cli_invalid_inputs_and_zero_steps(tmp_path):
    config = tmp_path / "world.yaml"
    assert invoke("init", "--output", config).returncode == 0
    invalid = invoke("run", "--config", config, "--steps", -1, "--output", tmp_path / "invalid")
    assert invalid.returncode == 2
    assert not (tmp_path / "invalid").exists()
    assert invoke("validate", "--config", tmp_path / "missing").returncode == 2
    result = invoke(
        "run", "--config", config, "--steps", 0, "--seed", 5, "--output", tmp_path / "zero"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["metrics"]["tick"] == 0


def test_determinism_under_different_python_hash_seeds(tmp_path):
    config = Path(__file__).resolve().parents[1] / "configs" / "archipelago.yaml"
    digests = []
    for seed in ("1", "789"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "genesis",
                "run",
                "--config",
                str(config),
                "--steps",
                "15",
                "--output",
                str(tmp_path / seed),
            ],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        digests.append(json.loads(result.stdout)["state_digest"])
    assert digests[0] == digests[1]
    with np.load(tmp_path / "1" / "final_state.npz", allow_pickle=False) as state:
        assert state["agent_ids"].size > 0


def test_failed_run_is_marked_and_file_handler_closed(tmp_path, monkeypatch):
    def fail_step(self):
        raise RuntimeError("injected failure")

    monkeypatch.setattr("genesis.core.simulation.Simulation.step", fail_step)
    before = tuple(LOG.handlers)
    with pytest.raises(RuntimeError, match="injected failure"):
        run(Config(), tmp_path / "failure")
    manifest = json.loads((tmp_path / "failure" / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert "injected failure" in manifest["error"]
    assert tuple(LOG.handlers) == before


def test_cli_batch_and_benchmark(tmp_path):
    config = tmp_path / "world.yaml"
    assert invoke("init", "--output", config).returncode == 0
    batch = invoke(
        "batch",
        "--scenario",
        f"world={config}",
        "--seeds",
        2,
        3,
        "--steps",
        2,
        "--jobs",
        2,
        "--output",
        tmp_path / "batch",
    )
    assert batch.returncode == 0, batch.stderr
    report = json.loads(batch.stdout)
    assert report["task_count"] == 2
    assert [item["seed"] for item in report["results"]] == [2, 3]

    measured = invoke(
        "benchmark",
        "--config",
        config,
        "--steps",
        2,
        "--warmup",
        0,
        "--repeats",
        2,
        "--output",
        tmp_path / "benchmark",
    )
    assert measured.returncode == 0, measured.stderr
    assert json.loads(measured.stdout)["median_ticks_per_second"] > 0


def test_cli_batch_rejects_invalid_scenario_spec(tmp_path):
    result = invoke(
        "batch",
        "--scenario",
        "missing-equals",
        "--seeds",
        1,
        "--output",
        tmp_path / "batch",
    )
    assert result.returncode == 2
