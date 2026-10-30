# Primary Six-Factor Model and Exploratory E Extension

This folder reproduces the final joint-model analysis reported in the manuscript.

## Analysis roles

- **Primary model:** A, D, H, P, C, and T.
- **Exploratory extension:** E (particulate-matter exposure) is added only as a continuous area-level multiplier using the October 2023 proxy.
- E is excluded from the primary 64-cell joint distribution because its Gaza exposure proxy is based on one month of monitoring from a station outside Gaza and differs in direction from the satellite alternative.

## Main reproducible results

- Primary six-factor increment: **173.5 deaths** (95% UI 90.9–286.5).
- Primary six-factor scenario deaths: **1172.8** (965.4–1424.6).
- Primary relative increase: **17.44%** (9.32%–27.70%).
- Exploratory extension including E at Δx=4.1 µg/m³: **239.8 additional deaths** (131.2–391.6).
- Random seed: **20260921**; Monte Carlo draws: **100,000**.

## Requirements

- Python 3.10 or later
- NumPy (see `requirements.txt`)

Install and run:

```bash
python -m pip install -r requirements.txt
python run_all.py
```

All generated files are written to `results/`. Running the analysis does not modify the source files.

## Files

- `joint_effect_monte_carlo_evidence_calibrated.py`: primary six-factor model and exploratory E extension, including overlap, pathway, endpoint-transport, Shapley, and sensitivity scenarios.
- `single_factor_support.py`: bundled historical-trend and random-draw functions used to preserve the analysis stream.
- `flat_baseline_sensitivity.py`: 2019–2022 average registered-mortality-rate sensitivity.
- `export_figure2.py`: generates the final Figure 2 SVG and caption.
- `verify_outputs.py`: checks the headline results, 64-cell probability sum, and program validation status.
- `run_all.py`: runs the full sequence.
- `authoritative_analysis_results.json`: frozen baseline summary used for continuity verification.
- `evidence_records/`: traceable records for overlap parameters and the diagnostic-delay residual assumption.
- `reference_results/`: frozen configuration and factor/overlap inputs from the final analysis.

## Interpretation

The outputs are conditional scenario estimates on the registered-death scale. Shapley values allocate the modelled increment under the specified joint distribution and pathway rules; they are not independently attributable deaths. The primary setting uses `g=1.00` as a no-attenuation upper-bound scenario. Omitted wartime pathways may bias estimates downward, while upper-bound affected-burden mappings and `g=1.00` may bias them upward; the net direction of bias is uncertain.
