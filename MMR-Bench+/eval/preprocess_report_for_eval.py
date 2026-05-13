#!/usr/bin/env python
"""Preprocess a markdown report into an evaluation-ready artifact.

Features:
- remove configured sections from the final report while optionally exporting them
- render fenced Mermaid blocks into PNGs
- replace Mermaid source blocks with markdown image links
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import requests


MERMAID_BLOCK_RE = re.compile(
    r"```mermaid[ \t]*\r?\n(?P<code>.*?)\r?\n```",
    flags=re.IGNORECASE | re.DOTALL,
)
GENERIC_CODE_BLOCK_RE = re.compile(
    r"```[^\n\r`]*\r?\n(?P<code>.*?)\r?\n```",
    flags=re.DOTALL,
)
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})[ \t]+(?P<title>.+?)\s*$", flags=re.MULTILINE)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def remove_sections(markdown: str, section_titles: Iterable[str]) -> tuple[str, list[tuple[str, str]]]:
    wanted = {normalize_heading(title) for title in section_titles if title.strip()}
    if not wanted:
        return markdown, []

    matches = list(HEADING_RE.finditer(markdown))
    removed: list[tuple[str, str]] = []
    kept_parts: list[str] = []
    cursor = 0

    for index, match in enumerate(matches):
        title = match.group("title").strip()
        normalized_title = normalize_heading(title)
        if normalized_title not in wanted:
            continue

        kept_parts.append(markdown[cursor:match.start()])
        level = len(match.group("hashes"))
        end = len(markdown)
        for later in matches[index + 1 :]:
            later_level = len(later.group("hashes"))
            if later_level <= level:
                end = later.start()
                break
        removed.append((title, markdown[match.start():end].strip()))
        cursor = end

    kept_parts.append(markdown[cursor:])
    updated = "".join(kept_parts)
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip() + "\n"
    return updated, removed


def render_mermaid_png(
    mermaid_code: str,
    destination: Path,
    *,
    kroki_base_url: str,
    timeout: int,
) -> None:
    ensure_parent(destination)
    response = requests.post(
        f"{kroki_base_url.rstrip('/')}/mermaid/png",
        data=mermaid_code.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        timeout=timeout,
    )
    response.raise_for_status()
    destination.write_bytes(response.content)


def replace_mermaid_blocks(
    markdown: str,
    *,
    assets_dir: Path,
    output_report: Path,
    kroki_base_url: str,
    timeout: int,
) -> tuple[str, list[Path]]:
    rendered_paths: list[Path] = []
    assets_dir.mkdir(parents=True, exist_ok=True)

    def _replace(match: re.Match[str]) -> str:
        index = len(rendered_paths) + 1
        image_path = assets_dir / f"mermaid_{index:02d}.png"
        render_mermaid_png(
            match.group("code").strip() + "\n",
            image_path,
            kroki_base_url=kroki_base_url,
            timeout=timeout,
        )
        rendered_paths.append(image_path)
        relative = image_path.relative_to(output_report.parent)
        alt_text = f"mermaid diagram {index}"
        return f"![{alt_text}]({relative.as_posix()})"

    updated = MERMAID_BLOCK_RE.sub(_replace, markdown)
    return updated, rendered_paths


def build_learnings_text(removed_sections: list[tuple[str, str]]) -> str:
    if not removed_sections:
        return ""
    return "\n\n".join(section for _, section in removed_sections).strip() + "\n"


def unwrap_generic_code_blocks(markdown: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        code = match.group("code").strip("\n")
        if not code.strip():
            return ""
        return f"\n{code}\n"

    updated = GENERIC_CODE_BLOCK_RE.sub(_replace, markdown)
    return re.sub(r"\n{3,}", "\n\n", updated).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess a markdown report before evaluation.")
    parser.add_argument("--input-report", required=True, help="Path to the source markdown report.")
    parser.add_argument("--output-report", required=True, help="Path to the evaluation-ready markdown report.")
    parser.add_argument(
        "--assets-dir",
        required=True,
        help="Directory where rendered mermaid images will be saved.",
    )
    parser.add_argument(
        "--remove-section",
        action="append",
        default=[],
        help="Section heading to remove from the final report. Repeatable.",
    )
    parser.add_argument(
        "--learnings-output",
        default=None,
        help="Optional path to save the removed sections, e.g. as learnings.txt.",
    )
    parser.add_argument(
        "--kroki-base-url",
        default="https://kroki.io",
        help="Base URL for Kroki Mermaid rendering.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="HTTP timeout in seconds for each Mermaid render request.",
    )
    parser.add_argument(
        "--unwrap-code-fences",
        action="store_true",
        help="Replace remaining fenced code blocks with their plain-text contents.",
    )
    args = parser.parse_args()

    input_report = Path(args.input_report).resolve()
    output_report = Path(args.output_report).resolve()
    assets_dir = Path(args.assets_dir).resolve()
    learnings_output = Path(args.learnings_output).resolve() if args.learnings_output else None

    markdown = input_report.read_text(encoding="utf-8")
    markdown, removed_sections = remove_sections(markdown, args.remove_section)
    markdown, rendered_paths = replace_mermaid_blocks(
        markdown,
        assets_dir=assets_dir,
        output_report=output_report,
        kroki_base_url=args.kroki_base_url,
        timeout=args.timeout,
    )
    if args.unwrap_code_fences:
        markdown = unwrap_generic_code_blocks(markdown)

    ensure_parent(output_report)
    output_report.write_text(markdown, encoding="utf-8")

    if learnings_output is not None:
        ensure_parent(learnings_output)
        learnings_output.write_text(build_learnings_text(removed_sections), encoding="utf-8")

    print(f"Saved preprocessed report to {output_report}")
    print(f"Rendered mermaid images: {len(rendered_paths)}")
    if learnings_output is not None:
        print(f"Saved removed sections to {learnings_output}")


if __name__ == "__main__":
    main()
