"""Reproduce S01-6 checkpoint integrity, event history and exact resume evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from genesis.config import AgentConfig, Config, RunConfig, TerrainConfig, WorldConfig, dump_config


def invoke(
    arguments: list[str], *, expect_success: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "genesis", *arguments],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if expect_success and result.returncode:
        raise RuntimeError(
            f"genesis {' '.join(arguments)} failed:\n{result.stdout}\n{result.stderr}"
        )
    return result


def summary(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(result.stdout)
    return value


def events(path: Path, event_type: str | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if event_type is None:
        return rows
    return [row for row in rows if row["type"] == event_type]


def npz_equal(left: Path, right: Path) -> bool:
    with np.load(left, allow_pickle=False) as a, np.load(right, allow_pickle=False) as b:
        return set(a.files) == set(b.files) and all(
            np.array_equal(a[name], b[name]) for name in a.files
        )


def verify_checkpoint(path: Path) -> bool:
    metadata = json.loads(path.with_suffix(".json").read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return (
        metadata["checkpoint_schema_version"] == 1
        and metadata["state_schema_version"] == 3
        and metadata["file"] == path.name
        and metadata["file_sha256"] == digest
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configs = args.output / "configs"
    configs.mkdir()

    base = Config(
        world=WorldConfig(width=48, height=32, boundary="periodic"),
        terrain=TerrainConfig(kind="uniform"),
        agents=AgentConfig(initial_count=96, max_population=2048, max_age=240),
        run=RunConfig(steps=180, metrics_interval=20, checkpoint_interval=60),
    )
    pairs: list[dict[str, Any]] = []
    max_balance = 0.0
    all_checkpoints: list[Path] = []
    corruption_source: Path | None = None
    for seed in (0, 42, 2026):
        config = replace(base, seed=seed)
        config_path = configs / f"seed-{seed}.yaml"
        config_path.write_text(dump_config(config), encoding="utf-8")
        continuous_dir = args.output / f"continuous-{seed}"
        first_dir = args.output / f"first-{seed}"
        resumed_dir = args.output / f"resumed-{seed}"

        continuous = summary(
            invoke(["run", "--config", str(config_path), "--output", str(continuous_dir)])
        )
        first = summary(
            invoke(
                [
                    "run",
                    "--config",
                    str(config_path),
                    "--steps",
                    "73",
                    "--output",
                    str(first_dir),
                ]
            )
        )
        checkpoint = first_dir / "checkpoints" / "tick-000000000073.npz"
        resumed = summary(
            invoke(
                [
                    "resume",
                    "--checkpoint",
                    str(checkpoint),
                    "--steps",
                    "107",
                    "--output",
                    str(resumed_dir),
                ]
            )
        )
        whole_ticks = events(continuous_dir / "events.jsonl", "tick")
        split_ticks = [
            *events(first_dir / "events.jsonl", "tick"),
            *events(resumed_dir / "events.jsonl", "tick"),
        ]
        all_events = [
            *events(continuous_dir / "events.jsonl"),
            *events(first_dir / "events.jsonl"),
            *events(resumed_dir / "events.jsonl"),
        ]
        genealogy_consistent = all(
            len(row["agents"]["born_ids"])
            == len(row["agents"]["parent_ids"])
            == row["agents"]["births"]
            and len(row["agents"]["dead_ids"]) == row["agents"]["deaths"]
            for row in all_events
            if row["type"] == "tick"
        )
        manifest = json.loads((resumed_dir / "manifest.json").read_text())
        pair = {
            "seed": seed,
            "continuous_digest": continuous["state_digest"],
            "resumed_digest": resumed["state_digest"],
            "digest_match": continuous["state_digest"] == resumed["state_digest"],
            "metrics_match": continuous["metrics"] == resumed["metrics"],
            "final_npz_match": npz_equal(
                continuous_dir / "final_state.npz", resumed_dir / "final_state.npz"
            ),
            "tick_events_match": whole_ticks == split_ticks,
            "event_genealogy_consistent": genealogy_consistent,
            "event_schema_valid": all(row["event_schema_version"] == 1 for row in all_events),
            "resume_start_tick": resumed["start_tick"],
            "resume_end_tick": resumed["end_tick"],
            "lineage_tick": manifest["resumed_from"]["tick"],
            "lineage_digest": manifest["resumed_from"]["state_digest"],
            "first_digest": first["state_digest"],
        }
        pairs.append(pair)
        max_balance = max(
            max_balance,
            abs(float(continuous["metrics"]["combined_balance_error"])),
            abs(float(resumed["metrics"]["combined_balance_error"])),
        )
        for directory in (continuous_dir, first_dir, resumed_dir):
            all_checkpoints.extend((directory / "checkpoints").glob("*.npz"))
        corruption_source = checkpoint

    if corruption_source is None:
        raise RuntimeError("no checkpoint selected for corruption test")
    corrupt_dir = args.output / "corruption-probe"
    corrupt_dir.mkdir()
    corrupt = corrupt_dir / corruption_source.name
    shutil.copy2(corruption_source, corrupt)
    shutil.copy2(corruption_source.with_suffix(".json"), corrupt.with_suffix(".json"))
    content = bytearray(corrupt.read_bytes())
    content[len(content) // 2] ^= 1
    corrupt.write_bytes(content)
    rejected_output = args.output / "corrupt-resume-must-not-exist"
    rejected = invoke(
        [
            "resume",
            "--checkpoint",
            str(corrupt),
            "--steps",
            "1",
            "--output",
            str(rejected_output),
        ],
        expect_success=False,
    )
    corruption_rejected = (
        rejected.returncode == 2
        and "SHA-256 mismatch" in rejected.stderr
        and not rejected_output.exists()
    )
    corrupt.unlink()
    corrupt.with_suffix(".json").unlink()
    corrupt_dir.rmdir()

    all_pairs_exact = all(
        pair["digest_match"]
        and pair["metrics_match"]
        and pair["final_npz_match"]
        and pair["tick_events_match"]
        and pair["event_genealogy_consistent"]
        and pair["event_schema_valid"]
        and pair["resume_start_tick"] == pair["lineage_tick"] == 73
        and pair["resume_end_tick"] == 180
        and pair["lineage_digest"] == pair["first_digest"]
        for pair in pairs
    )
    report = {
        "seeds": [0, 42, 2026],
        "process_runs": 9,
        "pairs": pairs,
        "all_pairs_exact": all_pairs_exact,
        "checkpoint_count": len(all_checkpoints),
        "all_checkpoint_hashes_valid": all(verify_checkpoint(path) for path in all_checkpoints),
        "all_run_logs_nonempty": all(
            path.stat().st_size > 0 for path in args.output.glob("*/run.log")
        ),
        "corruption_rejected_without_output": corruption_rejected,
        "max_abs_combined_balance_error": max_balance,
        "schema_versions": {"config": 4, "artifact": 4, "state": 3, "checkpoint": 1, "event": 1},
        "limitations": [
            "Only the current checkpoint schema is loaded; migrations are not implemented.",
            "Snapshots are complete local files, not incremental or distributed checkpoints.",
            "The event journal records the predefined-agent sandbox, not emergent life.",
        ],
    }
    required = (
        report["all_pairs_exact"],
        report["checkpoint_count"] == 21,
        report["all_checkpoint_hashes_valid"],
        report["all_run_logs_nonempty"],
        report["corruption_rejected_without_output"],
        report["max_abs_combined_balance_error"] < 1e-8,
    )
    if not all(required):
        raise RuntimeError(f"S01-6 acceptance failed: {report}")

    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# S01-6 acceptance report",
        "",
        f"- Independent process runs: {report['process_runs']}",
        f"- Exact continuous/resume pairs: {len(pairs)}/{len(pairs)}",
        f"- Integrity-checked checkpoints: {report['checkpoint_count']}",
        f"- Corruption rejected without output: {report['corruption_rejected_without_output']}",
        f"- Maximum combined balance error: {report['max_abs_combined_balance_error']:.3g}",
        "",
        "Exactness covers digest, metrics, final arrays and per-tick event history.",
    ]
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
