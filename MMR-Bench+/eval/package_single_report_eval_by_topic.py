#!/usr/bin/env python
"""Package single-report evaluation outputs into per-topic folders."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def copy_file_if_exists(source: Path | None, target: Path) -> bool:
    if source is None or not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(to_system_path(source), to_system_path(target))
    return True


def to_system_path(path: Path) -> str:
    value = str(path.resolve())
    if os.name != "nt":
        return value
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value.lstrip("\\")
    return "\\\\?\\" + value


def build_packaged_source_name(index: int, source_record: dict[str, Any]) -> str:
    cache_path_value = source_record.get("cache_path", "")
    cache_name = Path(cache_path_value).name
    stem = Path(cache_name).stem
    short_stem = stem[:24].rstrip("._-") or f"source_{index:02d}"
    digest_source = source_record.get("original_url") or cache_path_value or str(index)
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:10]
    return f"{index:02d}_{short_stem}_{digest}.txt"


def package_source_records(
    source_records: list[dict[str, Any]],
    target_dir: Path,
) -> list[dict[str, Any]]:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    packaged_records: list[dict[str, Any]] = []
    for index, source_record in enumerate(source_records, start=1):
        cache_path_value = source_record.get("cache_path")
        if not cache_path_value:
            continue
        source_path = Path(cache_path_value).resolve()
        if not source_path.exists():
            continue
        packaged_name = build_packaged_source_name(index, source_record)
        packaged_path = target_dir / packaged_name
        shutil.copy2(to_system_path(source_path), to_system_path(packaged_path))
        packaged_records.append(
            {
                "original_url": source_record.get("original_url"),
                "resolved_url": source_record.get("resolved_url"),
                "original_cache_path": str(source_path),
                "packaged_path": str(packaged_path),
            }
        )
    return packaged_records


def build_topic_summary(
    report_result: dict[str, Any],
    fetch_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    scores = {
        metric: payload["score"]
        for metric, payload in report_result.get("scores", {}).items()
    }
    summary = {
        "report_id": report_result["report_id"],
        "topic": report_result["topic"],
        "overall_score": report_result.get("overall_score"),
        "metric_scores": scores,
        "artifact_paths": report_result.get("artifact_paths", {}),
    }
    if fetch_meta:
        summary["learnings_fetch"] = {
            "link_count": fetch_meta.get("link_count", 0),
            "fetched_count": fetch_meta.get("fetched_count", 0),
            "failure_count": fetch_meta.get("failure_count", 0),
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package single-report evaluation outputs into per-topic folders."
    )
    parser.add_argument("--eval-json", required=True, help="Path to report_single_eval JSON.")
    parser.add_argument(
        "--fetch-meta-json",
        default=None,
        help="Optional path to generated learnings metadata JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where per-topic folders will be written.",
    )
    args = parser.parse_args()

    eval_path = Path(args.eval_json).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_payload = load_json(eval_path)
    report_results = eval_payload.get("report_results", [])
    if not report_results:
        raise ValueError("Evaluation JSON does not contain `report_results`.")

    fetch_meta_by_id: dict[str, dict[str, Any]] = {}
    if args.fetch_meta_json:
        fetch_meta_payload = load_json(Path(args.fetch_meta_json).resolve())
        fetch_meta_by_id = {
            item["report_id"]: item
            for item in fetch_meta_payload
            if isinstance(item, dict) and item.get("report_id")
        }

    index_entries: list[dict[str, Any]] = []
    for report_result in report_results:
        report_id = report_result["report_id"]
        topic_dir = output_dir / report_id
        topic_dir.mkdir(parents=True, exist_ok=True)

        fetch_meta = fetch_meta_by_id.get(report_id)
        summary = build_topic_summary(report_result, fetch_meta)

        save_json(topic_dir / "summary.json", summary)
        save_json(topic_dir / "report_single_eval.json", report_result)
        if fetch_meta:
            save_json(topic_dir / "learnings_fetch_meta.json", fetch_meta)

        artifact_paths = report_result.get("artifact_paths", {})
        learnings_path_value = artifact_paths.get("learnings_path")
        learnings_path = Path(learnings_path_value).resolve() if learnings_path_value else None
        copied_learnings = copy_file_if_exists(learnings_path, topic_dir / "learnings.md")

        packaged_source_records: list[dict[str, Any]] = []
        if fetch_meta and fetch_meta.get("source_records"):
            packaged_source_records = package_source_records(
                fetch_meta["source_records"],
                topic_dir / "fetched_sources",
            )
            save_json(topic_dir / "fetched_sources_index.json", packaged_source_records)

        index_entries.append(
            {
                "report_id": report_id,
                "topic": report_result["topic"],
                "topic_dir": str(topic_dir),
                "overall_score": report_result.get("overall_score"),
                "metric_scores": summary["metric_scores"],
                "copied_learnings": copied_learnings,
                "copied_fetched_source_files": len(packaged_source_records),
            }
        )

    save_json(
        output_dir / "index.json",
        {
            "source_eval_json": str(eval_path),
            "source_fetch_meta_json": str(Path(args.fetch_meta_json).resolve())
            if args.fetch_meta_json
            else None,
            "report_count": len(index_entries),
            "reports": index_entries,
        },
    )
    print(f"Saved per-topic evaluation package to {output_dir}")
    print(f"Report count: {len(index_entries)}")


if __name__ == "__main__":
    main()
