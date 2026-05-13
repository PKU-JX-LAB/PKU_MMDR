#!/usr/bin/env python
"""Package generated report pairs into a paper-eval-ready local bundle."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Any

import requests


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}

REMOTE_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", flags=re.IGNORECASE)
HTML_IMAGE_PATTERN = re.compile(r'<img[^>]+src="(https?://[^"]+)"[^>]*>', flags=re.IGNORECASE)
HTML_RENDERER_PATTERN = re.compile(
    r'<HTMLRenderer\s+htmlFile="([^"]+)"\s*/?>',
    flags=re.IGNORECASE,
)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_text_file(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    dst.write_text(src.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")


def slugify_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return safe or "file"


def stable_short_name(value: str, *, key: str, max_base_len: int = 24) -> str:
    """Build a compact, stable file stem to avoid Windows path length issues."""
    base = slugify_name(value)
    base = base[:max_base_len].rstrip("-._") or "file"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"{base}_{digest}"


def guess_extension(url: str, content_type: str | None) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return suffix

    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    return ".png"


def download_image(url: str, destination: Path, timeout: int) -> Path:
    ensure_dir(destination.parent)
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    extension = guess_extension(url, response.headers.get("Content-Type"))
    final_path = destination.with_suffix(extension)
    final_path.write_bytes(response.content)
    return final_path


def collect_visual_sequence(report_path: Path) -> list[dict[str, str]]:
    text = report_path.read_text(encoding="utf-8", errors="ignore")
    sequence: list[tuple[int, dict[str, str]]] = []

    for match in REMOTE_IMAGE_PATTERN.finditer(text):
        sequence.append((match.start(), {"kind": "remote_image", "value": html.unescape(match.group(1))}))

    for match in HTML_IMAGE_PATTERN.finditer(text):
        sequence.append((match.start(), {"kind": "remote_image", "value": html.unescape(match.group(1))}))

    for match in HTML_RENDERER_PATTERN.finditer(text):
        sequence.append((match.start(), {"kind": "chart_renderer", "value": match.group(1)}))

    sequence.sort(key=lambda item: item[0])
    return [payload for _, payload in sequence]


def package_system(
    *,
    system_name: str,
    system_dir: Path,
    package_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    report_path = system_dir / "final_report.md"
    if not report_path.exists():
        raise FileNotFoundError(f"Missing final_report.md in {system_dir}")

    packaged_system_dir = package_dir / system_name
    packaged_images_dir = packaged_system_dir / "report_images"
    ensure_dir(packaged_images_dir)

    packaged_report_path = packaged_system_dir / "final_report.md"
    copy_text_file(report_path, packaged_report_path)

    image_paths: list[str] = []
    downloaded_remote_by_url: dict[str, Path] = {}
    copied_chart_by_source: dict[str, Path] = {}

    for index, item in enumerate(collect_visual_sequence(report_path), start=1):
        prefix = f"{index:03d}"

        if item["kind"] == "remote_image":
            url = item["value"]
            if url in downloaded_remote_by_url:
                resolved = downloaded_remote_by_url[url]
            else:
                parsed = urllib.parse.urlparse(url)
                basename = stable_short_name(
                    Path(parsed.path).stem or "remote_image",
                    key=url,
                )
                try:
                    resolved = download_image(
                        url,
                        packaged_images_dir / f"{prefix}_{basename}",
                        timeout=timeout,
                    )
                except Exception as exc:
                    print(f"Warning: failed to download remote image {url}: {exc}")
                    continue
                downloaded_remote_by_url[url] = resolved
            image_paths.append(str(resolved))
            continue

        html_file = item["value"]
        chart_html_path = system_dir / html_file
        screenshot_path = chart_html_path.with_name(f"{chart_html_path.stem}_screenshot.png")
        if not screenshot_path.exists():
            continue

        screenshot_key = str(screenshot_path.resolve())
        if screenshot_key in copied_chart_by_source:
            resolved = copied_chart_by_source[screenshot_key]
        else:
            chart_stem = stable_short_name(screenshot_path.stem, key=screenshot_key)
            resolved = packaged_images_dir / f"{prefix}_{chart_stem}{screenshot_path.suffix.lower()}"
            shutil.copy2(screenshot_path, resolved)
            copied_chart_by_source[screenshot_key] = resolved
        image_paths.append(str(resolved))

    learnings_path = system_dir / "learnings.txt"
    packaged_learnings_path = None
    if learnings_path.exists():
        packaged_learnings_path = packaged_system_dir / "learnings.txt"
        copy_text_file(learnings_path, packaged_learnings_path)

    unique_image_paths: list[str] = []
    seen = set()
    for image_path in image_paths:
        if image_path in seen:
            continue
        seen.add(image_path)
        unique_image_paths.append(image_path)

    return {
        "name": system_name,
        "report_path": str(packaged_report_path),
        "image_paths": unique_image_paths,
        "learnings_path": str(packaged_learnings_path) if packaged_learnings_path else None,
    }


def build_combined_learnings(
    package_dir: Path,
    pair_id: str,
    left_name: str,
    left_dir: Path,
    right_name: str,
    right_dir: Path,
) -> Path:
    sections: list[str] = []
    for name, system_dir in ((left_name, left_dir), (right_name, right_dir)):
        learnings_path = system_dir / "learnings.txt"
        if not learnings_path.exists():
            continue
        content = learnings_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            continue
        sections.append(f"## {name}\n\n{content}")

    combined_path = package_dir / pair_id / "learnings.md"
    ensure_dir(combined_path.parent)
    combined_path.write_text("\n\n".join(sections).strip() + "\n", encoding="utf-8")
    return combined_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Package a generated report pair for paper_eval.py report mode.")
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--left-name", required=True)
    parser.add_argument("--left-dir", required=True)
    parser.add_argument("--right-name", required=True)
    parser.add_argument("--right-dir", required=True)
    parser.add_argument("--output-dir", required=True, help="Directory where packaged pair assets are written.")
    parser.add_argument("--manifest-output", required=True, help="Path to save the generated report manifest JSON.")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds for remote image downloads.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    pair_dir = output_dir / args.pair_id
    ensure_dir(pair_dir)

    left_dir = Path(args.left_dir).resolve()
    right_dir = Path(args.right_dir).resolve()

    left_payload = package_system(
        system_name=args.left_name,
        system_dir=left_dir,
        package_dir=pair_dir,
        timeout=args.timeout,
    )
    right_payload = package_system(
        system_name=args.right_name,
        system_dir=right_dir,
        package_dir=pair_dir,
        timeout=args.timeout,
    )

    combined_learnings_path = build_combined_learnings(
        output_dir,
        args.pair_id,
        args.left_name,
        left_dir,
        args.right_name,
        right_dir,
    )

    manifest = {
        "pairs": [
            {
                "pair_id": args.pair_id,
                "topic": args.topic,
                "learnings_path": str(combined_learnings_path),
                "systems": [
                    {
                        "name": left_payload["name"],
                        "report_path": left_payload["report_path"],
                        "image_paths": left_payload["image_paths"],
                    },
                    {
                        "name": right_payload["name"],
                        "report_path": right_payload["report_path"],
                        "image_paths": right_payload["image_paths"],
                    },
                ],
            }
        ]
    }

    manifest_path = Path(args.manifest_output).resolve()
    ensure_dir(manifest_path.parent)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved packaged pair assets to {pair_dir}")
    print(f"Saved manifest to {manifest_path}")


if __name__ == "__main__":
    main()
