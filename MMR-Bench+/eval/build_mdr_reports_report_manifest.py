#!/usr/bin/env python
"""Build a single-report evaluation manifest from multimodal_deepresearcher_reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def slug_to_topic(slug: str) -> str:
    topic = slug.replace("--", ": ")
    topic = topic.replace("-", " ")
    return topic


def build_manifest(dataset_root: Path) -> dict:
    reports = []
    for topic_dir in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
        report_path = topic_dir / "final_report.md"
        charts_dir = topic_dir / "html_charts"
        if not report_path.exists() or not charts_dir.exists():
            continue
        reports.append(
            {
                "report_id": topic_dir.name,
                "topic": slug_to_topic(topic_dir.name),
                "report_path": str(report_path.resolve()),
                "images_dir": str(charts_dir.resolve()),
            }
        )
    return {
        "reports": reports,
        "meta": {
            "dataset_root": str(dataset_root.resolve()),
            "report_count": len(reports),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build single-report manifest for MDR reports dataset.")
    parser.add_argument("--dataset-root", required=True, help="Path to multimodal_deepresearcher_reports.")
    parser.add_argument("--output", required=True, help="Path to the output manifest JSON.")
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root).resolve()
    output = Path(args.output).resolve()
    manifest = build_manifest(dataset_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved manifest to {output}")
    print(f"Report count: {manifest['meta']['report_count']}")


if __name__ == "__main__":
    main()
