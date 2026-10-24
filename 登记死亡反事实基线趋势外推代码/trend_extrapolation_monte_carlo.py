#!/usr/bin/env python3
"""Reproducible trend extrapolation and six-factor Monte Carlo analysis.

This script deliberately uses only Python's standard library so that it can be
rerun with the bundled Codex Python.  The primary 2023 counterfactual baseline
is obtained from a Poisson log-linear rate trend with a population offset.  The
coefficient covariance matrix is multiplied by the Pearson dispersion estimate
(quasi-Poisson covariance) before joint coefficient sampling.

By default outputs are written to outputs/manuscript_revision under the
workspace.  A different directory can be supplied with --output-dir.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


N_SIM = 100_000
SEED = 20_260_921
Z_975 = 1.959963984540054
M_FRACTION = 3.0 / 12.0

YEARS = [2016, 2017, 2018, 2019, 2020, 2021, 2022]
X = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
DEATHS = [348.0, 474.0, 566.0, 548.0, 539.0, 777.0, 915.0]
POPULATIONS = [
    1_828_614.0,
    1_876_666.0,
    1_932_843.0,
    1_989_970.0,
    2_047_969.0,
    2_106_745.0,
    2_166_269.0,
]
YEAR_TARGET = 2023
X_TARGET = 7.0
POP_TARGET = 2_226_544.0


FACTORS = [
    {
        "code": "A",
        "factor_en": "Barriers to health services accessibility",
        "factor_zh": "医疗服务可及性障碍",
        "model": "random",
        "hr": 1.12659694615175,
        "lower": 0.938382545820733,
        "upper": 1.35256211310746,
        "i2": 84.1,
        "f_main": 0.20,
        "f_low": 0.18,
        "f_high": 0.22,
        "fixed_hr": 0.944145613660327,
        "fixed_lower": 0.901868410767962,
        "fixed_upper": 0.988404659871586,
        "effect_type": "direct",
    },
    {
        "code": "D",
        "factor_en": "Delayed diagnosis",
        "factor_zh": "诊断延迟",
        "model": "random",
        "hr": 1.40082399155868,
        "lower": 1.07727003955917,
        "upper": 1.82155614030571,
        "i2": 54.9,
        "f_main": 0.75,
        "f_low": 0.50,
        "f_high": 1.00,
        "fixed_hr": 1.31514774947357,
        "fixed_lower": 1.17326023568769,
        "fixed_upper": 1.47419434353505,
        "effect_type": "direct",
    },
    {
        "code": "H",
        "factor_en": "Health workforce loss or shortage",
        "factor_zh": "医务人员损失或短缺",
        "model": "random",
        "hr": 1.01302594039352,
        "lower": 0.941311605866301,
        "upper": 1.0902038703387,
        "i2": 73.8,
        "f_main": 0.70,
        "f_low": 0.50,
        "f_high": 0.90,
        "fixed_hr": 1.01333526619584,
        "fixed_lower": 0.98544352878683,
        "fixed_upper": 1.04201644408822,
        "effect_type": "direct",
    },
    {
        "code": "P",
        "factor_en": "Psychosocial stress",
        "factor_zh": "心理社会压力",
        "model": "random",
        "hr": 1.23650966032884,
        "lower": 1.018684077252,
        "upper": 1.50091296627611,
        "i2": 58.7,
        "f_main": 0.80,
        "f_low": 0.50,
        "f_high": 0.94,
        "fixed_hr": 1.21802482826318,
        "fixed_lower": 1.0958531128707,
        "fixed_upper": 1.35381691655658,
        "effect_type": "direct",
    },
    {
        "code": "E",
        "factor_en": "Exposure to combustion smoke, coal dust or particulates",
        "factor_zh": "燃烧烟雾、煤尘或颗粒物暴露",
        "model": "random",
        "hr": 1.4270702743758,
        "lower": 1.07526525525956,
        "upper": 1.89397877225693,
        "i2": 98.7,
        "f_main": 1.00,
        "f_low": 1.00,
        "f_high": 1.00,
        "fixed_hr": 1.01289527620331,
        "fixed_lower": 0.996933330590114,
        "fixed_upper": 1.02911278926514,
        "effect_type": "per10",
        "delta_x_main": 4.1,
        "delta_x_low": 0.5,
        "delta_x_high": 7.2,
        "analysis_role_zh": "探索性分析",
        "analysis_note_zh": "主增量来自2023年10月单月监测值；不能代表11—12月，第四季度外推存在月际变化不确定性。",
    },
    {
        "code": "C",
        "factor_en": "Patient-provider communication barriers",
        "factor_zh": "患者—医务人员沟通障碍",
        "model": "fixed",
        "hr": 1.3521517680129,
        "lower": 0.978326692568816,
        "upper": 1.86881786792485,
        "i2": 0.0,
        "f_main": 197.0 / 658.0,
        "f_low": 66.0 / 658.0,
        "f_high": 361.0 / 658.0,
        "fixed_hr": 1.3521517680129,
        "fixed_lower": 0.978326692568816,
        "fixed_upper": 1.86881786792485,
        "effect_type": "direct",
        "f_definition_zh": "低值=Very poor；主值=Very poor+Poor；高值=除Excellent和Fair外（Good+Poor+Very poor）",
    },
]

# C的旧分级把Fair纳入沟通障碍。按用户要求，旧方案不再作为主分析，
# 仅保留为定义敏感性，以便结果可追溯且不丢失既有计算。
C_LEGACY_F_SCENARIOS = [
    ("旧定义敏感性：Poor+Very poor", 197.0 / 658.0),
    ("旧定义敏感性：Fair+Poor+Very poor", 395.0 / 658.0),
    ("旧定义敏感性：除Excellent外", 559.0 / 658.0),
]


def inv2(matrix: Sequence[Sequence[float]]) -> List[List[float]]:
    a, b = matrix[0]
    c, d = matrix[1]
    det = a * d - b * c
    if det <= 0.0:
        raise ValueError(f"Matrix is not positive definite: determinant={det}")
    return [[d / det, -b / det], [-c / det, a / det]]


def mat_vec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> List[float]:
    return [sum(a * b for a, b in zip(row, vector)) for row in matrix]


def fit_poisson_offset(
    x: Sequence[float], y: Sequence[float], population: Sequence[float]
) -> Dict[str, object]:
    """Fit log(mu)=alpha+beta*x+log(population) by Fisher scoring."""
    if not (len(x) == len(y) == len(population)):
        raise ValueError("Input lengths differ")
    beta = [math.log(sum(y) / sum(population)), 0.0]
    for iteration in range(100):
        mu = [p * math.exp(beta[0] + beta[1] * xi) for xi, p in zip(x, population)]
        score = [
            sum(yi - mui for yi, mui in zip(y, mu)),
            sum(xi * (yi - mui) for xi, yi, mui in zip(x, y, mu)),
        ]
        info = [
            [sum(mu), sum(xi * mui for xi, mui in zip(x, mu))],
            [
                sum(xi * mui for xi, mui in zip(x, mu)),
                sum(xi * xi * mui for xi, mui in zip(x, mu)),
            ],
        ]
        step = mat_vec(inv2(info), score)
        beta_new = [beta[0] + step[0], beta[1] + step[1]]
        if max(abs(beta_new[i] - beta[i]) for i in range(2)) < 1e-13:
            beta = beta_new
            break
        beta = beta_new
    else:
        raise RuntimeError("Poisson fit did not converge")

    mu = [p * math.exp(beta[0] + beta[1] * xi) for xi, p in zip(x, population)]
    info = [
        [sum(mu), sum(xi * mui for xi, mui in zip(x, mu))],
        [
            sum(xi * mui for xi, mui in zip(x, mu)),
            sum(xi * xi * mui for xi, mui in zip(x, mu)),
        ],
    ]
    covariance = inv2(info)
    residual_df = len(x) - 2
    pearson_chi2 = sum((yi - mui) ** 2 / mui for yi, mui in zip(y, mu))
    deviance = 0.0
    for yi, mui in zip(y, mu):
        if yi > 0.0:
            deviance += 2.0 * (yi * math.log(yi / mui) - (yi - mui))
        else:
            deviance += 2.0 * mui
    phi = pearson_chi2 / residual_df if residual_df > 0 else None
    deviance_scale = deviance / residual_df if residual_df > 0 else None
    return {
        "coefficients": beta,
        "fitted": mu,
        "covariance_poisson": covariance,
        "pearson_chi2": pearson_chi2,
        "deviance": deviance,
        "residual_df": residual_df,
        "pearson_phi": phi,
        "deviance_per_df": deviance_scale,
        "iterations": iteration + 1,
    }


def fit_ols(x: Sequence[float], y: Sequence[float]) -> Dict[str, object]:
    n = len(x)
    xbar = sum(x) / n
    ybar = sum(y) / n
    sxx = sum((xi - xbar) ** 2 for xi in x)
    slope = sum((xi - xbar) * (yi - ybar) for xi, yi in zip(x, y)) / sxx
    intercept = ybar - slope * xbar
    fitted = [intercept + slope * xi for xi in x]
    residuals = [yi - fi for yi, fi in zip(y, fitted)]
    residual_df = n - 2
    rss = sum(e * e for e in residuals)
    sigma2 = rss / residual_df
    xtx = [[float(n), sum(x)], [sum(x), sum(xi * xi for xi in x)]]
    covariance_unit = inv2(xtx)
    covariance = [[sigma2 * value for value in row] for row in covariance_unit]
    return {
        "coefficients": [intercept, slope],
        "fitted": fitted,
        "residuals": residuals,
        "rss": rss,
        "residual_df": residual_df,
        "sigma2": sigma2,
        "covariance": covariance,
    }


def scale_matrix(matrix: Sequence[Sequence[float]], scale: float) -> List[List[float]]:
    return [[scale * value for value in row] for row in matrix]


def cholesky2(covariance: Sequence[Sequence[float]]) -> Tuple[float, float, float]:
    l00 = math.sqrt(covariance[0][0])
    l10 = covariance[1][0] / l00
    remainder = covariance[1][1] - l10 * l10
    if remainder < 0.0 and abs(remainder) < 1e-18:
        remainder = 0.0
    l11 = math.sqrt(remainder)
    return l00, l10, l11


def draw_bivariate_normal(
    mean: Sequence[float], covariance: Sequence[Sequence[float]], n: int, rng: random.Random
) -> Tuple[List[float], List[float]]:
    l00, l10, l11 = cholesky2(covariance)
    first: List[float] = []
    second: List[float] = []
    append_first = first.append
    append_second = second.append
    for _ in range(n):
        z0 = rng.gauss(0.0, 1.0)
        z1 = rng.gauss(0.0, 1.0)
        append_first(mean[0] + l00 * z0)
        append_second(mean[1] + l10 * z0 + l11 * z1)
    return first, second


def percentile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot calculate percentile of empty data")
    h = (len(sorted_values) - 1) * probability
    lo = int(math.floor(h))
    hi = int(math.ceil(h))
    if lo == hi:
        return sorted_values[lo]
    weight = h - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def summarize(values: Iterable[float]) -> Dict[str, float]:
    ordered = sorted(values)
    return {
        "lower_2_5": percentile(ordered, 0.025),
        "median": percentile(ordered, 0.5),
        "upper_97_5": percentile(ordered, 0.975),
    }


def log_hr_parameters(point: float, lower: float, upper: float) -> Tuple[float, float]:
    mean = math.log(point)
    se = (math.log(upper) - math.log(lower)) / (2.0 * Z_975)
    return mean, se


def effect_draws_from_log_hr(log_hr: Sequence[float], factor: Dict[str, object], delta_x=None):
    if factor["effect_type"] == "direct":
        return [math.exp(value) for value in log_hr]
    delta = float(factor["delta_x_main"] if delta_x is None else delta_x)
    return [math.exp(value * delta / 10.0) for value in log_hr]


def scenario_draws(
    baseline: Sequence[float],
    effect: Sequence[float],
    f_value: float,
    g_value: float,
) -> Tuple[List[float], List[float], List[float]]:
    k = M_FRACTION * f_value * g_value
    scenario: List[float] = []
    increment: List[float] = []
    percent_change: List[float] = []
    append_s = scenario.append
    append_i = increment.append
    append_p = percent_change.append
    for d0, e in zip(baseline, effect):
        rel = k * (e - 1.0)
        change = d0 * rel
        append_s(d0 + change)
        append_i(change)
        append_p(rel * 100.0)
    return scenario, increment, percent_change


def baseline_from_log_coefficients(
    intercepts: Sequence[float], slopes: Sequence[float]
) -> List[float]:
    return [
        POP_TARGET * math.exp(a + X_TARGET * b)
        for a, b in zip(intercepts, slopes)
    ]


def baseline_from_linear_coefficients(
    intercepts: Sequence[float], slopes: Sequence[float]
) -> List[float]:
    values = [a + X_TARGET * b for a, b in zip(intercepts, slopes)]
    # The fitted distribution is far from zero here.  The explicit check makes
    # an invalid structural sensitivity visible rather than silently truncating.
    if min(values) <= 0.0:
        raise ValueError("Linear-count coefficient draws produced a non-positive baseline")
    return values


def format_summary(prefix: str, summary: Dict[str, float]) -> Dict[str, float]:
    return {
        f"{prefix}_median": summary["median"],
        f"{prefix}_lower_2_5": summary["lower_2_5"],
        f"{prefix}_upper_97_5": summary["upper_97_5"],
    }


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def factor_identity(factor: Dict[str, object]) -> Dict[str, object]:
    identity = {
        "code": factor["code"],
        "factor_zh": factor["factor_zh"],
        "factor_en": factor["factor_en"],
    }
    if factor.get("analysis_role_zh"):
        identity["analysis_role_zh"] = factor["analysis_role_zh"]
        identity["analysis_note_zh"] = factor.get("analysis_note_zh", "")
    return identity


def calculate() -> Dict[str, object]:
    main_fit = fit_poisson_offset(X, DEATHS, POPULATIONS)
    beta_hat = main_fit["coefficients"]
    cov_poisson = main_fit["covariance_poisson"]
    phi = float(main_fit["pearson_phi"])
    cov_quasi = scale_matrix(cov_poisson, phi)

    point_baseline = POP_TARGET * math.exp(beta_hat[0] + beta_hat[1] * X_TARGET)
    point_rate = point_baseline / POP_TARGET * 100_000.0
    prediction_vector = [1.0, X_TARGET]

    def linpred_variance(cov):
        return (
            cov[0][0]
            + 2.0 * X_TARGET * cov[0][1]
            + X_TARGET * X_TARGET * cov[1][1]
        )

    quasi_lp_se = math.sqrt(linpred_variance(cov_quasi))
    poisson_lp_se = math.sqrt(linpred_variance(cov_poisson))

    rng = random.Random(SEED)
    main_a, main_b = draw_bivariate_normal(beta_hat, cov_quasi, N_SIM, rng)
    baseline_main = baseline_from_log_coefficients(main_a, main_b)
    baseline_main_summary = summarize(baseline_main)

    # All six primary log-HR samples use the same master stream after the joint
    # trend-coefficient samples; they remain independent of the baseline draws.
    main_log_hr_draws: Dict[str, List[float]] = {}
    for factor in FACTORS:
        log_mean, log_se = log_hr_parameters(
            float(factor["hr"]), float(factor["lower"]), float(factor["upper"])
        )
        main_log_hr_draws[str(factor["code"])] = [
            rng.gauss(log_mean, log_se) for _ in range(N_SIM)
        ]

    historical_rows = []
    for year, xi, deaths, population, fitted in zip(
        YEARS, X, DEATHS, POPULATIONS, main_fit["fitted"]
    ):
        historical_rows.append(
            {
                "year": year,
                "t": int(xi),
                "registered_cancer_deaths": int(deaths),
                "midyear_population": int(population),
                "crude_rate_per_100000": deaths / population * 100_000.0,
                "poisson_fitted_deaths": fitted,
                "poisson_fitted_rate_per_100000": fitted / population * 100_000.0,
            }
        )

    # Expanding-window, one-step-ahead point validation.  Each fold starts
    # with the minimum two observations required for an intercept and slope.
    backtest_rows = []
    for end_index in range(1, len(YEARS) - 1):
        fold_fit = fit_poisson_offset(
            X[: end_index + 1], DEATHS[: end_index + 1], POPULATIONS[: end_index + 1]
        )
        target_index = end_index + 1
        prediction = POPULATIONS[target_index] * math.exp(
            fold_fit["coefficients"][0]
            + fold_fit["coefficients"][1] * X[target_index]
        )
        observed = DEATHS[target_index]
        error = prediction - observed
        backtest_rows.append(
            {
                "training_years": f"{YEARS[0]}–{YEARS[end_index]}",
                "prediction_year": YEARS[target_index],
                "observed_deaths": observed,
                "predicted_deaths": prediction,
                "error_predicted_minus_observed": error,
                "absolute_error": abs(error),
                "absolute_percentage_error_percent": abs(error) / observed * 100.0,
            }
        )
    mape = sum(row["absolute_percentage_error_percent"] for row in backtest_rows) / len(
        backtest_rows
    )
    mae = sum(row["absolute_error"] for row in backtest_rows) / len(backtest_rows)
    rmse = math.sqrt(
        sum(row["error_predicted_minus_observed"] ** 2 for row in backtest_rows)
        / len(backtest_rows)
    )

    main_rows: List[Dict[str, object]] = []
    for factor in FACTORS:
        code = str(factor["code"])
        effects = effect_draws_from_log_hr(main_log_hr_draws[code], factor)
        scenario, increment, percent = scenario_draws(
            baseline_main, effects, float(factor["f_main"]), 1.0
        )
        row = factor_identity(factor)
        row.update(
            {
                "meta_model": factor["model"],
                "pooled_hr": factor["hr"],
                "hr_lower_95": factor["lower"],
                "hr_upper_95": factor["upper"],
                "i2_percent": factor["i2"],
                "f": factor["f_main"],
                "g": 1.0,
                "duration_fraction": M_FRACTION,
                "delta_x": factor.get("delta_x_main", ""),
            }
        )
        row.update(format_summary("effective_hr", summarize(effects)))
        row.update(format_summary("scenario_deaths", summarize(scenario)))
        row.update(format_summary("additional_deaths", summarize(increment)))
        row.update(format_summary("percent_change", summarize(percent)))
        row["p_additional_deaths_positive_percent"] = (
            100.0 * sum(value > 0.0 for value in increment) / N_SIM
        )
        main_rows.append(row)

    # Fixed-effect meta-analytic sensitivity.
    fixed_rng = random.Random(SEED + 101)
    fixed_rows: List[Dict[str, object]] = []
    for factor in FACTORS:
        log_mean, log_se = log_hr_parameters(
            float(factor["fixed_hr"]),
            float(factor["fixed_lower"]),
            float(factor["fixed_upper"]),
        )
        fixed_log_hr = [fixed_rng.gauss(log_mean, log_se) for _ in range(N_SIM)]
        effects = effect_draws_from_log_hr(fixed_log_hr, factor)
        _, increments, percents = scenario_draws(
            baseline_main, effects, float(factor["f_main"]), 1.0
        )
        row = factor_identity(factor)
        row.update(
            {
                "fixed_hr": factor["fixed_hr"],
                "fixed_hr_lower_95": factor["fixed_lower"],
                "fixed_hr_upper_95": factor["fixed_upper"],
                "f": factor["f_main"],
                "g": 1.0,
                "delta_x": factor.get("delta_x_main", ""),
            }
        )
        row.update(format_summary("additional_deaths", summarize(increments)))
        row.update(format_summary("percent_change", summarize(percents)))
        fixed_rows.append(row)

    # f sensitivity: factor-specific low, main, and high values.  The same HR
    # and baseline draws are reused so differences isolate the f assumption.
    f_rows: List[Dict[str, object]] = []
    for factor in FACTORS:
        code = str(factor["code"])
        effects = effect_draws_from_log_hr(main_log_hr_draws[code], factor)
        f_scenarios = [
            ("low", float(factor["f_low"])),
            ("main", float(factor["f_main"])),
            ("high", float(factor["f_high"])),
        ]
        seen = set()
        for label, f_value in f_scenarios:
            # Keep all named scenarios even when a factor's f is fixed at 1;
            # this makes the absence of f uncertainty explicit.
            _, increments, percents = scenario_draws(baseline_main, effects, f_value, 1.0)
            row = factor_identity(factor)
            row.update({"f_scenario": label, "f": f_value, "g": 1.0})
            row.update(format_summary("additional_deaths", summarize(increments)))
            row.update(format_summary("percent_change", summarize(percents)))
            f_rows.append(row)
            seen.add(f_value)

    communication = next(factor for factor in FACTORS if factor["code"] == "C")
    communication_effects = effect_draws_from_log_hr(
        main_log_hr_draws["C"], communication
    )
    for label, f_value in C_LEGACY_F_SCENARIOS:
        _, increments, percents = scenario_draws(
            baseline_main, communication_effects, f_value, 1.0
        )
        row = factor_identity(communication)
        row.update(
            {
                "f_scenario": label,
                "f": f_value,
                "g": 1.0,
                "f_definition": "旧方案；包含Fair，仅作敏感性分析",
            }
        )
        row.update(format_summary("additional_deaths", summarize(increments)))
        row.update(format_summary("percent_change", summarize(percents)))
        f_rows.append(row)

    # g sensitivity.  g=1 is retained as the reference row.
    g_rows: List[Dict[str, object]] = []
    for factor in FACTORS:
        code = str(factor["code"])
        effects = effect_draws_from_log_hr(main_log_hr_draws[code], factor)
        for g_value in [0.35, 0.50, 0.65, 1.00]:
            _, increments, percents = scenario_draws(
                baseline_main, effects, float(factor["f_main"]), g_value
            )
            row = factor_identity(factor)
            row.update(
                {
                    "g_scenario": "main" if g_value == 1.0 else "sensitivity",
                    "f": factor["f_main"],
                    "g": g_value,
                }
            )
            row.update(format_summary("additional_deaths", summarize(increments)))
            row.update(format_summary("percent_change", summarize(percents)))
            g_rows.append(row)

    # Particulate concentration increment sensitivity.
    particulate = next(f for f in FACTORS if f["code"] == "E")
    particulate_log_hr = main_log_hr_draws["E"]
    particulate_rows: List[Dict[str, object]] = []
    for label, delta_x, f_value in [
        ("low", particulate["delta_x_low"], 1.00),
        ("main", particulate["delta_x_main"], 1.00),
        ("high", particulate["delta_x_high"], 1.00),
        ("no_change", 0.0, 1.00),
        ("satellite_alternative", -1.16, 1.00),
        ("household_fuel_smoke", 10.0, 0.92),
    ]:
        effects = effect_draws_from_log_hr(particulate_log_hr, particulate, delta_x)
        _, increments, percents = scenario_draws(
            baseline_main, effects, f_value, 1.0
        )
        row = factor_identity(particulate)
        row.update({"delta_x_scenario": label, "delta_x": delta_x, "f": f_value, "g": 1.0})
        row.update(format_summary("effective_hr", summarize(effects)))
        row.update(format_summary("additional_deaths", summarize(increments)))
        row.update(format_summary("percent_change", summarize(percents)))
        particulate_rows.append(row)

    # Alternative baseline models.  Coefficient uncertainty is sampled from a
    # multivariate normal in all four models so the structural comparison is
    # not confounded by a different sampling family.
    ordinary_rng = random.Random(SEED + 201)
    ordinary_a, ordinary_b = draw_bivariate_normal(
        beta_hat, cov_poisson, N_SIM, ordinary_rng
    )
    baseline_ordinary = baseline_from_log_coefficients(ordinary_a, ordinary_b)

    linear_fit = fit_ols(X, DEATHS)
    linear_rng = random.Random(SEED + 202)
    linear_a, linear_b = draw_bivariate_normal(
        linear_fit["coefficients"], linear_fit["covariance"], N_SIM, linear_rng
    )
    baseline_linear = baseline_from_linear_coefficients(linear_a, linear_b)

    crude_rates = [y / p * 100_000.0 for y, p in zip(DEATHS, POPULATIONS)]
    log_rate_fit = fit_ols(X, [math.log(rate) for rate in crude_rates])
    log_rate_rng = random.Random(SEED + 203)
    log_rate_a, log_rate_b = draw_bivariate_normal(
        log_rate_fit["coefficients"], log_rate_fit["covariance"], N_SIM, log_rate_rng
    )
    baseline_log_rate = [
        POP_TARGET / 100_000.0 * math.exp(a + X_TARGET * b)
        for a, b in zip(log_rate_a, log_rate_b)
    ]

    baseline_model_draws = [
        (
            "quasi_poisson_primary",
            "泊松对数线性率趋势（Pearson离散度修正，主分析）",
            baseline_main,
        ),
        ("ordinary_poisson", "普通泊松对数线性率趋势", baseline_ordinary),
        ("linear_count", "登记死亡数线性趋势", baseline_linear),
        ("log_linear_rate", "粗死亡率对数线性趋势", baseline_log_rate),
    ]

    baseline_summary_rows = []
    baseline_sensitivity_rows: List[Dict[str, object]] = []
    for model_code, model_zh, baseline_draws in baseline_model_draws:
        base_summary = summarize(baseline_draws)
        baseline_summary_row = {"model_code": model_code, "model_zh": model_zh}
        baseline_summary_row.update(format_summary("baseline_deaths", base_summary))
        baseline_summary_rows.append(baseline_summary_row)
        for factor in FACTORS:
            code = str(factor["code"])
            effects = effect_draws_from_log_hr(main_log_hr_draws[code], factor)
            _, increments, percents = scenario_draws(
                baseline_draws, effects, float(factor["f_main"]), 1.0
            )
            row = {"model_code": model_code, "model_zh": model_zh}
            row.update(factor_identity(factor))
            row.update(format_summary("additional_deaths", summarize(increments)))
            row.update(format_summary("percent_change", summarize(percents)))
            baseline_sensitivity_rows.append(row)

    model_summary = {
        "model": "Poisson log-linear rate trend with population offset",
        "equation": "log(mu_t) = alpha + beta*(year-2016) + log(population_t)",
        "years_used": YEARS,
        "n_observations": len(YEARS),
        "coefficients": {
            "alpha": beta_hat[0],
            "beta_year": beta_hat[1],
            "annual_rate_ratio": math.exp(beta_hat[1]),
            "annual_rate_change_percent": (math.exp(beta_hat[1]) - 1.0) * 100.0,
        },
        "covariance_poisson": cov_poisson,
        "pearson_chi2": main_fit["pearson_chi2"],
        "residual_df": main_fit["residual_df"],
        "pearson_phi": phi,
        "deviance": main_fit["deviance"],
        "deviance_per_df": main_fit["deviance_per_df"],
        "covariance_quasi_poisson": cov_quasi,
        "target_year": YEAR_TARGET,
        "target_population": int(POP_TARGET),
        "point_prediction_deaths": point_baseline,
        "point_prediction_rate_per_100000": point_rate,
        "analytic_quasi_poisson_mean_ci": {
            "lower": point_baseline * math.exp(-Z_975 * quasi_lp_se),
            "upper": point_baseline * math.exp(Z_975 * quasi_lp_se),
            "log_scale_se": quasi_lp_se,
        },
        "analytic_ordinary_poisson_mean_ci": {
            "lower": point_baseline * math.exp(-Z_975 * poisson_lp_se),
            "upper": point_baseline * math.exp(Z_975 * poisson_lp_se),
            "log_scale_se": poisson_lp_se,
        },
        "monte_carlo_baseline_primary": baseline_main_summary,
        "backtest": {
            "folds": len(backtest_rows),
            "mape_percent": mape,
            "mae_deaths": mae,
            "rmse_deaths": rmse,
            "interpretation": f"Internal temporal validation with {len(backtest_rows)} expanding-window one-step-ahead folds.",
        },
        "alternative_baseline_models": {
            "linear_count": linear_fit,
            "log_linear_crude_rate": log_rate_fit,
        },
    }

    assumptions = {
        "estimand": "Expected 2023 counterfactual cancer deaths on the Gaza pre-war registration scale",
        "not_estimand": "True total cancer deaths or observed 2023 registered deaths",
        "simulation_draws": N_SIM,
        "master_seed": SEED,
        "duration_months": 3,
        "duration_fraction": M_FRACTION,
        "g_primary": 1.0,
        "g_sensitivity": [0.35, 0.50, 0.65],
        "uncertainty_interval": "2.5th and 97.5th Monte Carlo percentiles",
        "primary_baseline_uncertainty": "Joint MVN sampling of alpha and beta using Pearson-scaled Poisson covariance; no additional Poisson process count was drawn.",
        "hr_uncertainty": "Normal sampling on log-HR scale; SE recovered from reported 95% CI.",
        "factor_combination": "Factors are evaluated one at a time and are not multiplied or summed into a joint effect.",
        "structural_baseline_sensitivity": "All coefficient vectors sampled from multivariate normal approximations; alternative OLS models use residual-variance covariance.",
        "particulate_analysis_role": "Exploratory: the primary concentration increment is based on October 2023 only and does not observe November or December variation.",
        "communication_primary_definition": "low=Very poor (66/658); main=Very poor+Poor (197/658); high=Good+Poor+Very poor, excluding Excellent and Fair (361/658)",
        "communication_legacy_definition_sensitivity": "197/658, 395/658, and 559/658 retained only as definition sensitivity because Fair is included in the latter two legacy categories.",
    }

    return {
        "historical_rows": historical_rows,
        "backtest_rows": backtest_rows,
        "model_summary": model_summary,
        "assumptions": assumptions,
        "main_rows": main_rows,
        "fixed_rows": fixed_rows,
        "f_rows": f_rows,
        "g_rows": g_rows,
        "particulate_rows": particulate_rows,
        "baseline_summary_rows": baseline_summary_rows,
        "baseline_sensitivity_rows": baseline_sensitivity_rows,
        "factor_inputs": FACTORS,
    }


def find_workspace(script_dir: Path) -> Path:
    for candidate in (script_dir, *script_dir.parents):
        if (candidate / "outputs").is_dir() and (candidate / "work").is_dir():
            return candidate
    raise RuntimeError("Could not locate workspace containing outputs/ and work/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for JSON, CSV and README outputs; defaults to outputs/manuscript_revision.",
    )
    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent
    workspace = find_workspace(script_dir)
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else workspace / "outputs" / "manuscript_revision"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    results = calculate()
    write_csv(output_dir / "historical_registered_deaths.csv", results["historical_rows"])
    write_csv(output_dir / "rolling_backtest.csv", results["backtest_rows"])
    write_csv(output_dir / "main_six_factor_results.csv", results["main_rows"])
    write_csv(output_dir / "sensitivity_fixed_effect.csv", results["fixed_rows"])
    write_csv(output_dir / "sensitivity_f.csv", results["f_rows"])
    write_csv(output_dir / "sensitivity_g.csv", results["g_rows"])
    write_csv(
        output_dir / "sensitivity_particulate_concentration.csv",
        results["particulate_rows"],
    )
    write_csv(output_dir / "baseline_model_summaries.csv", results["baseline_summary_rows"])
    write_csv(
        output_dir / "sensitivity_baseline_models.csv",
        results["baseline_sensitivity_rows"],
    )
    write_csv(output_dir / "factor_inputs.csv", results["factor_inputs"])

    with (output_dir / "analysis_results.json").open("w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)

    readme = f"""# 趋势外推与六因素逐因素蒙特卡洛分析

主模型为带人口 offset 的泊松对数线性率趋势：

`log(mu_t) = alpha + beta × (year - 2016) + log(population_t)`

使用 2016–2022 年加沙登记癌症死亡数及年中人口拟合。因 Pearson 离散度大于 1，主分析将泊松模型的系数协方差乘以 Pearson 离散度，再联合抽样 alpha、beta，得到 2023 年反事实登记口径癌症死亡基线。目标是“登记口径下的期望死亡数”，因此没有另加一层 Poisson 过程噪声。

六个因素逐一模拟，未合并为综合效应。每一轮使用：

`D_i = D_0 × [1 + (3/12) × f_i × g × (E_i - 1)]`

主分析 `g=1`；颗粒物 `E=HR10^(Delta x/10)`，其他因素 `E=HR`。模拟次数 {N_SIM:,}，主随机种子 {SEED}。区间为蒙特卡洛分布第 2.5 和 97.5 百分位。

E（颗粒物）明确列为探索性分析：主浓度增量仅来自2023年10月单月监测，不能直接代表11—12月，第四季度存在月际变化不确定性。C（沟通障碍）的主分析分级为低值Very poor、主值Very poor+Poor、高值Good+Poor+Very poor（排除Excellent和Fair）；旧分级继续保留在f敏感性结果中，并标注为包含Fair的定义敏感性。

运行方式：

`python work/manuscript/trend_revision/run_trend_monte_carlo.py`

核心输出：

- `analysis_results.json`：全部模型、假设与表格的机器可读版本
- `historical_registered_deaths.csv`：历史输入与主模型拟合值
- `rolling_backtest.csv`：扩展窗口一步预测回测
- `main_six_factor_results.csv`：六因素主分析
- `sensitivity_fixed_effect.csv`：固定效应合并值敏感性分析
- `sensitivity_f.csv`、`sensitivity_g.csv`：情景参数敏感性分析
- `sensitivity_particulate_concentration.csv`：颗粒物浓度增量敏感性分析
- `baseline_model_summaries.csv`、`sensitivity_baseline_models.csv`：基线模型结构敏感性分析

解释边界：该分析估计的是按战前登记序列趋势外推的 2023 年反事实登记口径癌症死亡，而非真实癌症死亡总量，也不是 2023 年实际登记数。滚动回测提供五个扩展窗口一步预测折次，仍属于内部时间检验。
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    summary = results["model_summary"]
    print(json.dumps({
        "output_dir": str(output_dir),
        "alpha": summary["coefficients"]["alpha"],
        "beta": summary["coefficients"]["beta_year"],
        "annual_rate_ratio": summary["coefficients"]["annual_rate_ratio"],
        "pearson_phi": summary["pearson_phi"],
        "baseline_point": summary["point_prediction_deaths"],
        "baseline_mc": summary["monte_carlo_baseline_primary"],
        "backtest": summary["backtest"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
