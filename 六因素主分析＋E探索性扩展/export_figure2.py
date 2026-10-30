from __future__ import annotations

import csv
from html import escape
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "results" / "joint_scenarios.csv"
OUTDIR = ROOT / "results" / "figures"
SVG_OUT = OUTDIR / "Figure_2_primary_six_factor_joint_sensitivity.svg"
CAPTION_OUT = OUTDIR / "Figure_2_caption_replacement.txt"


def text_element(x, y, content, size, color, *, anchor="start", weight="400"):
    return (
        f'<text x="{x:g}" y="{y:g}" text-anchor="{anchor}" '
        'dominant-baseline="middle" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{color}">'
        f"{escape(content)}</text>"
    )


def main() -> None:
    with DATA.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    def get(category: str, scenario: str):
        matches = [r for r in rows if r["category"] == category and r["scenario"] == scenario]
        if len(matches) != 1:
            raise RuntimeError((category, scenario, len(matches)))
        return matches[0]

    selection = [
        ("Primary six-factor model", get("main", "主分析：证据校准重叠＋D保留50%对数HR"), "primary"),
        ("0% D residual effect", get("effect_structure", "D残余0%：诊断延迟也由T完全覆盖"), "standard"),
        ("100% D residual effect", get("effect_structure", "D残余100%：诊断延迟效应完全保留"), "standard"),
        ("Independent overlap structure", get("overlap", "独立结构"), "standard"),
        ("Evidence-calibrated low overlap", get("overlap", "证据低值"), "standard"),
        ("Evidence-calibrated high overlap", get("overlap", "证据高值"), "standard"),
        ("Treatment endpoint transport λT = 0.5", get("treatment_endpoint", "半效应代理迁移 λT=0.5"), "standard"),
        ("Treatment endpoint transport λT = 0", get("treatment_endpoint", "治疗效应置零 λT=0（保留T重叠）"), "standard"),
        ("Fixed-effect estimates for A/D/H/P/C", get("meta_model", "主联合五个新增因素固定效应合并值"), "standard"),
        ("Extreme: full multiplicative model", get("effect_structure", "极端探索：组合内完全乘法"), "standard"),
        ("Extreme: additive excess risk", get("effect_structure", "极端探索：加性超额风险"), "standard"),
        ("Exploratory addition of E (Δx = 4.1 μg/m³)", get("exploratory_particulate_extension", "探索性主值"), "exploratory"),
    ]

    width, height = 3000, 2100
    left, right = 1080.0, 2260.0
    top, bottom = 205.0, 1745.0
    xmin, xmax = 0.0, 550.0

    def x_pos(value: float) -> float:
        return left + (value - xmin) / (xmax - xmin) * (right - left)

    svg = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="figure-title figure-desc">',
        '<title id="figure-title">Primary six-factor joint increment and key sensitivity analyses</title>',
        '<desc id="figure-desc">Forest plot of the primary six-factor joint model excluding exploratory particulate-matter exposure. The exploratory seven-factor extension including particulate matter is displayed separately.</desc>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#FFFFFF"/>',
        text_element(width / 2, 65, "Primary Six-Factor Joint Increment and Key Sensitivity Analyses", 50, "#17365D", anchor="middle", weight="700"),
        text_element(width / 2, 125, "A, D, H, P, C, and T in the primary model; E added only as an exploratory extension", 25, "#5B6573", anchor="middle"),
    ]

    for tick in range(0, 551, 50):
        xx = x_pos(float(tick))
        svg.append(f'<line x1="{xx:.3f}" y1="{top}" x2="{xx:.3f}" y2="{bottom}" stroke="#E3E7EB" stroke-width="2"/>')
        svg.append(text_element(xx, bottom + 45, str(tick), 21, "#4B5563", anchor="middle"))
    svg.append(f'<line x1="{left:.3f}" y1="{top - 10:.3f}" x2="{left:.3f}" y2="{bottom:.3f}" stroke="#8B1E1E" stroke-width="5"/>')

    colors = {"primary": "#17365D", "standard": "#5B9BD5", "exploratory": "#C55A11"}
    for index, (label, row, role) in enumerate(selection):
        yy = top + 52 + index * 122
        lower = float(row["additional_deaths_lower_2_5"])
        median = float(row["additional_deaths_median"])
        upper = float(row["additional_deaths_upper_97_5"])
        color = colors[role]
        weight = "700" if role in {"primary", "exploratory"} else "400"
        radius = 15 if role == "primary" else 12
        lx, mx, ux = x_pos(max(lower, xmin)), x_pos(median), x_pos(min(upper, xmax))
        svg.append(text_element(45, yy, label, 27, "#1F2937", weight=weight))
        svg.append(f'<line x1="{lx:.3f}" y1="{yy}" x2="{ux:.3f}" y2="{yy}" stroke="{color}" stroke-width="10"/>')
        svg.append(f'<line x1="{lx:.3f}" y1="{yy - 14}" x2="{lx:.3f}" y2="{yy + 14}" stroke="{color}" stroke-width="4"/>')
        svg.append(f'<line x1="{ux:.3f}" y1="{yy - 14}" x2="{ux:.3f}" y2="{yy + 14}" stroke="{color}" stroke-width="4"/>')
        svg.append(f'<circle cx="{mx:.3f}" cy="{yy}" r="{radius}" fill="{color}"/>')
        svg.append(text_element(right + 40, yy, f"{median:.1f} ({lower:.1f}–{upper:.1f})", 23, "#1F2937", weight=weight))

    svg.extend([
        f'<line x1="{left:.3f}" y1="{bottom:.3f}" x2="{right:.3f}" y2="{bottom:.3f}" stroke="#4B5563" stroke-width="3"/>',
        text_element((left + right) / 2, bottom + 95, "Paired increment relative to the common baseline (deaths; median and 95% UI)", 28, "#374151", anchor="middle"),
        text_element(width / 2, 1950, "E is excluded from the primary model and shown only in the orange exploratory extension.", 23, "#5B6573", anchor="middle"),
        "</svg>",
    ])

    OUTDIR.mkdir(parents=True, exist_ok=True)
    SVG_OUT.write_text("\n".join(svg) + "\n", encoding="utf-8")
    ElementTree.parse(SVG_OUT)
    caption = (
        "Figure 2. Increment in registered cancer deaths under the primary six-factor joint model and key sensitivity analyses. "
        "Points indicate medians and horizontal lines indicate 95% uncertainty intervals from 100,000 Monte Carlo draws. "
        "The primary model combined health-care access barriers, diagnostic delay, health workforce loss or shortage, psychosocial stress, "
        "patient–provider communication barriers, and treatment delay or interruption. Particulate-matter exposure was excluded from the "
        "primary joint model and added only in the orange exploratory seven-factor extension using Δx=4.1 μg/m³. Full multiplication and "
        "additive excess risk are extreme structural explorations."
    )
    CAPTION_OUT.write_text(caption + "\n", encoding="utf-8")
    print(SVG_OUT)


if __name__ == "__main__":
    main()
