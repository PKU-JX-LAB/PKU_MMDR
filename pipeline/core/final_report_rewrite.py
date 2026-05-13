from __future__ import annotations

import json
import re
from pathlib import Path

from .config import FINAL_REPORT_POLISH_MAX_TOKENS, FINAL_REPORT_POLISH_MODEL
from .llm_utils import chat_with_model


REWRITE_SYSTEM_PROMPT = """You are an expert research report rewriter.
Your job is to rewrite an existing markdown report into a clearer, better-organized, and better-supported research report.
Goals:
1. Improve the report's structure, expression, and analytical presentation, enhancing its overall readability and organizational quality.
2. Improve how key content is supported and how precisely it is stated, making the report more rigorous, more credible, and easier to verify.


This is a strong whole-report rewrite, not a light polish. You may reorganize structure,
merge sections, delete low-value material, rewrite arguments, and improve analytical flow.

Important rules:
- Use only information already present in the current report, the supplied learnings, and the media inventory.
- Do not invent new facts, new data, new sources, or new claims.
- Keep the report in its original main language.
- Every [[MEDIA_ANCHOR_xxx]] token must be preserved exactly once in the output. You may move it, but you must not delete, rename, or duplicate it.
- Keep relevant links, source names, citations, footnote-style references, and media anchors.
- Preserve the report's substantive coverage breadth unless material is clearly redundant or irrelevant.
- Do not solve verifiability by aggressively narrowing scope, dropping major methods, or removing important comparisons that the original report already covered.
- If the original report meaningfully covers multiple systems, variants, periods, regions, or mechanisms, retain that breadth and make it clearer rather than collapsing it.
- Compression is allowed only for redundancy, filler, weak background, placeholders, editorial scaffolding, or unsupported overclaiming. Do not compress away useful content.
- You may absorb already-existing facts, numbers, comparisons, and source anchors from the learnings when they improve the report.
- Make the report read like a stronger research document: more complete, more analytical, more balanced, and easier to verify.
- For important quantitative claims, method comparisons, mechanism explanations, and empirical judgments, place a source anchor nearby in the prose whenever the supplied material supports it.
- Prefer claim-local traceability over reference-list-only traceability: readers should not have to scan far away from a key claim to find its support.
- If a paragraph contains several distinct claims, break it into shorter units or distribute source anchors so each major claim remains auditable.
- Keep source support readable and publication-like: integrate citations naturally into sentences or paragraph endings rather than emitting repeated standalone `Source:` / `Sources:` note lines.
- Do not delete valid supporting links merely for style. If a standalone source-note line is removed, move its supporting link(s) into the relevant sentence or the end of the same paragraph instead.
- Avoid repeating the same URL many times across adjacent sentences when one nearby citation is sufficient for the surrounding claim.
- During rewriting, use normal markdown links or source naming where helpful; final numbered citation formatting will be handled downstream.
- Replace vague source-free phrasing such as "materials indicate", "studies show", "it is reported", or "the literature suggests" with more explicit source naming and nearby support whenever the supplied material allows it.
- If a claim is only partially supported, rewrite it more narrowly or attach a caveat rather than leaving a strong but weakly anchored statement.
- Remove clearly irrelevant, malformed, or unused links when they reduce traceability, but keep relevant links and citations.
- If the available material does not fully support a strong claim, rewrite it more cautiously, but keep any still-useful comparison or interpretation that can be stated with proper caveats.
- Prefer preserving or modestly increasing substantive depth over making the report shorter.
- Return only the final rewritten markdown.
"""


REWRITE_USER_PROMPT = """Rewrite the following report into a stronger research report.

Primary goals:
- Make the report clearer, better structured, and easier to follow
- Make the report more precise and easier to verify

What to optimize for:
- Answer the topic more directly and more completely
- Preserve the original report's real coverage breadth while improving clarity and analytical strength
- Remove repetition, filler, weak background, off-topic content, and unfinished sections
- Keep and strengthen the most valuable technical detail, comparisons, numbers, and conclusions
- Turn material stacking into clearer analysis, synthesis, comparison, and explanation
- Increase information density without making the report bloated
- Strengthen mechanism explanations, boundary conditions, applicability, and section-level takeaways
- Make important claims, important numbers, important comparisons, and key judgments easier for a reader to verify
- Improve verifiability without sacrificing major methods, cases, or comparisons that matter for answering the topic
- Move supporting links and source naming closer to the claims they justify, especially for numbers, rankings, benchmarks, method differences, and causal or empirical conclusions
- Prefer several well-placed local citations over one citation cluster that loosely covers an entire long paragraph
- Keep citations readable in the prose: avoid standalone `Source:` / `Sources:` lines when the support can be integrated naturally into the sentence or paragraph
- Do not drop valid supporting links. When removing a standalone source-note line, preserve its link(s) by moving them into the associated sentence or paragraph-end citation.
- Avoid repeating the same URL across nearby sentences when one local citation is enough for the immediately surrounding claim
- Do not worry about final `[1]`-style numbering; downstream post-processing will normalize citation format
- Prune clearly irrelevant or malformed links that do not help a reader verify the surrounding text
- Rewrite unsupported generalizations into narrower, source-bounded statements instead of leaving them broad

You may:
- Reorganize the article structure
- Rename and reorder sections
- Merge or delete paragraphs
- Rewrite transitions and local argument structure
- Pull in already-existing material from the learnings

Hard requirements:
- Do not add any fact, data point, source, or claim that is not already supported by the supplied report or learnings
- Keep all images, markdown image tags, original-image references, and <HTMLRenderer ... /> tags by preserving every [[MEDIA_ANCHOR_xxx]] exactly once
- Keep the report in the same main language as the input

Additional rewrite guidance:
- Retain all major methods, variants, systems, entities, and comparisons that the original report already treated as important unless they are clearly redundant.
- If the topic implicitly or explicitly asks for a fixed set of items, preserve that coverage and make the comparison cleaner rather than shorter.
- Do not replace detailed comparative coverage with a shorter high-level summary.
- If you need to improve verifiability, prefer adding caveats, source anchoring, or more precise wording over deleting substantive content.
- Do not leave long analytical paragraphs with only a distant end-of-paragraph citation when the paragraph contains multiple distinct claims.
- When a figure, table, or original image supports a claim, make the surrounding prose say so explicitly and keep the source traceable nearby.
- Aim for a final report that is roughly comparable in substantive scope to the original, unless the original contains obvious low-value padding.

Please output only the rewritten markdown report.

## Topic
{topic_hint}

## Media Inventory
{media_inventory}

## Learnings
{learnings_text}

## Current Report
{report_with_anchors}
"""


ANCHOR_REPAIR_SYSTEM_PROMPT = """You are a strict markdown repair assistant.
Repair only media-anchor problems in the rewritten report.

Rules:
- Every [[MEDIA_ANCHOR_xxx]] token must appear exactly once.
- Do not delete any valid media anchor.
- Do not invent new facts.
- Make the smallest possible textual changes.
- Return only the repaired full markdown report.
"""


ANCHOR_REPAIR_USER_PROMPT = """The rewritten report below does not preserve media anchors correctly.

Problems to fix:
- Missing anchors: {missing}
- Duplicate anchors: {duplicates}

Valid anchor set:
{all_anchors}

Please minimally repair the report and return the full corrected markdown.

## Broken Report
{broken_report}
"""


COMBINED_MEDIA_PATTERN = re.compile(r"(<HTMLRenderer\b[^>]*\/>)|(!\[[^\]]*\]\([^)]+\))", re.IGNORECASE)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return head + "\n\n[... trimmed for length ...]\n\n" + tail


def _strip_code_fences(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped
    match = re.match(r"^```[a-zA-Z0-9_-]*\n([\s\S]*?)\n```$", stripped)
    if match:
        return match.group(1).strip()
    parts = stripped.split("```")
    if len(parts) >= 3:
        return parts[1].strip()
    return stripped


def _normalize_output(text: str) -> str:
    normalized = _strip_code_fences(text)
    normalized = re.sub(r"(?is)\A#\s*(?:rewritten|polished)\s+report\s*\n+", "", normalized).strip()
    return normalized


def _extract_media_info(raw_media: str, image_refs_by_url: dict[str, dict]) -> str:
    html_match = re.search(r'htmlFile="([^"]+)"', raw_media)
    if html_match:
        return f"generated visualization from {html_match.group(1)}"

    md_match = re.search(r"!\[[^\]]*\]\(([^)]+)\)", raw_media)
    if not md_match:
        return "media anchor"

    url = md_match.group(1)
    ref = image_refs_by_url.get(url)
    if not ref:
        return f"image url={url}"

    page_title = ref.get("page_title", "").strip()
    page_url = ref.get("page_url", "").strip()
    source_kind = ref.get("source_kind", "").strip()
    parts = []
    if page_title:
        parts.append(page_title)
    if page_url:
        parts.append(page_url)
    if source_kind:
        parts.append(f"source_kind={source_kind}")
    return " | ".join(parts) if parts else f"image url={url}"


def _protect_media(report_text: str, output_dir: Path):
    image_refs = _load_json(output_dir / "image_references.json", default=[])
    image_refs_by_url = {}
    for item in image_refs:
        url = item.get("url")
        if url and url not in image_refs_by_url:
            image_refs_by_url[url] = item

    anchors = []
    rebuilt = []
    cursor = 0
    for idx, match in enumerate(COMBINED_MEDIA_PATTERN.finditer(report_text), start=1):
        rebuilt.append(report_text[cursor:match.start()])
        token = f"[[MEDIA_ANCHOR_{idx:03d}]]"
        raw_media = match.group(0)
        rebuilt.append(token)
        anchors.append(
            {
                "token": token,
                "raw_media": raw_media,
                "info": _extract_media_info(raw_media, image_refs_by_url),
            }
        )
        cursor = match.end()
    rebuilt.append(report_text[cursor:])
    return "".join(rebuilt), anchors


def _restore_media(report_text: str, anchors: list[dict]) -> str:
    restored = report_text
    for item in anchors:
        restored = restored.replace(item["token"], item["raw_media"])
    return restored


def _summarize_media_inventory(anchors: list[dict]) -> str:
    if not anchors:
        return "No media anchors detected."
    return "\n".join(f"- {item['token']}: {item['info']}" for item in anchors)


def _validate_anchor_counts(text: str, anchors: list[dict]):
    missing = []
    duplicates = []
    for item in anchors:
        count = text.count(item["token"])
        if count == 0:
            missing.append(item["token"])
        elif count > 1:
            duplicates.append(item["token"])
    return missing, duplicates


def rewrite_report_content(
    report_content: str,
    output_dir: str | Path,
    topic_hint: str,
    model: str | None = None,
    max_tokens: int | None = None,
    max_report_chars: int = 90000,
    max_learnings_chars: int = 45000,
) -> str:
    output_dir = Path(output_dir)
    learnings_path = output_dir / "learnings.txt"
    learnings_text = learnings_path.read_text(encoding="utf-8") if learnings_path.exists() else ""

    protected_report, anchors = _protect_media(report_content, output_dir)
    media_inventory = _summarize_media_inventory(anchors)
    model = model or FINAL_REPORT_POLISH_MODEL
    max_tokens = max_tokens or FINAL_REPORT_POLISH_MAX_TOKENS

    rewritten = chat_with_model(
        model,
        REWRITE_SYSTEM_PROMPT,
        REWRITE_USER_PROMPT.format(
            topic_hint=topic_hint,
            media_inventory=media_inventory,
            learnings_text=_shorten(learnings_text, max_learnings_chars),
            report_with_anchors=_shorten(protected_report, max_report_chars),
        ),
        max_tokens=max_tokens,
    )
    rewritten = _normalize_output(rewritten)

    if not rewritten:
        return report_content

    missing, duplicates = _validate_anchor_counts(rewritten, anchors)
    if missing or duplicates:
        repaired = chat_with_model(
            model,
            ANCHOR_REPAIR_SYSTEM_PROMPT,
            ANCHOR_REPAIR_USER_PROMPT.format(
                missing=", ".join(missing) if missing else "None",
                duplicates=", ".join(duplicates) if duplicates else "None",
                all_anchors=", ".join(item["token"] for item in anchors) if anchors else "None",
                broken_report=rewritten,
            ),
            max_tokens=max_tokens,
        )
        rewritten = _normalize_output(repaired)
        missing, duplicates = _validate_anchor_counts(rewritten, anchors)

    if missing or duplicates:
        raise RuntimeError(
            f"Media anchor validation failed. Missing={missing}, duplicates={duplicates}"
        )

    restored = _restore_media(rewritten, anchors)
    restored = re.sub(r"\n{3,}", "\n\n", restored).strip() + "\n"
    return restored
