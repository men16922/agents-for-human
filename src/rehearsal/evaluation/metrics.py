"""Read-only pilot metrics from independently audited practice-batch artifacts."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median

from rehearsal.evaluation.batch import summarize
from rehearsal.evaluation.frozen_run import METHODS
from rehearsal.world.storage import Json


def measured(cells: list[Json], key: str) -> Json:
    values = [
        c[key] for c in cells
        if c["status"] != "INVALID_EVIDENCE" and type(c.get(key)) is int and c[key] >= 0
    ]
    return {
        "recorded": sum(values),
        "cells_with_records": len(values),
        "unavailable_cells": len(cells) - len(values),
    }


def report(directory: Path) -> Json:
    audited = summarize(directory)
    methods = {}
    for method in METHODS:
        cells = [c for c in audited["cells"] if c["method"] == method]
        durations = sorted(
            c["duration_ns"] / 1_000_000_000
            for c in cells
            if type(c.get("duration_ns")) is int and c["duration_ns"] >= 0
        )
        methods[method] = {
            "planned": len(cells),
            "status_counts": dict(Counter(c["status"] for c in cells)),
            "goal_complete": sum(c["goal_complete"] for c in cells),
            "model_calls": measured(cells, "model_calls"),
            "tool_calls": measured(cells, "tool_calls"),
            "tokens": measured(cells, "recorded_total_tokens") | {
                "complete_usage_cells": sum(c["token_usage_complete"] for c in cells),
            },
            "recorded_micro_usd": sum(c["recorded_micro_usd"] for c in cells),
            "unresolved_reserved_micro_usd": sum(
                c["unresolved_reserved_micro_usd"] for c in cells
            ),
            "duration": {
                "basis": "single-process-monotonic-cell-total",
                "samples": len(durations),
                "unavailable_cells": len(cells) - len(durations),
                "median_seconds": median(durations) if durations else None,
                "p95_seconds": durations[math.ceil(len(durations) * 0.95) - 1]
                if durations else None,
            },
        }
    return {
        "batch_id": audited["batch_id"],
        "scope": audited["scope"],
        "planned": audited["planned"],
        "status_counts": audited["status_counts"],
        "methods": methods,
        "model_efficacy_verified": False,
        "held_out_evaluation_verified": False,
        "timing_scope": "Entire uninterrupted cell, including learning and evaluation; "
        "excludes batch preparation and reporting. Not provider latency or recovery time.",
        "token_scope": "Sum of recorded input, output, cache-read and cache-write tokens; "
        "partial usage remains partial. Missing and invalid evidence is unavailable.",
    }


def markdown(value: Json) -> str:
    def number(n: float | None) -> str:
        return "unavailable" if n is None else f"{n:.3f}"

    lines = [
        "# Practice batch metrics", "",
        f"Batch: `{value['batch_id']}`", f"Scope: `{value['scope']}`", "",
        "| Arm | Goal complete / planned | Recorded tokens | Complete usage cells | "
        "Tool calls (observed cells) | Recorded USD | Reserved USD | "
        "Median / p95 seconds (samples) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, row in value["methods"].items():
        tokens, tools, duration = row["tokens"], row["tool_calls"], row["duration"]
        token_text = str(tokens["recorded"]) if tokens["cells_with_records"] else "unavailable"
        tool_text = str(tools["recorded"]) if tools["cells_with_records"] else "unavailable"
        lines.append(
            f"| {method} | {row['goal_complete']} / {row['planned']} | {token_text} | "
            f"{tokens['complete_usage_cells']} / {row['planned']} | "
            f"{tool_text} ({tools['cells_with_records']}) | "
            f"{row['recorded_micro_usd'] / 1_000_000:.6f} | "
            f"{row['unresolved_reserved_micro_usd'] / 1_000_000:.6f} | "
            f"{number(duration['median_seconds'])} / {number(duration['p95_seconds'])} "
            f"({duration['samples']}) |"
        )
    lines.extend(["", "Statuses retain the full denominator:", ""])
    lines.extend(
        f"- {method}: {json.dumps(row['status_counts'], sort_keys=True)}"
        for method, row in value["methods"].items()
    )
    lines.extend([
        "", value["timing_scope"], "", value["token_scope"], "",
        "Recorded costs exclude unresolved reservations; unexecuted cells are not free model "
        "runs. Offline fixture costs are fictional. These metrics do not establish model "
        "efficacy, held-out performance, provider billing, or developer time savings.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    value = report(args.directory)
    print(json.dumps(value, indent=2) if args.format == "json" else markdown(value), end="\n")


if __name__ == "__main__":
    main()
