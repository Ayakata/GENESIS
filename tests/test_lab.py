import json
from dataclasses import replace

import pytest

from genesis.config import AgentConfig, Config, RunConfig, TerrainConfig, WorldConfig
from genesis.lab.batch import BatchScenario, run_batch
from genesis.lab.runner import benchmark, benchmark_artifact


def small_config() -> Config:
    return Config(
        world=WorldConfig(width=8, height=6),
        terrain=TerrainConfig(kind="uniform"),
        agents=AgentConfig(initial_count=4, max_population=16),
        run=RunConfig(steps=4, metrics_interval=2),
    )


def scientific_results(report):
    return [
        (item["scenario"], item["seed"], item["state_digest"], item["metrics"])
        for item in report["results"]
    ]


def test_batch_serial_and_parallel_are_scientifically_identical(tmp_path):
    scenarios = (
        BatchScenario("baseline", small_config()),
        BatchScenario("alternate", replace(small_config(), run=RunConfig(steps=3))),
    )
    serial = run_batch(scenarios, (1, 9), tmp_path / "serial", jobs=1)
    parallel = run_batch(scenarios, (1, 9), tmp_path / "parallel", jobs=2)

    assert serial["task_count"] == parallel["task_count"] == 4
    assert scientific_results(serial) == scientific_results(parallel)
    assert [item["index"] for item in parallel["results"]] == list(range(4))
    for root in (tmp_path / "serial", tmp_path / "parallel"):
        manifest = json.loads((root / "batch_manifest.json").read_text())
        assert manifest["status"] == "completed"
        assert manifest["batch_schema_version"] == 1
        assert (root / "runs" / "baseline" / "seed-1" / "final_state.npz").is_file()
        assert "Completed" in (root / "runs" / "baseline" / "seed-1" / "run.log").read_text()


@pytest.mark.parametrize(
    ("scenarios", "seeds", "jobs", "message"),
    [
        ((), (1,), 1, "scenario"),
        ((BatchScenario("ok", small_config()),), (), 1, "seed"),
        ((BatchScenario("../escape", small_config()),), (1,), 1, "unsafe"),
        (
            (BatchScenario("same", small_config()), BatchScenario("same", small_config())),
            (1,),
            1,
            "unique",
        ),
        ((BatchScenario("ok", small_config()),), (1, 1), 1, "unique"),
        ((BatchScenario("ok", small_config()),), (1,), 0, "jobs"),
    ],
)
def test_batch_rejects_ambiguous_or_unsafe_plans(tmp_path, scenarios, seeds, jobs, message):
    with pytest.raises(ValueError, match=message):
        run_batch(scenarios, seeds, tmp_path / "invalid", jobs=jobs)
    assert not (tmp_path / "invalid").exists()


def test_batch_refuses_to_merge_with_existing_output(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        run_batch((BatchScenario("ok", small_config()),), (1,), output)


def test_benchmark_repeats_same_state_and_records_positive_rates(tmp_path):
    report = benchmark(small_config(), steps=3, warmup=1, repeats=2)
    assert report["repeats"] == 2
    assert report["median_ticks_per_second"] > 0
    assert report["samples"][0]["state_digest"] == report["samples"][1]["state_digest"]

    persisted = benchmark_artifact(
        small_config(), tmp_path / "benchmark", steps=2, warmup=0, repeats=1
    )
    assert persisted["state_digest"]
    manifest = json.loads((tmp_path / "benchmark" / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert (tmp_path / "benchmark" / "config.resolved.yaml").is_file()


@pytest.mark.parametrize(
    ("steps", "warmup", "repeats"), ((0, 0, 1), (1, -1, 1), (1, 0, 0), (1, 0, 101))
)
def test_benchmark_rejects_invalid_parameters(steps, warmup, repeats):
    with pytest.raises(ValueError):
        benchmark(small_config(), steps=steps, warmup=warmup, repeats=repeats)
