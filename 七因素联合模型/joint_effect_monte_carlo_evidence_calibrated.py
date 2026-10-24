#!/usr/bin/env python3
"""Seven-factor joint-exposure scenario model for Gaza cancer mortality.

This script writes only to a new output directory and reuses the current
single-factor trend/Monte Carlo implementation in read-only mode so that the
baseline and the six existing effect streams are exactly continuous with the
authoritative analysis.  It does not modify the existing single-factor
workbooks, scripts, or manuscript.  Structural assumptions (overlap and
mediation) are reported separately from Monte Carlo parameter uncertainty.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
import math
import random
import shutil
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

import numpy as np


N_SIM = 100_000
SEED = 20_260_921
Z_975 = 1.959963984540054
DURATION_MONTHS = 3.0
Q = DURATION_MONTHS / 12.0

YEARS = np.array([2016, 2017, 2018, 2019, 2020, 2021, 2022], dtype=float)
X = YEARS - 2016.0
DEATHS = np.array([348.0, 474.0, 566.0, 548.0, 539.0, 777.0, 915.0], dtype=float)
POPULATIONS = np.array([
    1_828_614.0,
    1_876_666.0,
    1_932_843.0,
    1_989_970.0,
    2_047_969.0,
    2_106_745.0,
    2_166_269.0,
])
TARGET_YEAR = 2023
X_TARGET = float(TARGET_YEAR - 2016)
POP_TARGET = 2_226_544.0

# Six retained cancer-specific mortality effects from the current analysis.
FACTORS = {
    "A": {
        "factor_zh": "医疗服务可及性障碍",
        "factor_en": "Barriers to health services accessibility",
        "model": "random",
        "hr": 1.12659694615175,
        "lower": 0.938382545820733,
        "upper": 1.35256211310746,
        "i2": 84.1,
        "f_low": 0.18,
        "f_main": 0.20,
        "f_high": 0.22,
        "fixed_hr": 0.944145613660327,
        "fixed_lower": 0.901868410767962,
        "fixed_upper": 0.988404659871586,
        "effect_type": "direct",
        "outcome": "cancer-specific mortality/survival",
    },
    "D": {
        "factor_zh": "诊断延迟",
        "factor_en": "Delayed diagnosis",
        "model": "random",
        "hr": 1.40082399155868,
        "lower": 1.07727003955917,
        "upper": 1.82155614030571,
        "i2": 54.9,
        "f_low": 0.50,
        "f_main": 0.75,
        "f_high": 1.00,
        "fixed_hr": 1.31514774947357,
        "fixed_lower": 1.17326023568769,
        "fixed_upper": 1.47419434353505,
        "effect_type": "direct",
        "outcome": "cancer-specific mortality/survival",
    },
    "H": {
        "factor_zh": "医务人员损失或短缺",
        "factor_en": "Health workforce loss or shortage",
        "model": "random",
        "hr": 1.01302594039352,
        "lower": 0.941311605866301,
        "upper": 1.0902038703387,
        "i2": 73.8,
        "f_low": 0.50,
        "f_main": 0.70,
        "f_high": 0.90,
        "fixed_hr": 1.01333526619584,
        "fixed_lower": 0.98544352878683,
        "fixed_upper": 1.04201644408822,
        "effect_type": "direct",
        "outcome": "cancer-specific mortality/survival",
    },
    "P": {
        "factor_zh": "心理社会压力",
        "factor_en": "Psychosocial stress",
        "model": "random",
        "hr": 1.23650966032884,
        "lower": 1.018684077252,
        "upper": 1.50091296627611,
        "i2": 58.7,
        "f_low": 0.50,
        "f_main": 0.80,
        "f_high": 0.94,
        "fixed_hr": 1.21802482826318,
        "fixed_lower": 1.0958531128707,
        "fixed_upper": 1.35381691655658,
        "effect_type": "direct",
        "outcome": "cancer-specific mortality/survival",
    },
    "E": {
        "factor_zh": "燃烧烟雾、煤尘或颗粒物暴露",
        "factor_en": "Exposure to combustion smoke, coal dust or particulates",
        "model": "random",
        "hr": 1.4270702743758,
        "lower": 1.07526525525956,
        "upper": 1.89397877225693,
        "i2": 98.7,
        "f_low": 1.00,
        "f_main": 1.00,
        "f_high": 1.00,
        "fixed_hr": 1.01289527620331,
        "fixed_lower": 0.996933330590114,
        "fixed_upper": 1.02911278926514,
        "effect_type": "per10",
        "delta_x_low": 0.5,
        "delta_x_main": 4.1,
        "delta_x_high": 7.2,
        "outcome": "cancer-specific mortality/survival",
        "analysis_role_zh": "探索性分析",
        "analysis_note_zh": "主浓度增量仅来自2023年10月单月监测；不能代表11—12月，第四季度外推存在月际变化不确定性。",
    },
    "C": {
        "factor_zh": "患者—医务人员沟通障碍",
        "factor_en": "Patient-provider communication barriers",
        "model": "fixed",
        "hr": 1.3521517680129,
        "lower": 0.978326692568816,
        "upper": 1.86881786792485,
        "i2": 0.0,
        "f_low": 66.0 / 658.0,
        "f_main": 197.0 / 658.0,
        "f_high": 361.0 / 658.0,
        "fixed_hr": 1.3521517680129,
        "fixed_lower": 0.978326692568816,
        "fixed_upper": 1.86881786792485,
        "effect_type": "direct",
        "outcome": "cancer-specific mortality/survival",
        "f_definition_zh": "低值=Very poor；主值=Very poor+Poor；高值=除Excellent和Fair外（Good+Poor+Very poor）",
    },
}

C_LEGACY_F_SCENARIOS = [
    ("C旧定义低值：Poor+Very poor", 197.0 / 658.0),
    ("C旧定义主值：Fair+Poor+Very poor", 395.0 / 658.0),
    ("C旧定义高值：除Excellent外", 559.0 / 658.0),
]

# The original article's treatment-delay effect.  This is an overall-survival
# (all-cause mortality) effect and is therefore an explicitly labelled proxy in
# the cancer-specific joint scenario.
TREATMENT = {
    "code": "T",
    "factor_zh": "治疗延迟或中断",
    "factor_en": "Delayed or interrupted cancer treatment",
    "hr4": 1.085,
    "lower4": 1.051,
    "upper4": 1.120,
    "delay_weeks": 12.0,
    "f_low": 0.50,
    "f_main": 0.75,
    "f_high": 1.00,
    "outcome": "overall survival/all-cause mortality proxy",
}

BINARY_CODES = ("A", "D", "H", "P", "C", "T")
UPSTREAM_CODES = ("A", "H", "C")
PAIR_CODES = ("A", "D", "H", "C")
SHAPLEY_CODES = ("A", "D", "H", "P", "E", "C", "T")

# Evidence-calibrated pairwise associations with treatment delay/interruption.
# Odds ratios are transported to the model's effective-burden margins by
# solving the 2x2 table under fixed f_i and f_T. A "nested" rule is used for A
# because the operational exposure is an actual delayed/denied treatment
# permit; at the main margins this gives P(T|A)=1.
GADE_D_OR = 4.429945054945055
GADE_D_OR_LOW = 2.9064204390127495
GADE_D_OR_HIGH = 6.752090277929007
RAO_D_OR = 1.41
TAMIRAT_C_OR = 2.54
TAMIRAT_C_OR_LOW = 1.92
TAMIRAT_C_OR_HIGH = 3.38
TAMIRAT_C_OR_FACILITY_ADJUSTED = 1.23
RCR_H_OR = 21.04716981132079       # calibrated from fH=.70, fT=.75, P(T|H)=.92
RCR_H_OR_HIGH = 48.05882352941166  # calibrated from P(T|H)=.95

OVERLAP_SCENARIOS = {
    "independent": {
        "label": "独立结构",
        "rules": {code: ("or", 1.0) for code in PAIR_CODES},
        "use": "结构敏感性",
    },
    "evidence_low": {
        "label": "证据低值",
        "rules": {
            "A": ("or", 1.0),
            "D": ("or", GADE_D_OR_LOW),
            "H": ("or", 1.0),
            "C": ("or", TAMIRAT_C_OR_LOW),
        },
        "use": "重叠证据低值敏感性",
    },
    "evidence_primary": {
        "label": "证据校准主值",
        "rules": {
            "A": ("nested", math.inf),
            "D": ("or", GADE_D_OR),
            "H": ("or", RCR_H_OR),
            "C": ("or", TAMIRAT_C_OR),
        },
        "use": "主分析",
    },
    "evidence_high": {
        "label": "证据高值",
        "rules": {
            "A": ("nested", math.inf),
            "D": ("or", GADE_D_OR_HIGH),
            "H": ("or", RCR_H_OR_HIGH),
            "C": ("or", TAMIRAT_C_OR_HIGH),
        },
        "use": "重叠证据高值敏感性",
    },
    "rao_conservative_d": {
        "label": "D-T保守关联（Rao调整OR=1.41）",
        "rules": {
            "A": ("nested", math.inf),
            "D": ("or", RAO_D_OR),
            "H": ("or", RCR_H_OR),
            "C": ("or", TAMIRAT_C_OR),
        },
        "use": "D-T保守旁证敏感性",
    },
    "tamirat_facility_adjusted_c": {
        "label": "C-T保守关联（Tamirat纳入诊断机构OR=1.23）",
        "rules": {
            "A": ("nested", math.inf),
            "D": ("or", GADE_D_OR),
            "H": ("or", RCR_H_OR),
            "C": ("or", TAMIRAT_C_OR_FACILITY_ADJUSTED),
        },
        "use": "C-T保守旁证敏感性",
    },
}


def load_authoritative_single_factor_model(workspace: Path):
    """Load the current six-factor implementation without changing it."""
    source = workspace / "work" / "manuscript" / "trend_revision" / "run_trend_monte_carlo.py"
    spec = importlib.util.spec_from_file_location("authoritative_six_factor_model", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load authoritative model: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.SEED != SEED or module.N_SIM != N_SIM:
        raise RuntimeError("Authoritative seed or draw count differs from the joint model")
    return module, source


def fit_poisson_offset() -> Dict[str, object]:
    beta = np.array([math.log(DEATHS.sum() / POPULATIONS.sum()), 0.0])
    design = np.column_stack([np.ones_like(X), X])
    for _ in range(100):
        mu = POPULATIONS * np.exp(design @ beta)
        score = design.T @ (DEATHS - mu)
        info = design.T @ (design * mu[:, None])
        step = np.linalg.solve(info, score)
        beta_new = beta + step
        if np.max(np.abs(beta_new - beta)) < 1e-13:
            beta = beta_new
            break
        beta = beta_new
    mu = POPULATIONS * np.exp(design @ beta)
    info = design.T @ (design * mu[:, None])
    covariance_poisson = np.linalg.inv(info)
    residual_df = len(DEATHS) - 2
    pearson_chi2 = float(np.sum((DEATHS - mu) ** 2 / mu))
    phi = pearson_chi2 / residual_df
    return {
        "coefficients": beta,
        "fitted": mu,
        "covariance_poisson": covariance_poisson,
        "covariance_quasi": covariance_poisson * phi,
        "pearson_chi2": pearson_chi2,
        "pearson_phi": phi,
        "residual_df": residual_df,
    }


def fit_ols(y: np.ndarray) -> Dict[str, np.ndarray | float]:
    design = np.column_stack([np.ones_like(X), X])
    coefficients = np.linalg.solve(design.T @ design, design.T @ y)
    residuals = y - design @ coefficients
    residual_df = len(y) - 2
    sigma2 = float(residuals @ residuals / residual_df)
    covariance = sigma2 * np.linalg.inv(design.T @ design)
    return {"coefficients": coefficients, "covariance": covariance}


def percentile_summary(values: np.ndarray) -> Dict[str, float]:
    q = np.quantile(values, [0.025, 0.5, 0.975])
    return {
        "lower_2_5": float(q[0]),
        "median": float(q[1]),
        "upper_97_5": float(q[2]),
    }


def log_hr_params(point: float, lower: float, upper: float) -> tuple[float, float]:
    return math.log(point), (math.log(upper) - math.log(lower)) / (2.0 * Z_975)


def ratio_draws(z: np.ndarray, point: float, lower: float, upper: float) -> np.ndarray:
    mu, se = log_hr_params(point, lower, upper)
    return np.exp(mu + se * z)


def draw_bivariate_normal_legacy(
    mean: Sequence[float], covariance: Sequence[Sequence[float]], n: int, rng: random.Random
) -> tuple[np.ndarray, np.ndarray]:
    """Match the exact coefficient-draw sequence used by the prior six-factor analysis."""
    l00 = math.sqrt(float(covariance[0][0]))
    l10 = float(covariance[1][0]) / l00
    remainder = float(covariance[1][1]) - l10 * l10
    if remainder < 0.0 and abs(remainder) < 1e-18:
        remainder = 0.0
    l11 = math.sqrt(remainder)
    first = np.empty(n, dtype=float)
    second = np.empty(n, dtype=float)
    for index in range(n):
        z0 = rng.gauss(0.0, 1.0)
        z1 = rng.gauss(0.0, 1.0)
        first[index] = float(mean[0]) + l00 * z0
        second[index] = float(mean[1]) + l10 * z0 + l11 * z1
    return first, second


def draw_log_ratio_legacy(
    point: float, lower: float, upper: float, rng: random.Random
) -> np.ndarray:
    """Draw log-ratios with the same random.Random.gauss calls as the prior model."""
    mu, se = log_hr_params(point, lower, upper)
    return np.fromiter(
        (rng.gauss(mu, se) for _ in range(N_SIM)), dtype=float, count=N_SIM
    )


def f_values(level: str) -> Dict[str, float]:
    if level not in {"low", "main", "high"}:
        raise ValueError(level)
    result = {code: float(values[f"f_{level}"]) for code, values in FACTORS.items() if code != "E"}
    result["T"] = float(TREATMENT[f"f_{level}"])
    return result


def joint_from_odds_ratio(fi: float, ft: float, odds_ratio: float) -> float:
    """Return the legal 2x2 intersection for fixed margins and an odds ratio."""
    lower = max(0.0, fi + ft - 1.0)
    upper = min(fi, ft)
    if fi <= 0.0 or ft <= 0.0:
        return 0.0
    if fi >= 1.0:
        return ft
    if ft >= 1.0:
        return fi
    if not math.isfinite(odds_ratio):
        return upper
    if odds_ratio <= 0.0:
        return lower
    if abs(odds_ratio - 1.0) < 1e-14:
        return fi * ft
    lo, hi = lower, upper
    for _ in range(200):
        joint = (lo + hi) / 2.0
        denominator = (fi - joint) * (ft - joint)
        implied = math.inf if denominator <= 0.0 else (
            joint * (1.0 - fi - ft + joint) / denominator
        )
        if implied < odds_ratio:
            lo = joint
        else:
            hi = joint
    return (lo + hi) / 2.0


def overlap_parameters(
    f: Mapping[str, float], overlap_scenario: str
) -> Dict[str, Dict[str, float | str]]:
    """Maximum-entropy star distribution using evidence-calibrated pair rules.

    Pairwise intersections are determined from fixed margins and source odds
    ratios, except A in the primary/high scenarios, which is nested within T.
    P remains independent of T. Conditional on T, A/D/H/P/C are independent.
    """
    if overlap_scenario not in OVERLAP_SCENARIOS:
        raise ValueError(overlap_scenario)
    ft = float(f["T"])
    rules = OVERLAP_SCENARIOS[overlap_scenario]["rules"]
    params: Dict[str, Dict[str, float | str]] = {}
    for code in ("A", "D", "H", "P", "C"):
        fi = float(f[code])
        if code == "P":
            rule, parameter = "independent", 1.0
            joint = fi * ft
        else:
            rule, parameter = rules[code]
            if rule == "nested":
                joint = min(fi, ft)
            elif rule == "or":
                joint = joint_from_odds_ratio(fi, ft, float(parameter))
            else:
                raise ValueError((overlap_scenario, code, rule))
        p1 = fi if ft == 0.0 else joint / ft
        p0 = fi if ft == 1.0 else (fi - joint) / (1.0 - ft)
        params[code] = {
            "marginal": fi,
            "joint_with_T": joint,
            "p_given_T1": p1,
            "p_given_T0": p0,
            "p_T_given_i": joint / fi if fi > 0.0 else math.nan,
            "rule": rule,
            "association_parameter": (
                float(parameter) if math.isfinite(float(parameter)) else None
            ),
        }
    return params


def pattern_rows(f: Mapping[str, float], overlap_scenario: str) -> list[Dict[str, float | int | str]]:
    cond = overlap_parameters(f, overlap_scenario)
    ft = float(f["T"])
    rows: list[Dict[str, float | int | str]] = []
    for state in itertools.product((0, 1), repeat=len(BINARY_CODES)):
        values = dict(zip(BINARY_CODES, state))
        t = values["T"]
        probability = ft if t else 1.0 - ft
        for code in ("A", "D", "H", "P", "C"):
            p = cond[code]["p_given_T1" if t else "p_given_T0"]
            probability *= p if values[code] else 1.0 - p
        rows.append({
            "pattern": "".join(str(values[c]) for c in BINARY_CODES),
            **{c: values[c] for c in BINARY_CODES},
            "probability": float(probability),
        })
    return rows


def build_overlap_constraint_rows(f: Mapping[str, float]) -> list[Dict[str, object]]:
    rows: list[Dict[str, object]] = []
    for scenario_key in (
        "independent", "evidence_low", "evidence_primary",
        "evidence_high", "rao_conservative_d", "tamirat_facility_adjusted_c",
    ):
        scenario = OVERLAP_SCENARIOS[scenario_key]
        params = overlap_parameters(f, scenario_key)
        ft = float(f["T"])
        for code in PAIR_CODES:
            fi = float(f[code])
            joint = params[code]["joint_with_T"]
            rows.append({
                "overlap_scenario_key": scenario_key,
                "overlap_scenario": scenario["label"],
                "factor_pair": f"{code}-T",
                "f_i": fi,
                "f_T": ft,
                "frechet_lower": max(0.0, fi + ft - 1.0),
                "frechet_upper": min(fi, ft),
                "independent_intersection": fi * ft,
                "target_intersection": joint,
                "p_T_given_i": joint / fi if fi > 0.0 else math.nan,
                "p_i_given_T": params[code]["p_given_T1"],
                "p_i_given_not_T": params[code]["p_given_T0"],
                "rule": params[code]["rule"],
                "association_parameter": params[code]["association_parameter"],
                "source_type": "证据校准/定义性嵌套/结构敏感性，详见证据记录",
                "use": scenario["use"],
            })
    return rows


def expected_wartime_rr(
    effects: Mapping[str, np.ndarray],
    f: Mapping[str, float],
    overlap_scenario: str,
    structure: str,
) -> np.ndarray:
    """Integrate exactly over all 64 binary exposure patterns."""
    cond = overlap_parameters(f, overlap_scenario)
    ft = float(f["T"])
    re = effects["E"]

    if structure == "additive":
        result = 1.0 + (re - 1.0)
        for code in ("A", "D", "H", "P", "C", "T"):
            result = result + float(f[code]) * (effects[code] - 1.0)
        return result

    residual_by_structure = {
        "evidence_calibrated": (0.0, 0.5),
        "diagnosis_residual_0": (0.0, 0.0),
        "diagnosis_residual_1": (0.0, 1.0),
        "full_product": (1.0, 1.0),
    }
    if structure not in residual_by_structure:
        raise ValueError(structure)
    residual_upstream, residual_diagnosis = residual_by_structure[structure]

    # T=0: upstream factors retain their observed marginal effects.
    rr0 = re.copy()
    for code in ("A", "D", "H", "P", "C"):
        p0 = cond[code]["p_given_T0"]
        rr0 *= 1.0 + p0 * (effects[code] - 1.0)

    # T=1: A/H/C are attenuated because T is their downstream pathway.
    rr1 = re * effects["T"]
    for code in ("A", "D", "H", "P", "C"):
        p1 = cond[code]["p_given_T1"]
        if code in UPSTREAM_CODES:
            exponent = residual_upstream
        elif code == "D":
            exponent = residual_diagnosis
        else:
            exponent = 1.0
        adjusted = np.power(effects[code], exponent)
        rr1 *= 1.0 + p1 * (adjusted - 1.0)

    return (1.0 - ft) * rr0 + ft * rr1


def expected_wartime_rr_fixed_distribution(
    effects: Mapping[str, np.ndarray],
    f: Mapping[str, float],
    overlap_scenario: str,
    structure: str,
    active_codes: Iterable[str],
) -> np.ndarray:
    """Evaluate a coalition while holding the primary 64-cell distribution fixed."""
    active = set(active_codes)
    cond = overlap_parameters(f, overlap_scenario)
    ft = float(f["T"])
    re = effects["E"] if "E" in active else np.ones(N_SIM, dtype=float)

    if structure == "additive":
        result = re.copy()
        for code in BINARY_CODES:
            if code in active:
                result = result + float(f[code]) * (effects[code] - 1.0)
        return result

    residual_by_structure = {
        "evidence_calibrated": (0.0, 0.5),
        "diagnosis_residual_0": (0.0, 0.0),
        "diagnosis_residual_1": (0.0, 1.0),
        "full_product": (1.0, 1.0),
    }
    if structure not in residual_by_structure:
        raise ValueError(structure)
    residual_upstream, residual_diagnosis = residual_by_structure[structure]

    conditional_rr = []
    for latent_t in (0, 1):
        active_t = latent_t if "T" in active else 0
        rr = re.copy()
        if active_t:
            rr *= effects["T"]
        for code in ("A", "D", "H", "P", "C"):
            if code not in active:
                continue
            probability = cond[code]["p_given_T1" if latent_t else "p_given_T0"]
            if active_t and code in UPSTREAM_CODES:
                exponent = residual_upstream
            elif active_t and code == "D":
                exponent = residual_diagnosis
            else:
                exponent = 1.0
            adjusted = np.power(effects[code], exponent)
            rr *= 1.0 + probability * (adjusted - 1.0)
        conditional_rr.append(rr)
    return (1.0 - ft) * conditional_rr[0] + ft * conditional_rr[1]


def calculate_scenario(
    name: str,
    category: str,
    baseline: np.ndarray,
    effects: Mapping[str, np.ndarray],
    f: Mapping[str, float],
    overlap_scenario: str,
    structure: str,
    g: float = 1.0,
    notes: str = "",
    fixed_distribution_active: Iterable[str] | None = None,
) -> Dict[str, object]:
    if fixed_distribution_active is None:
        wartime_rr = expected_wartime_rr(effects, f, overlap_scenario, structure)
    else:
        wartime_rr = expected_wartime_rr_fixed_distribution(
            effects, f, overlap_scenario, structure, fixed_distribution_active
        )
    annual_multiplier = 1.0 + Q * g * (wartime_rr - 1.0)
    joint_deaths = baseline * annual_multiplier
    additional = joint_deaths - baseline
    percent_change = 100.0 * (annual_multiplier - 1.0)

    treatment_rr = 1.0 + float(f["T"]) * (effects["T"] - 1.0)
    treatment_deaths = baseline * (1.0 + Q * g * (treatment_rr - 1.0))
    treatment_additional = treatment_deaths - baseline
    treatment_percent_change = 100.0 * Q * g * (treatment_rr - 1.0)
    beyond_treatment = joint_deaths - treatment_deaths

    row: Dict[str, object] = {
        "category": category,
        "scenario": name,
        "structure": structure,
        "overlap_scenario_key": overlap_scenario,
        "overlap_scenario": OVERLAP_SCENARIOS[overlap_scenario]["label"],
        "g": g,
        "f_A": f["A"],
        "f_D": f["D"],
        "f_H": f["H"],
        "f_P": f["P"],
        "f_C": f["C"],
        "f_T": f["T"],
        "notes": notes,
        "fixed_distribution_active": (
            ",".join(fixed_distribution_active)
            if fixed_distribution_active is not None
            else ""
        ),
    }
    for prefix, values in (
        ("wartime_rr", wartime_rr),
        ("annual_multiplier", annual_multiplier),
        ("joint_deaths", joint_deaths),
        ("additional_deaths", additional),
        ("percent_change", percent_change),
        ("treatment_only_deaths", treatment_deaths),
        ("treatment_only_additional_deaths", treatment_additional),
        ("treatment_only_percent_change", treatment_percent_change),
        ("beyond_treatment_deaths", beyond_treatment),
    ):
        for key, value in percentile_summary(values).items():
            row[f"{prefix}_{key}"] = value
    row["p_additional_positive_percent"] = 100.0 * float(np.mean(additional > 0.0))
    row["p_beyond_treatment_positive_percent"] = 100.0 * float(np.mean(beyond_treatment > 0.0))
    row["p_treatment_only_additional_positive_percent"] = (
        100.0 * float(np.mean(treatment_additional > 0.0))
    )
    row["min_wartime_rr"] = float(np.min(wartime_rr))
    return row


def exact_shapley_decomposition(
    baseline: np.ndarray,
    effects: Mapping[str, np.ndarray],
    f: Mapping[str, float],
    overlap_scenario: str,
    structure: str,
    g: float = 1.0,
) -> tuple[list[Dict[str, object]], float, np.ndarray]:
    """Allocate the joint increment exactly over all 2^7 coalitions.

    The primary 64-cell exposure distribution remains fixed for every
    coalition.  Removing a factor only masks its risk indicator/effect; an
    absent T also stops suppressing upstream A/H/C effects.  Thus the
    allocation does not redistribute exposure probability between coalitions.
    The result is a model decomposition, not an estimate of independent causal
    deaths.
    """
    n_factors = len(SHAPLEY_CODES)
    full_mask = (1 << n_factors) - 1
    values: Dict[int, np.ndarray] = {}

    for mask in range(full_mask + 1):
        active_codes = tuple(
            code
            for index, code in enumerate(SHAPLEY_CODES)
            if mask & (1 << index)
        )
        wartime_rr = expected_wartime_rr_fixed_distribution(
            effects, f, overlap_scenario, structure, active_codes
        )
        values[mask] = baseline * Q * g * (wartime_rr - 1.0)

    factorial = math.factorial
    denominator = factorial(n_factors)
    contributions: Dict[str, np.ndarray] = {}
    for index, code in enumerate(SHAPLEY_CODES):
        bit = 1 << index
        phi = np.zeros(N_SIM, dtype=float)
        for mask in range(full_mask + 1):
            if mask & bit:
                continue
            size = mask.bit_count()
            weight = factorial(size) * factorial(n_factors - size - 1) / denominator
            phi += weight * (values[mask | bit] - values[mask])
        contributions[code] = phi

    total = values[full_mask]
    allocated = np.sum(np.stack([contributions[c] for c in SHAPLEY_CODES]), axis=0)
    additivity_error = float(np.max(np.abs(allocated - total)))
    rows: list[Dict[str, object]] = []
    for code in SHAPLEY_CODES:
        factor = TREATMENT if code == "T" else FACTORS[code]
        contribution = contributions[code]
        share = np.divide(
            contribution * 100.0,
            total,
            out=np.full_like(contribution, np.nan),
            where=total != 0.0,
        )
        contribution_summary = percentile_summary(contribution)
        share_summary = percentile_summary(share[np.isfinite(share)])
        rows.append({
            "code": code,
            "factor_zh": factor["factor_zh"],
            "factor_en": factor["factor_en"],
            "outcome": factor["outcome"],
            "contribution_lower_2_5": contribution_summary["lower_2_5"],
            "contribution_median": contribution_summary["median"],
            "contribution_upper_97_5": contribution_summary["upper_97_5"],
            "share_percent_lower_2_5": share_summary["lower_2_5"],
            "share_percent_median": share_summary["median"],
            "share_percent_upper_97_5": share_summary["upper_97_5"],
            "p_contribution_positive_percent": 100.0 * float(np.mean(contribution > 0.0)),
            "interpretation": "联合模型增量的Shapley分配；不是独立致死人数",
        })
    return rows, additivity_error, total


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_evidence_records(output_dir: Path, f: Mapping[str, float]) -> Dict[str, list[Dict[str, object]]]:
    """Write the evidence trail used to set overlap and D-residual scenarios."""
    evidence_dir = output_dir / "evidence_records"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    primary = overlap_parameters(f, "evidence_primary")
    low = overlap_parameters(f, "evidence_low")
    high = overlap_parameters(f, "evidence_high")
    rao = overlap_parameters(f, "rao_conservative_d")
    c_facility = overlap_parameters(f, "tamirat_facility_adjusted_c")

    conditional_rows = [
        {
            "factor_pair": "A-T", "citation": "Bouquet et al., PLOS ONE, 2021",
            "evidence_class": "直接资料＋定义性嵌套", "population_n": 3816,
            "source_observation": "需赴境外化疗/放疗者中，首次许可延迟或拒绝655例；论文未报告患者最终是否实际接受治疗",
            "raw_statistic": "655/3816=0.1716（A发生比例；不是P(T|A)，也不是治疗实施比例）",
            "association_measure": "结构嵌套假设", "association_value": "P(T|A)=1不是论文观察值",
            "model_f_i": f["A"], "model_f_T": f["T"],
            "model_P_T_given_i": primary["A"]["p_T_given_i"],
            "model_use": "主分析纯结构假设：A嵌套于T；A与T并存时A残余效应=0",
            "limitation": "655/3816不能推出P(T|A)=1；论文无实际治疗实施信息。若A改定义为仅需许可，应重新估计fA和条件概率",
            "url": "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0251058",
        },
        {
            "factor_pair": "A-T", "citation": "Massad et al., BMJ Global Health, 2026",
            "evidence_class": "外部直接比例旁证", "population_n": 271,
            "source_observation": "加沙儿童肿瘤患者67例许可延迟>1月；含1例拒绝为68例",
            "raw_statistic": "67/271=0.2472；68/271=0.2509",
            "association_measure": "发生比例", "association_value": 0.2509,
            "model_f_i": f["A"], "model_f_T": f["T"], "model_P_T_given_i": "不直接代入",
            "model_use": "用于核对A的量级与定义，不替代嵌套规则",
            "limitation": "儿童肿瘤、特定许可制度；不是当前有效负担边际下的条件概率",
            "url": "https://gh.bmj.com/content/11/1/e015493",
        },
        {
            "factor_pair": "D-T", "citation": "Gade et al., JCO Global Oncology, 2026",
            "evidence_class": "直接患者级2×2关联（主证据）", "population_n": 418,
            "source_observation": "D&T=129，D-only=91，non-D&T=48，neither=150",
            "raw_statistic": "P(T|D)=129/220=0.5864；原始边际与本模型边际不同",
            "association_measure": "OR", "association_value": GADE_D_OR,
            "association_lower_95": GADE_D_OR_LOW, "association_upper_95": GADE_D_OR_HIGH,
            "model_f_i": f["D"], "model_f_T": f["T"],
            "model_P_T_given_i": primary["D"]["p_T_given_i"],
            "model_P_low": low["D"]["p_T_given_i"], "model_P_high": high["D"]["p_T_given_i"],
            "model_use": "主分析将OR运输到fD=fT=0.75；CI界用于重叠低/高情景",
            "limitation": "印度宫颈癌队列；运输OR假设关联强度可迁移，绝对条件概率不可直接搬用",
            "url": "https://ascopubs.org/doi/10.1200/GO-25-00765",
        },
        {
            "factor_pair": "D-T", "citation": "Rao et al., JNCCN, 2021",
            "evidence_class": "调整后关联旁证", "population_n": ">900",
            "source_observation": "诊断延迟与治疗延迟关联的调整OR",
            "raw_statistic": "OR=1.41（95%CI 0.82–2.44）",
            "association_measure": "adjusted OR", "association_value": RAO_D_OR,
            "association_lower_95": 0.82, "association_upper_95": 2.44,
            "model_f_i": f["D"], "model_f_T": f["T"],
            "model_P_T_given_i": rao["D"]["p_T_given_i"],
            "model_use": "单列D-T保守关联敏感性，不作为主值",
            "limitation": "肝细胞癌队列，且关联较弱、置信区间跨1",
            "url": "https://jnccn.org/downloadpdf/journals/jnccn/19/9/article-p1063.pdf",
        },
        {
            "factor_pair": "H-T", "citation": "Royal College of Radiologists workforce census, 2023",
            "evidence_class": "机构级权威代理", "population_n": "英国全部60个临床肿瘤中心",
            "source_observation": "92%中心报告因人员短缺至少出现过放疗延迟；95%中心至少出现过SACT延迟",
            "raw_statistic": "RT=0.92；SACT=0.95",
            "association_measure": "P(T|H)机构级代理", "association_value": 0.92,
            "model_f_i": f["H"], "model_f_T": f["T"],
            "model_P_T_given_i": primary["H"]["p_T_given_i"],
            "model_P_high": high["H"]["p_T_given_i"],
            "model_use": "0.92校准为OR后用于主分析；0.95用于证据高值",
            "limitation": "这是机构层‘至少出现延迟’比例，不是患者层P(T|H)；英国常规医疗环境而非战争环境",
            "url": "https://www.rcr.ac.uk/media/j5jmhpju/rcr-census-clinical-oncology-workforce-census-2023.pdf",
        },
        {
            "factor_pair": "C-T", "citation": "Tamirat et al., Cancer Causes & Control, 2025",
            "evidence_class": "调整后患者级关联（主代理）", "population_n": 13625,
            "source_observation": "Model 1：非英语CALD与澳大利亚出生患者相比，确定性治疗延迟>90天；未纳入诊断机构",
            "raw_statistic": "Model 1 adjusted OR=2.54（95%CI 1.92–3.38）",
            "association_measure": "adjusted OR", "association_value": TAMIRAT_C_OR,
            "association_lower_95": TAMIRAT_C_OR_LOW, "association_upper_95": TAMIRAT_C_OR_HIGH,
            "model_f_i": f["C"], "model_f_T": f["T"],
            "model_P_T_given_i": primary["C"]["p_T_given_i"],
            "model_P_low": low["C"]["p_T_given_i"], "model_P_high": high["C"]["p_T_given_i"],
            "model_use": "总关联OR运输到当前fC与fT作为主代理；CI界用于证据低/高情景",
            "limitation": "暴露是非英语CALD，并非直接测量患者—医务人员沟通障碍；未纳入诊断机构，澳大利亚前列腺癌队列",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12630315/",
        },
        {
            "factor_pair": "C-T", "citation": "Tamirat et al., Cancer Causes & Control, 2025, Model 2",
            "evidence_class": "纳入诊断机构后的保守关联", "population_n": 13625,
            "source_observation": "Model 2加入诊断机构后，非英语CALD与治疗延迟>90天的关联明显衰减；作者中介分析认为更多在公立机构确诊可完全中介该关联",
            "raw_statistic": "adjusted OR=1.23（95%CI 0.92–1.65）",
            "association_measure": "facility-adjusted OR", "association_value": TAMIRAT_C_OR_FACILITY_ADJUSTED,
            "association_lower_95": 0.92, "association_upper_95": 1.65,
            "model_f_i": f["C"], "model_f_T": f["T"],
            "model_P_T_given_i": c_facility["C"]["p_T_given_i"],
            "model_use": "单列C-T保守关联敏感性；不替代总关联主代理",
            "limitation": "诊断机构可能是中介而非应控制的混杂因素；暴露仍是CALD代理而非直接沟通障碍",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12630315/",
        },
        {
            "factor_pair": "C-T", "citation": "Han et al., Cancer Treatment and Research Communications, 2026",
            "evidence_class": "患者级比例旁证", "population_n": 138,
            "source_observation": "非英语主要语言组32.4%发生沟通相关治疗延迟，英语组19.4%",
            "raw_statistic": "32.4% vs 19.4%",
            "association_measure": "未调整比例", "association_value": "近似OR约1.99",
            "model_f_i": f["C"], "model_f_T": f["T"], "model_P_T_given_i": "未作为主值",
            "model_use": "方向和量级旁证",
            "limitation": "样本小，百分比为摘要报告，定义较窄",
            "url": "https://www.sciencedirect.com/science/article/pii/S246829422600362X",
        },
        {
            "factor_pair": "C-T", "citation": "本项目加沙Mapping资料",
            "evidence_class": "本地情境描述性证据", "population_n": 90,
            "source_observation": "90条记录中32条提及沟通障碍",
            "raw_statistic": "32/90=0.3556",
            "association_measure": "障碍比例，无T交叉", "association_value": 0.3556,
            "model_f_i": f["C"], "model_f_T": f["T"], "model_P_T_given_i": "不能估计",
            "model_use": "仅支持因素存在，不用于C-T重叠定量",
            "limitation": "没有与治疗延迟/中断交叉表",
            "url": "",
        },
    ]

    residual_rows = [
        {
            "evidence": "现有D癌症特异性Meta分析", "evidence_class": "直接效应证据的调整变量审计",
            "finding": "4项研究均未明确控制治疗延迟/中断T",
            "implication": "合并HR 1.4008不能解释为控制T后的D直接效应",
            "supports_kappa": "不能定量选择0、0.5或1",
            "url_or_path": "D:/癌症pdf/Health Services and Systems/Delayed diagnosis/HR_Meta_Analysis_Cancer_Specific_2026-10-17/included_HR_cancer_specific.csv",
        },
        {
            "evidence": "Zhao et al., Cancer Medicine, 2026", "evidence_class": "独立路径旁证",
            "finding": "N=450；治疗延迟>1月仅21例；诊断延迟>5月与OS/DFS相关，但CSS单变量HR 1.41且不显著",
            "implication": "D可能在几乎没有T时仍通过分期等路径作用，但未给出D与T并存时的控制直接效应",
            "supports_kappa": "支持kappa>0的可能性，不支持具体百分比",
            "url_or_path": "https://pmc.ncbi.nlm.nih.gov/articles/PMC13140271/",
        },
        {
            "evidence": "Gade et al., JCO Global Oncology, 2026", "evidence_class": "D-only存在性证据",
            "finding": "220例诊断延迟中91例没有后续治疗延迟/中断",
            "implication": "D与T并非同一事件，但不能据此估计并存时D的残余死亡效应",
            "supports_kappa": "支持结构上保留D独立路径",
            "url_or_path": "https://ascopubs.org/doi/10.1200/GO-25-00765",
        },
        {
            "evidence": "Lung Cancer Under Siege in Spain, 2025", "evidence_class": "同一Cox模型同时纳入D和T",
            "finding": "全因死亡模型中，诊断间隔≥30天HR 0.78（95%CI 0.54–1.14），治疗间隔≥42天HR 0.90（95%CI 0.65–1.24）",
            "implication": "在同一模型控制两种间隔后未观察到显著独立效应；可支持κ=0作为合理下界，但不能证明D效应必为0",
            "supports_kappa": "支持κ=0下界；结局为全因死亡且CI较宽，不足以确定主值",
            "url_or_path": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12384519/",
        },
        {
            "evidence": "Hollenbeck et al., Cancer, 2010", "evidence_class": "癌症特异性独立路径旁证",
            "finding": "膀胱癌诊断延迟9–12月对比<3月：CSS HR 1.34（95%CI 1.20–1.50）；进一步调整分期/分级后HR 1.29（1.14–1.45），但未控制T",
            "implication": "分期/分级调整后关联仍存在，提示D可能有未被分期完全解释的路径；因未调T，不能当作D在T后的控制直接效应",
            "supports_kappa": "支持κ>0的可能性，不支持具体比例",
            "url_or_path": "https://acsjournals.onlinelibrary.wiley.com/doi/full/10.1002/cncr.25310",
        },
        {
            "evidence": "系统检索结论", "evidence_class": "证据缺口",
            "finding": "未找到直接报告D与T并存时控制直接效应或中介比例的癌症研究",
            "implication": "不能把0%、50%或100%称为经验估计",
            "supports_kappa": "主分析kappa=0.5为对称中心预设；kappa=0与1为结构敏感性",
            "url_or_path": "见search_log.csv",
        },
    ]

    parameter_rows = [
        {"parameter": "P(T|A)", "primary": primary["A"]["p_T_given_i"], "low": f["T"], "high": 1.0, "basis": "A为实际许可延迟/拒绝事件，主值定义性嵌套；独立结构为低敏感性"},
        {"parameter": "D-T OR", "primary": GADE_D_OR, "low": GADE_D_OR_LOW, "high": GADE_D_OR_HIGH, "basis": "Gade患者级2×2；OR运输到当前有效边际"},
        {"parameter": "P(T|D)@current margins", "primary": primary["D"]["p_T_given_i"], "low": low["D"]["p_T_given_i"], "high": high["D"]["p_T_given_i"], "basis": "由D-T OR和fD=fT=0.75求合法2×2交集"},
        {"parameter": "P(T|H)", "primary": primary["H"]["p_T_given_i"], "low": f["T"], "high": high["H"]["p_T_given_i"], "basis": "RCR中心级RT 92%主值、SACT 95%高值；低值独立"},
        {"parameter": "C-T OR", "primary": TAMIRAT_C_OR, "low": TAMIRAT_C_OR_LOW, "high": TAMIRAT_C_OR_HIGH, "basis": "Tamirat调整OR及95%CI；OR运输到当前有效边际"},
        {"parameter": "P(T|C)@current margins", "primary": primary["C"]["p_T_given_i"], "low": low["C"]["p_T_given_i"], "high": high["C"]["p_T_given_i"], "basis": f"由C-T OR和fC={f['C']:.6f}、fT={f['T']:.2f}求合法2×2交集；C主值为Very poor+Poor"},
        {"parameter": "P(T|C) facility-adjusted sensitivity", "primary": c_facility["C"]["p_T_given_i"], "low": "", "high": "", "basis": "Tamirat Model 2纳入诊断机构OR=1.23；作为C-T保守关联敏感性"},
        {"parameter": "P与T关联", "primary": "独立", "low": "独立", "high": "独立", "basis": "用户指定暂按独立处理"},
        {"parameter": "D residual kappa", "primary": 0.5, "low": 0.0, "high": 1.0, "basis": "无直接中介比例；对称中心预设并进行两端结构敏感性"},
        {"parameter": "A/H/C residual when T=1", "primary": 0.0, "low": 0.0, "high": 0.0, "basis": "用户指定完全由T路径覆盖；文章需明确为模型假设"},
    ]

    search_rows = [
        {"search_topic": "A-T条件关联", "sources_checked": "PLOS ONE Gaza permit cohort；BMJ Global Health pediatric Gaza cohort", "usable_record": "Bouquet 655/3816；Massad 67/271或68/271；均无可直接代入的P(T|A)", "decision": "P(T|A)=1为纯结构嵌套假设；655/3816只用于A量级旁证"},
        {"search_topic": "D-T条件关联", "sources_checked": "Gade JCO Global Oncology；Rao JNCCN", "usable_record": "Gade完整2×2；Rao调整OR1.41", "decision": "Gade OR4.4299为主；CI为低/高；Rao作保守敏感性"},
        {"search_topic": "H-T条件关联", "sources_checked": "RCR 2023 clinical oncology workforce census", "usable_record": "60/60中心；92%至少出现RT延迟，95%至少出现SACT延迟", "decision": "92%主、95%高、独立低；明确为机构层代理而非患者条件概率"},
        {"search_topic": "C-T条件关联", "sources_checked": "Tamirat registry cohort；Han cohort；Gaza Mapping", "usable_record": "Tamirat Model1 aOR2.54；Model2纳入诊断机构aOR1.23；Han 32.4% vs19.4%；Mapping 32/90无交叉", "decision": "2.54作总关联主代理；1.23单列保守敏感性；暴露是非英语CALD而非直接沟通测量"},
        {"search_topic": "D在T后残余效应", "sources_checked": "4项D Meta原始调整变量；Zhao；Gade；Spain肺癌同一Cox模型；Hollenbeck膀胱癌CSS；中介/控制直接效应检索", "usable_record": "Spain模型支持κ=0下界；Hollenbeck支持κ>0可能性；仍无直接中介百分比", "decision": "kappa=0.5仅为中心预设；0和1必须报告"},
    ]

    write_csv(evidence_dir / "conditional_overlap_evidence.csv", conditional_rows)
    write_csv(evidence_dir / "diagnostic_residual_evidence.csv", residual_rows)
    write_csv(evidence_dir / "search_log.csv", search_rows)
    write_csv(evidence_dir / "parameter_decisions.csv", parameter_rows)

    readme = f"""# 条件重叠与诊断延迟残余效应证据记录

本目录记录七因素联合模型中 `P(T|A)`、`P(T|D)`、`P(T|H)`、`P(T|C)` 与诊断延迟残余效应的来源、换算和模型决策。直接患者资料、机构级代理、模型校准与无数据预设在表中分开标注。

## 换算规则

对可获得比值比的D和C，先固定当前模型有效边际 `f_i` 与 `f_T`，再在Fréchet合法区间内求解交集 `J`：

`OR = J(1-f_i-f_T+J) / [(f_i-J)(f_T-J)]`，随后 `P(T|i)=J/f_i`。

这样保留来源研究的关联强度，同时避免把不同人群的原始绝对概率直接搬到当前有效负担边际。A的 `P(T|A)=1` 是结构嵌套假设；Bouquet的655/3816仅为许可延迟/拒绝发生比例，论文没有实际治疗实施信息，不能据此估计 `P(T|A)`。H的92%是机构层“至少出现过放疗延迟”的比例，不是患者层条件概率；模型先在主边际校准为OR，再用于其他f情景。P暂按独立。

主边际下的模型值为：`P(T|A)={float(primary['A']['p_T_given_i']):.6f}`、`P(T|D)={float(primary['D']['p_T_given_i']):.6f}`、`P(T|H)={float(primary['H']['p_T_given_i']):.6f}`、`P(T|C)={float(primary['C']['p_T_given_i']):.6f}`。

## 可直接写入文章“方法”的表述

联合暴露分布采用以治疗延迟或中断（T）为中心的最大熵星形模型构建。在给定各因素有效暴露份额的条件下，医疗服务可及性障碍（A）假定嵌套于T，该关系为结构假设而非Bouquet研究的直接观测结果；诊断延迟（D）与T的关联依据患者级2×2资料所得OR进行校准；医务人员损失或短缺（H）与T的关联以英国皇家放射科医师学会全部60个临床肿瘤中心中92%的中心报告至少出现过放疗延迟作为机构级代理；患者—医务人员沟通障碍（C）与T的主关联采用Tamirat研究中非英语文化和语言多样性暴露的Model 1调整OR 2.54作为总关联代理，并以纳入诊断机构后的Model 2调整OR 1.23进行保守敏感性分析；心理社会压力（P）暂按与T独立处理。对D和C，通过固定模型边际并求解2×2表交集，将来源OR转换为合法的条件概率。效应组合时，假定A、H和C与T并存时其死亡效应被T路径完全覆盖；D与T并存时，主分析将D的对数HR乘以κ=0.5，即使用HR_D^0.5，并分别令κ=0与κ=1进行结构敏感性分析。颗粒物与P的效应按既定模型保留。

## 可直接写入文章“局限性”的表述

联合暴露参数并非全部来自同一战争人群的个体级交叉数据。A的嵌套关系是纯结构假设，Bouquet研究的655/3816不是 `P(T|A)` 且未报告实际治疗实施；H使用机构层“至少出现延迟”的比例代理患者层条件概率。C的主代理暴露为非英语文化和语言多样性，并非直接测量患者—医务人员沟通障碍；其Model 1总关联在纳入诊断机构后由OR 2.54衰减至1.23，作者的中介分析提示关联可由更常在公立机构确诊完全中介，因此本文将OR 1.23另作保守敏感性。D和C的OR均来自不同癌种和医疗体系并运输到本模型的有效负担边际，所得条件概率属于证据校准参数，而非加沙人群的直接观测值。现有诊断延迟Meta分析未控制治疗延迟或中断，检索亦未发现可直接估计两者并存时诊断延迟控制直接效应或中介比例的研究，故κ=0.5只是0与1之间的对称中心预设。本文将独立结构、证据低值、证据高值、D-T保守关联、C-T诊断机构调整关联以及κ=0和κ=1分别报告，以显示这些结构假设对结果的影响。
"""
    (evidence_dir / "README.md").write_text(readme, encoding="utf-8")
    return {
        "conditional_overlap_evidence": conditional_rows,
        "diagnostic_residual_evidence": residual_rows,
        "search_log": search_rows,
        "parameter_decisions": parameter_rows,
    }


def point_pattern_table(rows: list[Dict[str, object]], structure: str) -> list[Dict[str, object]]:
    point_effects = {
        code: np.array([float(values["hr"])]) for code, values in FACTORS.items() if code != "E"
    }
    point_effects["E"] = np.array([
        float(FACTORS["E"]["hr"]) ** (float(FACTORS["E"]["delta_x_main"]) / 10.0)
    ])
    point_effects["T"] = np.array([
        float(TREATMENT["hr4"]) ** (float(TREATMENT["delay_weeks"]) / 4.0)
    ])
    residuals = {
        "evidence_calibrated": (0.0, 0.5),
        "diagnosis_residual_0": (0.0, 0.0),
        "diagnosis_residual_1": (0.0, 1.0),
        "full_product": (1.0, 1.0),
    }
    out: list[Dict[str, object]] = []
    for row in rows:
        z = {code: int(row[code]) for code in BINARY_CODES}
        if structure == "additive":
            rr = 1.0 + (point_effects["E"][0] - 1.0)
            rr += sum(z[c] * (point_effects[c][0] - 1.0) for c in BINARY_CODES)
        else:
            ru, rd = residuals[structure]
            rr = point_effects["E"][0] * point_effects["T"][0] ** z["T"]
            for code in ("A", "D", "H", "P", "C"):
                exponent = 1.0
                if z["T"] and code in UPSTREAM_CODES:
                    exponent = ru
                if z["T"] and code == "D":
                    exponent = rd
                rr *= point_effects[code][0] ** (z[code] * exponent)
        enriched = dict(row)
        enriched["point_rr"] = float(rr)
        enriched["weighted_point_rr"] = float(row["probability"]) * float(rr)
        out.append(enriched)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    script_path = Path(__file__).resolve()
    workspace = next(p for p in script_path.parents if (p / "outputs").is_dir())
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else workspace / "outputs" / "joint_effect_model_evidence_calibrated"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    current, authoritative_source = load_authoritative_single_factor_model(workspace)
    current_fit = current.fit_poisson_offset(current.X, current.DEATHS, current.POPULATIONS)
    cov_quasi_list = current.scale_matrix(
        current_fit["covariance_poisson"], current_fit["pearson_phi"]
    )
    fit = {**current_fit, "covariance_quasi": cov_quasi_list}
    beta = np.asarray(current_fit["coefficients"], dtype=float)
    cov_quasi = np.asarray(cov_quasi_list, dtype=float)
    cov_poisson = np.asarray(current_fit["covariance_poisson"], dtype=float)

    # Continue the exact pseudo-random stream used by the authoritative
    # six-factor analysis: trend coefficients first, then A/D/H/P/E/C.
    # T is appended after those six draws, so all existing draws remain intact.
    rng_main = current.random.Random(SEED)
    main_a, main_b = current.draw_bivariate_normal(
        current_fit["coefficients"], cov_quasi_list, N_SIM, rng_main
    )
    baseline_main = np.asarray(
        current.baseline_from_log_coefficients(main_a, main_b), dtype=float
    )

    ordinary_rng = current.random.Random(SEED + 201)
    ordinary_a, ordinary_b = current.draw_bivariate_normal(
        current_fit["coefficients"], current_fit["covariance_poisson"], N_SIM, ordinary_rng
    )
    baseline_ordinary = np.asarray(
        current.baseline_from_log_coefficients(ordinary_a, ordinary_b), dtype=float
    )

    linear_fit = current.fit_ols(current.X, current.DEATHS)
    linear_rng = current.random.Random(SEED + 202)
    linear_a, linear_b = current.draw_bivariate_normal(
        linear_fit["coefficients"],
        linear_fit["covariance"],
        N_SIM,
        linear_rng,
    )
    baseline_linear = np.asarray(
        current.baseline_from_linear_coefficients(linear_a, linear_b), dtype=float
    )

    rates = [y / p * 100_000.0 for y, p in zip(current.DEATHS, current.POPULATIONS)]
    log_rate_fit = current.fit_ols(current.X, [math.log(rate) for rate in rates])
    log_rate_rng = current.random.Random(SEED + 203)
    log_rate_a, log_rate_b = current.draw_bivariate_normal(
        log_rate_fit["coefficients"],
        log_rate_fit["covariance"],
        N_SIM,
        log_rate_rng,
    )
    baseline_log_rate = np.asarray(
        [
            POP_TARGET / 100_000.0 * math.exp(a + X_TARGET * b)
            for a, b in zip(log_rate_a, log_rate_b)
        ],
        dtype=float,
    )

    main_log_hr_draws: Dict[str, np.ndarray] = {}
    effects: Dict[str, np.ndarray] = {}
    for code, values in FACTORS.items():
        log_draws = draw_log_ratio_legacy(
            float(values["hr"]), float(values["lower"]), float(values["upper"]), rng_main
        )
        main_log_hr_draws[code] = log_draws
        if values["effect_type"] == "per10":
            delta = float(values["delta_x_main"]) / 10.0
            base = np.fromiter(
                (math.exp(value * delta) for value in log_draws),
                dtype=float,
                count=N_SIM,
            )
        else:
            base = np.fromiter(
                (math.exp(value) for value in log_draws), dtype=float, count=N_SIM
            )
        effects[code] = base

    treatment_log4 = draw_log_ratio_legacy(
        float(TREATMENT["hr4"]),
        float(TREATMENT["lower4"]),
        float(TREATMENT["upper4"]),
        rng_main,
    )
    treatment_mu, treatment_se = log_hr_params(
        float(TREATMENT["hr4"]), float(TREATMENT["lower4"]), float(TREATMENT["upper4"])
    )
    treatment_z = (treatment_log4 - treatment_mu) / treatment_se
    treatment_4w = np.fromiter(
        (math.exp(value) for value in treatment_log4), dtype=float, count=N_SIM
    )
    effects["T"] = np.power(treatment_4w, float(TREATMENT["delay_weeks"]) / 4.0)

    f_main = f_values("main")
    overlap_constraint_rows = build_overlap_constraint_rows(f_main)
    main_row = calculate_scenario(
        "主分析：证据校准重叠＋D保留50%对数HR",
        "main",
        baseline_main,
        effects,
        f_main,
        "evidence_primary",
        "evidence_calibrated",
        notes="A/H/C与T并存时残余效应为0；D保留50%对数HR（HR^0.5）；P独立且效应保留；T使用全因死亡代理HR。",
    )

    scenarios: list[Dict[str, object]] = [main_row]

    for structure, label in (
        ("diagnosis_residual_0", "D残余0%：诊断延迟也由T完全覆盖"),
        ("evidence_calibrated", "D残余50%：主路径结构"),
        ("diagnosis_residual_1", "D残余100%：诊断延迟效应完全保留"),
        ("full_product", "极端探索：组合内完全乘法"),
        ("additive", "极端探索：加性超额风险"),
    ):
        scenarios.append(calculate_scenario(
            label, "effect_structure", baseline_main, effects, f_main,
            "evidence_primary", structure
        ))

    for overlap_key in (
        "independent", "evidence_low", "evidence_primary",
        "evidence_high", "rao_conservative_d", "tamirat_facility_adjusted_c",
    ):
        scenarios.append(calculate_scenario(
            OVERLAP_SCENARIOS[overlap_key]["label"], "overlap", baseline_main,
            effects, f_main, overlap_key, "evidence_calibrated"
        ))

    for level, label in (("low", "全部f低值"), ("main", "全部f主值"), ("high", "全部f高值")):
        scenarios.append(calculate_scenario(
            label, "exposure_fraction", baseline_main, effects, f_values(level), "evidence_primary", "evidence_calibrated"
        ))

    factor_fraction_labels = {
        **{code: values["factor_zh"] for code, values in FACTORS.items() if code != "E"},
        "T": TREATMENT["factor_zh"],
    }
    for code in ("A", "D", "H", "P", "C", "T"):
        source = TREATMENT if code == "T" else FACTORS[code]
        for level, level_zh in (("low", "低"), ("main", "主"), ("high", "高")):
            alternative_f = dict(f_main)
            alternative_f[code] = float(source[f"f_{level}"])
            scenarios.append(calculate_scenario(
                f"{code}：{factor_fraction_labels[code]} f{level_zh}={alternative_f[code]:.2f}",
                "factor_fraction_oat",
                baseline_main,
                effects,
                alternative_f,
                "evidence_primary",
                "evidence_calibrated",
                notes=f"仅改变{code}的有效暴露份额；其余因素保持主值",
            ))

    for label, legacy_f_c in C_LEGACY_F_SCENARIOS:
        alternative_f = dict(f_main)
        alternative_f["C"] = legacy_f_c
        scenarios.append(calculate_scenario(
            label,
            "communication_legacy_definition",
            baseline_main,
            effects,
            alternative_f,
            "evidence_primary",
            "evidence_calibrated",
            notes="旧方案包含Fair；仅作C定义敏感性，其余因素保持主值",
        ))

    for g in (0.35, 0.50, 0.65, 1.00):
        scenarios.append(calculate_scenario(
            f"g={g:.2f}", "transportability", baseline_main, effects, f_main, "evidence_primary", "evidence_calibrated", g=g
        ))

    for label, delta_x in (("浓度不变", 0.0), ("低增量", 0.5), ("主值", 4.1), ("高增量", 7.2)):
        alternative = dict(effects)
        hr10 = np.exp(main_log_hr_draws["E"])
        alternative["E"] = np.power(hr10, delta_x / 10.0)
        scenarios.append(calculate_scenario(
            label, "particulate_delta", baseline_main, alternative, f_main, "evidence_primary", "evidence_calibrated",
            notes=f"PM2.5浓度增量={delta_x} µg/m³"
        ))

    # Fixed-effect pooling sensitivity for the six retained factors.
    fixed_effects = dict(effects)
    fixed_rng = random.Random(SEED + 101)
    for code, values in FACTORS.items():
        fixed_log = draw_log_ratio_legacy(
            float(values["fixed_hr"]),
            float(values["fixed_lower"]),
            float(values["fixed_upper"]),
            fixed_rng,
        )
        if values["effect_type"] == "per10":
            delta = float(values["delta_x_main"]) / 10.0
            fixed_base = np.fromiter(
                (math.exp(value * delta) for value in fixed_log),
                dtype=float,
                count=N_SIM,
            )
        else:
            fixed_base = np.fromiter(
                (math.exp(value) for value in fixed_log), dtype=float, count=N_SIM
            )
        fixed_effects[code] = fixed_base
    scenarios.append(calculate_scenario(
        "六因素固定效应合并值", "meta_model", baseline_main, fixed_effects, f_main, "evidence_primary", "evidence_calibrated"
    ))

    # Endpoint/proxy sensitivity for the treatment-delay factor.
    treatment_sensitivities = (
        ("完整代理迁移 λT=1", 1.085, 1.051, 1.120, 1.0, "primary proxy"),
        ("半效应代理迁移 λT=0.5", 1.085, 1.051, 1.120, 0.5, "endpoint transfer sensitivity"),
        ("治疗效应置零 λT=0（保留T重叠）", 1.085, 1.051, 1.120, 0.0, "endpoint transfer sensitivity; T overlap retained"),
        ("原文正文四舍五入（全因）", 1.09, 1.051, 1.120, 1.0, "reproduction"),
        ("原文时间敏感性", 1.083, 1.048, 1.119, 1.0, "original time sensitivity"),
    )
    for label, point, lower, upper, transfer_lambda, note in treatment_sensitivities:
        alternative = dict(effects)
        h4 = ratio_draws(treatment_z, point, lower, upper)
        r12 = np.power(h4, float(TREATMENT["delay_weeks"]) / 4.0)
        alternative["T"] = np.power(r12, transfer_lambda)
        scenarios.append(calculate_scenario(
            label, "treatment_endpoint", baseline_main, alternative, f_main, "evidence_primary", "evidence_calibrated",
            notes=f"{note}; λT={transfer_lambda}"
        ))

    scenarios.append(calculate_scenario(
        "固定联合分布下排除T（取消路径抑制）",
        "treatment_endpoint",
        baseline_main,
        effects,
        f_main,
        "evidence_primary",
        "evidence_calibrated",
        notes="固定主分析64格概率；T风险指标置零；A/H/C不再因T而衰减",
        fixed_distribution_active=("A", "D", "H", "P", "E", "C"),
    ))

    for label, baseline in (
        ("准泊松率趋势（主分析）", baseline_main),
        ("普通泊松率趋势", baseline_ordinary),
        ("登记死亡数线性趋势", baseline_linear),
        ("粗死亡率对数线性趋势", baseline_log_rate),
    ):
        scenarios.append(calculate_scenario(
            label, "baseline_model", baseline, effects, f_main, "evidence_primary", "evidence_calibrated"
        ))

    pattern_scenarios: list[Dict[str, object]] = []
    for overlap_key in ("independent", "evidence_primary", "evidence_high"):
        base_rows = pattern_rows(f_main, overlap_key)
        enriched = point_pattern_table(base_rows, "evidence_calibrated")
        for row in enriched:
            row["overlap_scenario_key"] = overlap_key
            row["overlap_scenario"] = OVERLAP_SCENARIOS[overlap_key]["label"]
            pattern_scenarios.append(row)

    shapley_rows, shapley_additivity_error, shapley_total = exact_shapley_decomposition(
        baseline_main,
        effects,
        f_main,
        "evidence_primary",
        "evidence_calibrated",
        g=1.0,
    )

    # Validation checks.
    scenario_constraint_max_error = 0.0
    scenario_min_pattern_probability = 1.0
    scenario_conditional_min = 1.0
    scenario_conditional_max = 0.0
    seen_constraint_sets = set()
    for scenario in scenarios:
        scenario_f = {code: float(scenario[f"f_{code}"]) for code in BINARY_CODES}
        scenario_overlap = str(scenario["overlap_scenario_key"])
        constraint_key = (
            *(scenario_f[code] for code in BINARY_CODES),
            scenario_overlap,
        )
        if constraint_key in seen_constraint_sets:
            continue
        seen_constraint_sets.add(constraint_key)
        rows = pattern_rows(scenario_f, scenario_overlap)
        scenario_min_pattern_probability = min(
            scenario_min_pattern_probability,
            min(float(row["probability"]) for row in rows),
        )
        scenario_constraint_max_error = max(
            scenario_constraint_max_error,
            abs(sum(float(row["probability"]) for row in rows) - 1.0),
        )
        for code in BINARY_CODES:
            calculated = sum(
                float(row["probability"]) * int(row[code]) for row in rows
            )
            scenario_constraint_max_error = max(
                scenario_constraint_max_error, abs(calculated - scenario_f[code])
            )
        scenario_params = overlap_parameters(scenario_f, scenario_overlap)
        for code in PAIR_CODES:
            calculated = sum(
                float(row["probability"]) * int(row[code]) * int(row["T"])
                for row in rows
            )
            scenario_constraint_max_error = max(
                scenario_constraint_max_error,
                abs(calculated - scenario_params[code]["joint_with_T"]),
            )
        conditional_values_all = [
            value
            for values in scenario_params.values()
            for key, value in values.items()
            if key in {"p_given_T1", "p_given_T0"}
        ]
        scenario_conditional_min = min(scenario_conditional_min, *conditional_values_all)
        scenario_conditional_max = max(scenario_conditional_max, *conditional_values_all)

    main_patterns = pattern_rows(f_main, "evidence_primary")
    probability_sum = sum(float(r["probability"]) for r in main_patterns)
    min_pattern_probability = min(float(r["probability"]) for r in main_patterns)
    marginal_errors = {}
    for code in BINARY_CODES:
        calculated = sum(float(r["probability"]) * int(r[code]) for r in main_patterns)
        marginal_errors[code] = calculated - float(f_main[code])
    pair_errors = {}
    target_pairs = overlap_parameters(f_main, "evidence_primary")
    for code in PAIR_CODES:
        calculated = sum(float(r["probability"]) * int(r[code]) * int(r["T"]) for r in main_patterns)
        pair_errors[f"{code}T"] = calculated - target_pairs[code]["joint_with_T"]

    ones = {code: np.ones(N_SIM) for code in (*FACTORS.keys(), "T")}
    t_only = dict(ones)
    t_only["T"] = effects["T"]
    integrated_t = expected_wartime_rr(t_only, f_main, "evidence_primary", "evidence_calibrated")
    direct_t = 1.0 + f_main["T"] * (effects["T"] - 1.0)
    t_reduction_error = float(np.max(np.abs(integrated_t - direct_t)))

    neutral_rr = expected_wartime_rr(ones, f_main, "evidence_primary", "evidence_calibrated")
    neutral_effect_error = float(np.max(np.abs(neutral_rr - 1.0)))
    primary_rr = expected_wartime_rr(effects, f_main, "evidence_primary", "evidence_calibrated")
    fixed_distribution_full_rr = expected_wartime_rr_fixed_distribution(
        effects, f_main, "evidence_primary", "evidence_calibrated", SHAPLEY_CODES
    )
    fixed_distribution_full_error = float(
        np.max(np.abs(primary_rr - fixed_distribution_full_rr))
    )
    additive_low = expected_wartime_rr(effects, f_main, "independent", "additive")
    additive_high = expected_wartime_rr(effects, f_main, "evidence_high", "additive")
    additive_overlap_error = float(np.max(np.abs(additive_low - additive_high)))
    min_additive_pattern_rr = effects["E"].copy()
    for code in BINARY_CODES:
        min_additive_pattern_rr += np.minimum(0.0, effects[code] - 1.0)
    additive_nonpositive_count = int(np.sum(min_additive_pattern_rr <= 0.0))
    additive_nonpositive_percent = 100.0 * additive_nonpositive_count / N_SIM
    cond_main = overlap_parameters(f_main, "evidence_primary")
    conditional_values = [
        value
        for code in cond_main.values()
        for key, value in code.items()
        if key in {"p_given_T1", "p_given_T0"}
    ]
    conditional_min = min(conditional_values)
    conditional_max = max(conditional_values)

    # Confirm exact continuity with the saved authoritative baseline summary.
    authoritative_results_path = workspace / "outputs" / "manuscript_revision" / "analysis_results.json"
    authoritative_results = json.loads(authoritative_results_path.read_text(encoding="utf-8"))
    authoritative_baseline = next(
        row
        for row in authoritative_results["baseline_summary_rows"]
        if row["model_code"] == "quasi_poisson_primary"
    )
    computed_baseline_summary = percentile_summary(baseline_main)
    baseline_summary_errors = {
        "lower_2_5": computed_baseline_summary["lower_2_5"]
        - float(authoritative_baseline["baseline_deaths_lower_2_5"]),
        "median": computed_baseline_summary["median"]
        - float(authoritative_baseline["baseline_deaths_median"]),
        "upper_97_5": computed_baseline_summary["upper_97_5"]
        - float(authoritative_baseline["baseline_deaths_upper_97_5"]),
    }

    # Ten deterministic blocks provide a simple Monte Carlo stability record.
    main_additional = shapley_total
    block_summaries = []
    for index, block in enumerate(np.array_split(main_additional, 10), start=1):
        summary = percentile_summary(block)
        block_summaries.append({"block": index, **summary})

    validations = {
        "pattern_probability_sum": probability_sum,
        "minimum_pattern_probability": min_pattern_probability,
        "conditional_probability_min": conditional_min,
        "conditional_probability_max": conditional_max,
        "max_abs_marginal_error": max(abs(v) for v in marginal_errors.values()),
        "marginal_errors": marginal_errors,
        "max_abs_pair_error": max(abs(v) for v in pair_errors.values()),
        "pair_errors": pair_errors,
        "all_reported_scenarios_constraint_max_abs_error": scenario_constraint_max_error,
        "all_reported_scenarios_minimum_pattern_probability": scenario_min_pattern_probability,
        "all_reported_scenarios_conditional_probability_min": scenario_conditional_min,
        "all_reported_scenarios_conditional_probability_max": scenario_conditional_max,
        "treatment_only_reduction_max_abs_error": t_reduction_error,
        "neutral_effect_max_abs_error": neutral_effect_error,
        "fixed_distribution_full_coalition_max_abs_error": fixed_distribution_full_error,
        "additive_overlap_invariance_max_abs_error": additive_overlap_error,
        "additive_minimum_pattern_rr": float(np.min(min_additive_pattern_rr)),
        "additive_nonpositive_pattern_draw_count": additive_nonpositive_count,
        "additive_nonpositive_pattern_draw_percent": additive_nonpositive_percent,
        "shapley_additivity_max_abs_error": shapley_additivity_error,
        "authoritative_baseline_summary_errors": baseline_summary_errors,
        "authoritative_baseline_summary_max_abs_error": max(
            abs(value) for value in baseline_summary_errors.values()
        ),
        "baseline_first_three_float_hex": [float(value).hex() for value in baseline_main[:3]],
        "monte_carlo_block_summaries": block_summaries,
        "all_scenarios_finite": all(
            math.isfinite(float(row["joint_deaths_median"])) for row in scenarios
        ),
        "all_wartime_rr_positive": all(float(row["min_wartime_rr"]) > 0.0 for row in scenarios),
        "status": "PASS",
    }
    if (
        abs(probability_sum - 1.0) > 1e-12
        or min_pattern_probability < -1e-14
        or conditional_min < -1e-12
        or conditional_max > 1.0 + 1e-12
        or validations["max_abs_marginal_error"] > 1e-12
        or validations["max_abs_pair_error"] > 1e-12
        or scenario_constraint_max_error > 1e-12
        or scenario_min_pattern_probability < -1e-14
        or scenario_conditional_min < -1e-12
        or scenario_conditional_max > 1.0 + 1e-12
        or t_reduction_error > 1e-12
        or neutral_effect_error > 1e-12
        or fixed_distribution_full_error > 1e-12
        or additive_overlap_error > 1e-12
        or additive_nonpositive_count > 0
        or shapley_additivity_error > 1e-9
        or validations["authoritative_baseline_summary_max_abs_error"] > 1e-12
        or not validations["all_scenarios_finite"]
        or not validations["all_wartime_rr_positive"]
    ):
        validations["status"] = "FAIL"
        raise RuntimeError(json.dumps(validations, ensure_ascii=False, indent=2))

    factor_rows = []
    for code, values in FACTORS.items():
        factor_rows.append({"code": code, **values})
    factor_rows.append({
        "code": "T",
        "factor_zh": TREATMENT["factor_zh"],
        "factor_en": TREATMENT["factor_en"],
        "model": "random",
        "hr": TREATMENT["hr4"],
        "lower": TREATMENT["lower4"],
        "upper": TREATMENT["upper4"],
        "hr_12week": float(TREATMENT["hr4"]) ** 3,
        "lower_12week": float(TREATMENT["lower4"]) ** 3,
        "upper_12week": float(TREATMENT["upper4"]) ** 3,
        "i2": 98.3,
        "f_low": TREATMENT["f_low"],
        "f_main": TREATMENT["f_main"],
        "f_high": TREATMENT["f_high"],
        "effect_type": "per4weeks_then_power3",
        "outcome": TREATMENT["outcome"],
    })

    baseline_rows = []
    for code, label, values in (
        ("quasi_poisson", "准泊松率趋势（主分析）", baseline_main),
        ("ordinary_poisson", "普通泊松率趋势", baseline_ordinary),
        ("linear_count", "登记死亡数线性趋势", baseline_linear),
        ("log_linear_rate", "粗死亡率对数线性趋势", baseline_log_rate),
    ):
        row = {"model_code": code, "model_zh": label}
        for key, value in percentile_summary(values).items():
            row[f"baseline_deaths_{key}"] = value
        baseline_rows.append(row)

    treatment_reference_rows = [{
        "scenario": "治疗延迟或中断单独参照（程序核验/补充材料）",
        "outcome": TREATMENT["outcome"],
        "hr_per_4_weeks": TREATMENT["hr4"],
        "hr_per_4_weeks_lower_95": TREATMENT["lower4"],
        "hr_per_4_weeks_upper_95": TREATMENT["upper4"],
        "hr_12_weeks": float(TREATMENT["hr4"]) ** 3,
        "hr_12_weeks_lower_95": float(TREATMENT["lower4"]) ** 3,
        "hr_12_weeks_upper_95": float(TREATMENT["upper4"]) ** 3,
        "f_T": f_main["T"],
        "g": 1.0,
        "duration_fraction": Q,
        "deaths_lower_2_5": main_row["treatment_only_deaths_lower_2_5"],
        "deaths_median": main_row["treatment_only_deaths_median"],
        "deaths_upper_97_5": main_row["treatment_only_deaths_upper_97_5"],
        "additional_deaths_lower_2_5": main_row["treatment_only_additional_deaths_lower_2_5"],
        "additional_deaths_median": main_row["treatment_only_additional_deaths_median"],
        "additional_deaths_upper_97_5": main_row["treatment_only_additional_deaths_upper_97_5"],
        "percent_change_lower_2_5": main_row["treatment_only_percent_change_lower_2_5"],
        "percent_change_median": main_row["treatment_only_percent_change_median"],
        "percent_change_upper_97_5": main_row["treatment_only_percent_change_upper_97_5"],
        "p_additional_positive_percent": main_row[
            "p_treatment_only_additional_positive_percent"
        ],
        "interpretation": "总体生存/全因死亡代理；不作为新增因素的主结果",
    }]

    write_csv(output_dir / "factor_inputs.csv", factor_rows)
    write_csv(output_dir / "joint_scenarios.csv", scenarios)
    write_csv(output_dir / "pattern_probabilities.csv", pattern_scenarios)
    write_csv(output_dir / "overlap_constraints.csv", overlap_constraint_rows)
    write_csv(output_dir / "baseline_models.csv", baseline_rows)
    write_csv(output_dir / "shapley_contributions.csv", shapley_rows)
    write_csv(output_dir / "treatment_only_reference.csv", treatment_reference_rows)
    evidence_records = write_evidence_records(output_dir, f_main)

    config = {
        "analysis_version": "joint-effect-v2.1-2016-2022-baseline-evidence-calibrated",
        "estimand_zh": "2016—2022年战前登记趋势延续条件下，2023年加沙七因素联合暴露情景的癌症登记死亡增量",
        "simulation": {
            "draws": N_SIM,
            "master_seed": SEED,
            "duration_months": DURATION_MONTHS,
            "duration_fraction": Q,
            "primary_g": 1.0,
        },
        "primary_structure": "evidence_calibrated",
        "primary_diagnostic_residual_log_hr_fraction": 0.5,
        "primary_overlap_scenario": "evidence_primary",
        "primary_overlap_status": "evidence-calibrated scenario with structural assumptions stated explicitly",
        "overlap_model": "maximum-entropy star model; A nested within T; D/H/C pair intersections calibrated from evidence odds ratios at current margins; P independent; A/D/H/P/C conditionally independent given T",
        "overlap_constraints": overlap_constraint_rows,
        "evidence_records": evidence_records,
        "shapley": "exact 2^7-coalition allocation of the primary joint-model increment; model decomposition, not independent causal deaths",
        "authoritative_rng_source": str(authoritative_source),
        "treatment_endpoint_warning": "Treatment-delay HR is overall-survival/all-cause mortality and is used as an external proxy in the cancer-specific scenario.",
        "factor_inputs": factor_rows,
        "effective_fraction_interpretation": "f and the 64-cell probabilities are approximations to effective shares of the baseline registered cancer-death burden, not directly observed patient prevalence",
        "baseline": {
            "years": YEARS.astype(int).tolist(),
            "deaths": DEATHS.astype(int).tolist(),
            "populations": POPULATIONS.astype(int).tolist(),
            "target_year": TARGET_YEAR,
            "target_population": int(POP_TARGET),
            "coefficients": beta.tolist(),
            "covariance_poisson": cov_poisson.tolist(),
            "covariance_quasi": cov_quasi.tolist(),
            "pearson_phi": fit["pearson_phi"],
        },
    }
    (output_dir / "analysis_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "validation_report.json").write_text(json.dumps(validations, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "analysis_results.json").write_text(
        json.dumps({
            "main": main_row,
            "scenarios": scenarios,
            "baseline_models": baseline_rows,
            "overlap_constraints": overlap_constraint_rows,
            "evidence_records": evidence_records,
            "shapley": shapley_rows,
            "treatment_only_reference": treatment_reference_rows[0],
            "validation": validations,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    readme = """# 七因素综合效应蒙特卡洛分析（证据校准版）

本目录是新建的独立分析，不覆盖此前逐因素Excel、代码或Word文档。

趋势基线和六个既有因素沿用现行逐因素脚本的 `random.Random(20260921)` 抽样顺序；基线三个位点与现行结果完全一致。治疗因素在六因素之后追加抽样，不会改变既有随机流。

主分析使用现行准泊松趋势基线、100,000次蒙特卡洛抽样、3/12战争期和中心暴露份额。颗粒物作为全人群连续暴露处理，其余六个二元因素形成64种互斥组合。A、D、H、C与T的交集通过最大熵星形模型生成：A按实际许可延迟或拒绝定义并嵌套于T；D采用Gade患者级2×2所得OR 4.4299；H采用RCR机构级放疗延迟92%校准出的OR；C采用Tamirat调整OR 2.54；P与T独立。OR均在当前有效边际下转换为合法交集与条件概率。

E明确列为探索性分析，因为主浓度增量只来自2023年10月单月监测，不能观察11—12月的月际变化。C的主分级改为低值Very poor（66/658）、主值Very poor+Poor（197/658）、高值Good+Poor+Very poor（361/658，排除Excellent和Fair）。旧分级197/658、395/658、559/658继续保留为定义敏感性，其中后两档包含Fair。

模型中的 `f` 及64种组合概率解释为基线癌症登记死亡负担的“有效暴露份额”近似，不等同于已经观测到的患者患病率或人群暴露率。

主分析采用路径调整：A、H、C与T并存时残余效应为0；D的对数HR保留50%，即使用HR_D^0.5；P和E保留。D残余0%与100%作为结构敏感性，并将完全乘法和加性超额风险保留为极端探索情景。

治疗延迟效应使用原文每4周HR 1.085（95%CI 1.051–1.120），12周效应为其三次方。该HR对应总体生存/全因死亡，在癌症特异性模型中只作为外部代理参数。治疗端点敏感性分别令对数效应迁移系数λT为1、0.5和0，并复现正文四舍五入值及原文时间敏感性结果。

不确定区间只包含固定模型结构下的趋势基线和HR参数不确定性。f、g、联合暴露相关程度、效应组合规则、Meta模型和基线模型差异分别列为结构敏感性，不混入同一个95%区间。

核心文件：

- `analysis_config.json`：全部参数和模型定义
- `joint_scenarios.csv`：主分析及各敏感性结果
- `pattern_probabilities.csv`：64种组合及其概率
- `overlap_constraints.csv`：独立、证据低值、证据主值、证据高值、Rao保守D-T及Tamirat诊断机构调整C-T情景的Fréchet界、交集与条件概率
- `evidence_records/`：条件概率、D残余效应、检索过程和参数决策的完整记录；README含可直接写入论文的方法与局限性段落
- `shapley_contributions.csv`：七因素对联合模型增量的精确Shapley分配
- `treatment_only_reference.csv`：治疗因素单独参照，仅供程序核验和补充材料
- `baseline_models.csv`：四种趋势基线
- `validation_report.json`：概率、边际、交集和原文公式退化校验
- `analysis_results.json`：主要机器可读结果
- `joint_effect_monte_carlo_evidence_calibrated.py`：完整可复现代码
- `build_evidence_calibrated_workbook.mjs`：证据校准版工作簿生成代码
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    copied_script = output_dir / "joint_effect_monte_carlo_evidence_calibrated.py"
    shutil.copy2(script_path, copied_script)

    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    manifest_files = [
        "analysis_config.json",
        "analysis_results.json",
        "baseline_models.csv",
        "factor_inputs.csv",
        "joint_scenarios.csv",
        "overlap_constraints.csv",
        "pattern_probabilities.csv",
        "shapley_contributions.csv",
        "treatment_only_reference.csv",
        "validation_report.json",
        "README.md",
        "joint_effect_monte_carlo_evidence_calibrated.py",
        "build_evidence_calibrated_workbook.mjs",
        "evidence_records/conditional_overlap_evidence.csv",
        "evidence_records/diagnostic_residual_evidence.csv",
        "evidence_records/search_log.csv",
        "evidence_records/parameter_decisions.csv",
        "evidence_records/README.md",
    ]
    manifest = {
        "analysis_version": config["analysis_version"],
        "simulation_seed": SEED,
        "simulation_draws": N_SIM,
        "authoritative_source": str(authoritative_source),
        "authoritative_source_sha256": sha256(authoritative_source),
        "authoritative_results_source": str(authoritative_results_path),
        "authoritative_results_source_sha256": sha256(authoritative_results_path),
        "outputs_sha256": {
            name: sha256(output_dir / name) for name in manifest_files
        },
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps({
        "output_dir": str(output_dir),
        "validation": validations,
        "main": {
            key: value for key, value in main_row.items()
            if key in {
                "joint_deaths_lower_2_5", "joint_deaths_median", "joint_deaths_upper_97_5",
                "additional_deaths_lower_2_5", "additional_deaths_median", "additional_deaths_upper_97_5",
                "percent_change_lower_2_5", "percent_change_median", "percent_change_upper_97_5",
                "beyond_treatment_deaths_lower_2_5", "beyond_treatment_deaths_median", "beyond_treatment_deaths_upper_97_5",
            }
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

