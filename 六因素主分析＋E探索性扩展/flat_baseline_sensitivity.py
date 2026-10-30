#!/usr/bin/env python3
"""Flat 2019-2022 registered-rate sensitivity for the Gaza cancer model.

The primary 2016-2022 quasi-Poisson trend is intentionally left unchanged.
This script adds a reviewer-requested structural sensitivity in which the 2023
counterfactual rate equals the arithmetic mean of the four observed crude
registered cancer mortality rates for 2019-2022. Uncertainty in that mean is
propagated with a normal approximation using the between-year standard error.
The existing fixed random seed and effect-size stream are reproduced exactly.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import random
from pathlib import Path

import numpy as np


N_SIM = 100_000
SEED = 20_260_921
POP_2023 = 2_226_544.0
Q = 3.0 / 12.0


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summary(x: np.ndarray) -> dict[str, float]:
    q = np.quantile(x, [0.025, 0.5, 0.975])
    return {"lower_2_5": float(q[0]), "median": float(q[1]), "upper_97_5": float(q[2])}


def prefixed(prefix: str, x: np.ndarray) -> dict[str, float]:
    return {f"{prefix}_{k}": v for k, v in summary(x).items()}


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    package_dir = Path(__file__).resolve().parent
    output_dir = Path(args.output_dir).resolve() if args.output_dir else package_dir / "results" / "flat_rate_sensitivity"
    output_dir.mkdir(parents=True, exist_ok=True)

    workspace = package_dir
    joint_path = package_dir / "joint_effect_monte_carlo_evidence_calibrated.py"
    joint = load_module(joint_path, "joint_e_excluded")
    current, authoritative_source = joint.load_authoritative_single_factor_model(workspace)

    # Reproduce the original effect-size random stream exactly: the primary
    # trend coefficients are drawn first, followed by A/D/H/P/E/C and T.
    fit = current.fit_poisson_offset(current.X, current.DEATHS, current.POPULATIONS)
    cov_quasi = current.scale_matrix(fit["covariance_poisson"], fit["pearson_phi"])
    rng_main = current.random.Random(SEED)
    current.draw_bivariate_normal(fit["coefficients"], cov_quasi, N_SIM, rng_main)

    effects_full: dict[str, np.ndarray] = {}
    for code, values in joint.FACTORS.items():
        log_draws = joint.draw_log_ratio_legacy(
            float(values["hr"]), float(values["lower"]), float(values["upper"]), rng_main
        )
        if values["effect_type"] == "per10":
            delta = float(values["delta_x_main"]) / 10.0
            effects_full[code] = np.exp(log_draws * delta)
        else:
            effects_full[code] = np.exp(log_draws)

    treatment_log4 = joint.draw_log_ratio_legacy(
        float(joint.TREATMENT["hr4"]),
        float(joint.TREATMENT["lower4"]),
        float(joint.TREATMENT["upper4"]),
        rng_main,
    )
    effects_full["T"] = np.exp(treatment_log4 * (float(joint.TREATMENT["delay_weeks"]) / 4.0))
    effects_primary = dict(effects_full)
    effects_primary["E"] = np.ones(N_SIM, dtype=float)

    # Reviewer-requested flat trend: arithmetic mean of the exact crude rates
    # from 2019-2022. The normal draw uses the between-year SE of the mean.
    deaths_2019_2022 = np.asarray(joint.DEATHS[3:7], dtype=float)
    pop_2019_2022 = np.asarray(joint.POPULATIONS[3:7], dtype=float)
    rates = deaths_2019_2022 / pop_2019_2022 * 100_000.0
    mean_rate = float(np.mean(rates))
    sd_rate = float(np.std(rates, ddof=1))
    se_rate = sd_rate / math.sqrt(len(rates))
    rng_flat = random.Random(SEED + 204)
    rate_draws = np.fromiter((rng_flat.gauss(mean_rate, se_rate) for _ in range(N_SIM)), dtype=float, count=N_SIM)
    if np.any(rate_draws <= 0):
        raise RuntimeError("Flat-rate normal approximation generated a nonpositive rate")
    baseline_flat = rate_draws * POP_2023 / 100_000.0

    f_main = joint.f_values("main")
    primary_row = joint.calculate_scenario(
        "2019–2022 average registered mortality rate (flat-rate sensitivity)",
        "baseline_model",
        baseline_flat,
        effects_primary,
        f_main,
        "evidence_primary",
        "evidence_calibrated",
        notes="E excluded; arithmetic mean of 2019–2022 crude registered cancer mortality rates; uncertainty from between-year SE.",
    )
    exploratory_row = joint.calculate_scenario(
        "2019–2022 average rate plus exploratory E (Δx=4.1 μg/m³)",
        "baseline_model_exploratory_e",
        baseline_flat,
        effects_full,
        f_main,
        "evidence_primary",
        "evidence_calibrated",
        notes="Exploratory extension only; flat-rate baseline plus October particulate proxy.",
    )

    factor_rows: list[dict[str, object]] = []
    for code in ("A", "D", "H", "P", "E", "C"):
        factor = joint.FACTORS[code]
        f = float(factor["f_main"])
        eff = effects_full[code]
        pct = 100.0 * Q * f * (eff - 1.0)
        increment = baseline_flat * pct / 100.0
        deaths = baseline_flat + increment
        row: dict[str, object] = {
            "code": code,
            "factor_en": factor["factor_en"],
            "analysis_role": "exploratory" if code == "E" else "factor-specific",
            "f": f,
        }
        row.update(prefixed("scenario_deaths", deaths))
        row.update(prefixed("additional_deaths", increment))
        row.update(prefixed("percent_change", pct))
        factor_rows.append(row)

    baseline_row: dict[str, object] = {
        "model_code": "flat_average_rate_2019_2022",
        "model_en": "2019–2022 average registered cancer mortality rate",
        "years": "2019–2022",
        "annual_rates_per_100000": ";".join(f"{x:.8f}" for x in rates),
        "mean_rate_per_100000": mean_rate,
        "between_year_sd": sd_rate,
        "standard_error_of_mean": se_rate,
        "target_population_2023": POP_2023,
        "point_baseline_deaths": mean_rate * POP_2023 / 100_000.0,
        "uncertainty_method": "Normal approximation around arithmetic mean rate using between-year SE",
    }
    baseline_row.update(prefixed("baseline_deaths", baseline_flat))

    # Extend the previously reported machine-readable tables without altering them.
    old_baselines = list(csv.DictReader((workspace / "results" / "baseline_models.csv").open(encoding="utf-8-sig")))
    extended_baselines = old_baselines + [{
        "model_code": "flat_average_rate_2019_2022",
        "model_zh": "2019—2022年平均登记死亡率（平坦趋势敏感性）",
        "baseline_deaths_lower_2_5": baseline_row["baseline_deaths_lower_2_5"],
        "baseline_deaths_median": baseline_row["baseline_deaths_median"],
        "baseline_deaths_upper_97_5": baseline_row["baseline_deaths_upper_97_5"],
    }]
    old_scenarios = list(csv.DictReader((workspace / "results" / "joint_scenarios.csv").open(encoding="utf-8-sig")))
    # Only the primary six-factor flat-rate scenario is added to the set of
    # reported joint sensitivities. The E-inclusive row is retained in the
    # dedicated file as an internal exploratory calculation.
    extended_scenarios = old_scenarios + [primary_row]

    write_csv(output_dir / "flat_rate_baseline.csv", [baseline_row])
    write_csv(output_dir / "factor_specific_flat_rate.csv", factor_rows)
    write_csv(output_dir / "joint_flat_rate.csv", [primary_row, exploratory_row])
    write_csv(output_dir / "baseline_models_extended.csv", extended_baselines)
    write_csv(output_dir / "joint_scenarios_extended.csv", extended_scenarios)

    result = {
        "definition": baseline_row,
        "primary_six_factor": primary_row,
        "exploratory_with_e": exploratory_row,
        "factor_specific": factor_rows,
        "verification": {
            "n_sim": N_SIM,
            "seed": SEED,
            "all_baseline_draws_positive": bool(np.all(baseline_flat > 0)),
            "all_outputs_finite": bool(np.all(np.isfinite(baseline_flat))),
            "primary_relative_change_identity": float(primary_row["percent_change_median"]),
            "authoritative_effect_source": str(authoritative_source),
        },
    }
    (output_dir / "analysis_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "mean_rate": mean_rate,
        "point_baseline": baseline_row["point_baseline_deaths"],
        "baseline_summary": summary(baseline_flat),
        "primary_increment": {
            "lower": primary_row["additional_deaths_lower_2_5"],
            "median": primary_row["additional_deaths_median"],
            "upper": primary_row["additional_deaths_upper_97_5"],
        },
        "primary_deaths": {
            "lower": primary_row["joint_deaths_lower_2_5"],
            "median": primary_row["joint_deaths_median"],
            "upper": primary_row["joint_deaths_upper_97_5"],
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
