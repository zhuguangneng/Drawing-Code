#!/usr/bin/env python3
"""Independent checks for the headline primary and exploratory results."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def close(value: float, target: float, tolerance: float = 0.06) -> bool:
    return abs(value - target) <= tolerance


def main() -> None:
    with (RESULTS / "joint_scenarios.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    primary = next(row for row in rows if row["category"] == "main")
    exploratory = next(
        row for row in rows
        if row["category"] == "exploratory_particulate_extension"
        and row["scenario"] == "探索性主值"
    )

    with (RESULTS / "pattern_probabilities.csv").open(encoding="utf-8-sig", newline="") as handle:
        patterns = list(csv.DictReader(handle))
    primary_patterns = [
        row for row in patterns if row["overlap_scenario_key"] == "evidence_primary"
    ]
    probability_sum = sum(float(row["probability"]) for row in primary_patterns)

    checks = {
        "primary_increment_173_5": close(float(primary["additional_deaths_median"]), 173.5),
        "primary_joint_deaths_1172_8": close(float(primary["joint_deaths_median"]), 1172.8),
        "primary_relative_change_17_44": close(float(primary["percent_change_median"]), 17.44),
        "exploratory_E_increment_239_8": close(float(exploratory["additional_deaths_median"]), 239.8),
        "64_primary_pattern_probabilities_sum_to_1": (
            len(primary_patterns) == 64
            and math.isclose(probability_sum, 1.0, abs_tol=1e-12)
        ),
        "validation_report_passed": json.loads((RESULTS / "validation_report.json").read_text(encoding="utf-8"))["status"] == "PASS",
    }
    report = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
    (RESULTS / "upload_package_verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if report["status"] != "PASS":
        raise RuntimeError(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
