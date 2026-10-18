"""Cross-process reproducibility and explicit resource accounting; no evolutionary claim."""

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from genesis.config import AgentConfig, dump_config, load_config
from genesis.history.artifacts import provenance, write_json

ROOT = Path(__file__).resolve().parents[2]


def execute(config: Path, seed: int, output: Path):
    command = [
        sys.executable,
        "-m",
        "genesis",
        "run",
        "--config",
        str(config),
        "--seed",
        str(seed),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr)
    summary = json.loads(result.stdout)
    if abs(summary["metrics"]["balance_error"]) >= 1e-8:
        raise AssertionError(f"Resource ledger failed: {output}")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    base = replace(
        load_config(ROOT / "configs" / "archipelago.yaml"),
        agents=AgentConfig(initial_count=0),
    )
    base_path = args.output.resolve() / "closed.yaml"
    base_path.write_text(dump_config(base), encoding="utf-8")
    periodic_path = args.output.resolve() / "periodic.yaml"
    periodic_path.write_text(
        dump_config(replace(base, world=replace(base.world, boundary="periodic"))),
        encoding="utf-8",
    )
    rows = []
    for scenario, config_path in (
        ("archipelago_closed", base_path),
        ("archipelago_periodic", periodic_path),
    ):
        digests = set()
        for seed in (0, 42, 2026):
            name = f"{scenario}_{seed}"
            a = execute(config_path, seed, args.output / f"{name}_a")
            b = execute(config_path, seed, args.output / f"{name}_b")
            if a["state_digest"] != b["state_digest"]:
                raise AssertionError(f"Nondeterministic {name}")
            for filename in ("metrics.jsonl", "config.resolved.yaml"):
                left = args.output / f"{name}_a" / filename
                right = args.output / f"{name}_b" / filename
                if left.read_bytes() != right.read_bytes():
                    raise AssertionError(f"Nondeterministic {filename}")
            rows.append({"scenario": scenario, "seed": seed, "repeat_equal": True, **a})
            digests.add(a["state_digest"])
        if len(digests) != 3:
            raise AssertionError("Different seeds produced identical states")
    control = execute(ROOT / "configs" / "closed_system.yaml", 42, args.output / "closed_control")
    rows.append({"scenario": "closed_control", "seed": 42, **control})
    if control["metrics"]["source_total"] != 0 or control["metrics"]["sink_total"] != 0:
        raise AssertionError("Closed control has an external flow")
    write_json(args.output / "report.json", {"provenance": provenance(), "results": rows})
    lines = [
        "# S01-1/S01-2 — проверка среды",
        "",
        "Все повторы идентичны; баланс проверен.",
        "",
        "| Сценарий | Seed | Тики | Суша | Ресурс | Остаток баланса |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        m = row["metrics"]
        lines.append(
            f"| {row['scenario']} | {row['seed']} | {m['tick']} | {m['land_cells']} | "
            f"{m['resource_total']:.8f} | {m['balance_error']:.3e} |"
        )
    lines += [
        "",
        "Это проверка инфраструктуры и законов среды. Агентов, наследственности и",
        "возникновения жизни в этом эксперименте нет.",
        "",
    ]
    (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "passed", "scenarios": len(rows), "process_runs": 13}))


if __name__ == "__main__":
    main()
