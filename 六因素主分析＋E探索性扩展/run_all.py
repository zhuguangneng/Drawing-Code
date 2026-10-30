#!/usr/bin/env python3
"""Run the primary six-factor model, flat-rate sensitivity, figure, and checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(ROOT / script), *args], cwd=ROOT, check=True)


def main() -> None:
    run("joint_effect_monte_carlo_evidence_calibrated.py")
    run("flat_baseline_sensitivity.py")
    run("export_figure2.py")
    run("verify_outputs.py")


if __name__ == "__main__":
    main()
