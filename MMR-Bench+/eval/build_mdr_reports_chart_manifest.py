#!/usr/bin/env python
"""Build a chart-evaluation manifest from multimodal_deepresearcher_reports."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def slug_to_topic(slug: str) -> str:
    topic = slug.replace("--", ": ")
    topic = topic.replace("-", " ")
    return topic


def extract_visualization_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    start_tag = "<visualization>"
    end_tag = "</visualization>"
    start = 0
    while True:
        left = text.find(start_tag, start)
        if left == -1:
            break
        left += len(start_tag)
        right = text.find(end_tag, left)
        if right == -1:
            break
        blocks.append(text[left:right].strip())
        start = right + len(end_tag)
    return blocks


def html_index(path: Path) -> int:
    match = re.search(r"html_(\d+)_screenshot\.png$", path.name)
    if not match:
        raise ValueError(f"Unexpected screenshot name: {path.name}")
    return int(match.group(1))


def build_manifest(dataset_root: Path, extracted_specs_dir: Path) -> tuple[dict, list[dict]]:
    reports = []
    mismatches = []

    topic_dirs = sorted([path for path in dataset_root.iterdir() if path.is_dir()])
    for topic_dir in topic_dirs:
        textual_report = topic_dir / "textual_report.md"
        charts_dir = topic_dir / "html_charts"
        final_report = topic_dir / "final_report.md"
        if not textual_report.exists() or not charts_dir.exists() or not final_report.exists():
            continue

        text = textual_report.read_text(encoding="utf-8", errors="ignore")
        specs = extract_visualization_blocks(text)
        screenshots = sorted(charts_dir.glob("html_*_screenshot.png"), key=html_index)

        chart_count = min(len(specs), len(screenshots))
        report_id = topic_dir.name
        report_entry = {
            "report_id": report_id,
            "topic": slug_to_topic(topic_dir.name),
            "system": "ours",
            "report_path": str(final_report.resolve()),
            "charts": [],
        }

        if len(specs) != len(screenshots):
            mismatches.append(
                {
                    "report_id": report_id,
                    "topic": slug_to_topic(topic_dir.name),
                    "spec_count": len(specs),
                    "screenshot_count": len(screenshots),
                    "used_count": chart_count,
                }
            )

        target_dir = extracted_specs_dir / report_id
        target_dir.mkdir(parents=True, exist_ok=True)

        for i in range(chart_count):
            spec_path = target_dir / f"chart_{i}.md"
            spec_path.write_text(specs[i] + "\n", encoding="utf-8")
            report_entry["charts"].append(
                {
                    "chart_id": f"html_{i}",
                    "spec_path": str(spec_path.resolve()),
                    "image_path": str(screenshots[i].resolve()),
                }
            )
        reports.append(report_entry)

    manifest = {
        "reports": reports,
        "meta": {
            "dataset_root": str(dataset_root.resolve()),
            "system": "ours",
            "report_count": len(reports),
            "mismatch_count": len(mismatches),
        },
    }
    return manifest, mismatches


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chart evaluation manifest for MDR reports dataset.")
    parser.add_argument("--dataset-root", required=True, help="Path to multimodal_deepresearcher_reports.")
    parser.add_argument("--output", required=True, help="Path to the output manifest JSON.")
    parser.add_argument(
        "--spec-dir",
        required=True,
        help="Directory where extracted chart design spec files will be written.",
    )
    parser.add_argument(
        "--mismatch-report",
        required=True,
        help="Path to the mismatch summary JSON.",
    )
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root).resolve()
    output = Path(args.output).resolve()
    spec_dir = Path(args.spec_dir).resolve()
    mismatch_report = Path(args.mismatch_report).resolve()

    manifest, mismatches = build_manifest(dataset_root, spec_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    mismatch_report.parent.mkdir(parents=True, exist_ok=True)
    mismatch_report.write_text(json.dumps(mismatches, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Saved manifest to {output}")
    print(f"Saved mismatch report to {mismatch_report}")
    print(f"Report count: {manifest['meta']['report_count']}")
    print(f"Mismatch count: {manifest['meta']['mismatch_count']}")


if __name__ == "__main__":
    main()
