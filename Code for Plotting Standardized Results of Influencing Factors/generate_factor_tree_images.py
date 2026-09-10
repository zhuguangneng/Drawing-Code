#!/usr/bin/env python
"""Regenerate the bilingual publication figures from prepared statistics.

This is the small, user-facing entry point.  The exact production rendering
functions are kept in ``production_renderer.py`` so the figures produced here
use the same layout and drawing code as the formal project outputs.

Examples
--------
Generate Chinese and English SVG/PDF/600-dpi PNG files::

    python generate_factor_tree_images.py \
        --data visualization_data.json \
        --output-dir generated_figures

Generate only the English figure at 600 dpi::

    python generate_factor_tree_images.py --language en
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader

import production_renderer as renderer


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_data(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"metrics", "category_summary", "main_rows"}
    missing = sorted(required.difference(data))
    if missing:
        raise ValueError(f"Input JSON is missing required keys: {missing}")

    metrics = data["metrics"]
    categories = data["category_summary"]
    factors = data["main_rows"]
    if len(categories) != metrics["category_count"]:
        raise ValueError("Category count does not match metrics.category_count")
    if len(factors) != metrics["ge2_factor_count"]:
        raise ValueError("Factor count does not match metrics.ge2_factor_count")
    if any(int(row["frequency"]) < 2 for row in factors):
        raise ValueError("main_rows contains a factor with frequency below 2")
    if sum(int(row["frequency"]) for row in factors) != metrics["shown_frequency"]:
        raise ValueError("Factor frequencies do not sum to metrics.shown_frequency")

    category_names = {row["category_cn"] for row in categories}
    orders = [int(row["order"]) for row in categories]
    if orders != list(range(1, len(categories) + 1)):
        raise ValueError("category_summary must be ordered consecutively by order")
    color_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
    factor_keys: set[tuple[str, str]] = set()
    ranks_by_category: dict[str, list[int]] = {name: [] for name in category_names}
    for row in factors:
        if row["category_cn"] not in category_names:
            raise ValueError(f"Unknown category in main_rows: {row['category_cn']}")
        if not row.get("factor_cn") or not row.get("factor_en"):
            raise ValueError("Every plotted factor needs Chinese and English names")
        key = (row["category_cn"], row["factor_cn"])
        if key in factor_keys:
            raise ValueError(f"Duplicate factor key: {key}")
        factor_keys.add(key)
        ranks_by_category[row["category_cn"]].append(int(row["within_category_rank"]))

    for category in categories:
        name = category["category_cn"]
        rows = [row for row in factors if row["category_cn"] == name]
        if sum(int(row["frequency"]) for row in rows) != int(category["shown_frequency"]):
            raise ValueError(f"shown_frequency mismatch for category: {name}")
        expected_ranks = list(range(1, len(rows) + 1))
        if ranks_by_category[name] != expected_ranks:
            raise ValueError(f"within_category_rank is not consecutive for category: {name}")
        colors = category.get("colors", {})
        if not color_pattern.fullmatch(str(colors.get("dark", ""))):
            raise ValueError(f"Invalid dark color for category: {name}")
        if not color_pattern.fullmatch(str(colors.get("light", ""))):
            raise ValueError(f"Invalid light color for category: {name}")

    expected_nodes = len(categories) + len(factors)
    if expected_nodes != metrics["tree_node_count"]:
        raise ValueError("Node count does not match metrics.tree_node_count")
    return data


def apply_optional_titles(data: dict[str, Any]) -> None:
    titles = data.get("titles", {})
    mapping = {
        "CN_TITLE": "cn_title",
        "CN_SUBTITLE": "cn_subtitle",
        "CN_NOTE": "cn_note",
        "EN_TITLE": "en_title",
        "EN_SUBTITLE": "en_subtitle",
        "EN_NOTE": "en_note",
    }
    for attribute, key in mapping.items():
        value = titles.get(key)
        if value:
            setattr(renderer, attribute, str(value))


def apply_optional_fonts(args: argparse.Namespace) -> None:
    overrides = {
        "CN_REGULAR_CANDIDATES": args.cn_regular_font,
        "CN_BOLD_CANDIDATES": args.cn_bold_font,
        "EN_REGULAR_CANDIDATES": args.en_regular_font,
        "EN_BOLD_CANDIDATES": args.en_bold_font,
    }
    for attribute, value in overrides.items():
        if value:
            setattr(renderer, attribute, [Path(value).expanduser().resolve()])


def validate_svg(path: Path, category_count: int, factor_count: int) -> None:
    root = ET.parse(path).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    category_nodes = root.findall(".//svg:g[@class='category-node']", namespace)
    factor_nodes = root.findall(".//svg:g[@class='factor-node']", namespace)
    if len(category_nodes) != category_count or len(factor_nodes) != factor_count:
        raise RuntimeError(
            f"SVG node validation failed: categories={len(category_nodes)}, "
            f"factors={len(factor_nodes)}"
        )


def validate_pdf(path: Path, width_pt: float, height_pt: float) -> None:
    reader = PdfReader(str(path))
    if len(reader.pages) != 1:
        raise RuntimeError(f"PDF should contain one page, found {len(reader.pages)}")
    box = reader.pages[0].mediabox
    actual = (round(float(box.width), 2), round(float(box.height), 2))
    expected = (round(width_pt, 2), round(height_pt, 2))
    if actual != expected:
        raise RuntimeError(f"PDF page size mismatch: expected {expected}, found {actual}")


def validate_png(path: Path, width_pt: float, height_pt: float, dpi: int) -> None:
    expected_size = (round(width_pt * dpi / 72), round(height_pt * dpi / 72))
    with Image.open(path) as image:
        actual_dpi = image.info.get("dpi", (0, 0))
        if image.size != expected_size:
            raise RuntimeError(
                f"PNG pixel size mismatch: expected {expected_size}, found {image.size}"
            )
        if min(actual_dpi) < dpi - 1:
            raise RuntimeError(f"PNG DPI metadata is below {dpi}: {actual_dpi}")


def render_language(
    data: dict[str, Any],
    layout: dict[str, Any],
    language: str,
    output_dir: Path,
) -> dict[str, Any]:
    names = {
        "svg": f"factor_tree_{language}.svg",
        "pdf": f"factor_tree_{language}.pdf",
        "png": f"factor_tree_{language}_{renderer.PNG_DPI}dpi.png",
    }
    paths = {kind: output_dir / filename for kind, filename in names.items()}
    renderer.render_svg_compact(data, layout, language, paths["svg"])
    renderer.render_pdf_compact(data, layout, language, paths["pdf"])
    renderer.render_png_compact(data, layout, language, paths["png"])

    validate_svg(
        paths["svg"],
        data["metrics"]["category_count"],
        data["metrics"]["ge2_factor_count"],
    )
    validate_pdf(paths["pdf"], layout["width"], layout["height"])
    validate_png(paths["png"], layout["width"], layout["height"], renderer.PNG_DPI)
    return {
        kind: {
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for kind, path in paths.items()
    }


def runtime_manifest() -> dict[str, Any]:
    font_sets = {
        "cn_regular": renderer.CN_REGULAR_CANDIDATES,
        "cn_bold": renderer.CN_BOLD_CANDIDATES,
        "en_regular": renderer.EN_REGULAR_CANDIDATES,
        "en_bold": renderer.EN_BOLD_CANDIDATES,
    }
    fonts = {}
    for role, candidates in font_sets.items():
        selected = renderer.pick_font(candidates).resolve()
        fonts[role] = {"path": str(selected), "sha256": sha256(selected)}
    packages = {}
    for distribution in ("pandas", "Pillow", "reportlab", "pypdf"):
        try:
            packages[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[distribution] = None
    return {
        "python": sys.version.split()[0],
        "packages": packages,
        "fonts": fonts,
        "entrypoint_sha256": sha256(Path(__file__).resolve()),
        "renderer_sha256": sha256(Path(renderer.__file__).resolve()),
        "note": "SVG keeps text editable and references font families; PDF files may contain run-specific metadata/IDs.",
    }


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Generate the bilingual two-level standard-factor tree figures."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=script_dir / "visualization_data.json",
        help="Prepared visualization JSON (default: file beside this script).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "generated_figures",
        help="Directory for SVG, PDF, PNG and manifest outputs.",
    )
    parser.add_argument(
        "--language",
        choices=("both", "cn", "en"),
        default="both",
        help="Language edition to render (default: both).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=600,
        help="Native PNG rasterization DPI (default: 600).",
    )
    parser.add_argument("--cn-regular-font", help="Optional Chinese regular TTF/TTC path.")
    parser.add_argument("--cn-bold-font", help="Optional Chinese bold TTF/TTC path.")
    parser.add_argument("--en-regular-font", help="Optional English regular TTF path.")
    parser.add_argument("--en-bold-font", help="Optional English bold TTF path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 72 <= args.dpi <= 2400:
        raise ValueError("--dpi must be between 72 and 2400")

    data_path = args.data.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_data(data_path)
    apply_optional_titles(data)
    apply_optional_fonts(args)
    renderer.PNG_DPI = args.dpi
    layout = renderer.build_layout(data)

    languages = ("cn", "en") if args.language == "both" else (args.language,)
    outputs = {
        language: render_language(data, layout, language, output_dir)
        for language in languages
    }
    manifest = {
        "status": "passed",
        "input_json": str(data_path),
        "input_sha256": sha256(data_path),
        "languages": list(languages),
        "layout": {
            "design": layout["design"],
            "width_pt": layout["width"],
            "height_pt": layout["height"],
            "width_in": layout["physical_width_in"],
            "height_in": layout["physical_height_in"],
            "png_dpi": renderer.PNG_DPI,
            "category_nodes": len(layout["category_nodes"]),
            "factor_nodes": len(layout["factor_nodes"]),
        },
        "metrics": data["metrics"],
        "runtime": runtime_manifest(),
        "outputs": outputs,
    }
    manifest_path = output_dir / "render_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
