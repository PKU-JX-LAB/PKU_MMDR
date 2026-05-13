import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from .artifact_utils import load_json, save_json
from .config import VISION_METADATA_MLLM_MODEL
from .llm_utils import chat_with_image


VISION_SYSTEM_PROMPT = """You are an expert at understanding technical figures from papers and research webpages.
Return concise structured metadata about what the figure visually shows and what role it could play in a report."""

VISION_USER_PROMPT = """Analyze this image for a report about:
{topic}

Return plain text with exactly these fields:
summary: one sentence describing the visible content
figure_type: one of algorithm_diagram, pipeline, result_chart, ablation_table, qualitative_example, unknown
visual_keywords: comma-separated keywords grounded in visible content
evidence_role: one short phrase describing what claim this figure could support

Be conservative. If the image is not clearly technical or relevant, say so."""


def _score_candidate_for_vision(topic, item):
    topic_tokens = {t for t in re.findall(r"[a-zA-Z0-9]{3,}", (topic or "").lower())}
    keywords = set(item.get("keywords", []))
    score = len(topic_tokens & keywords) + item.get("credibility_score", 0)
    if item.get("figure_type") in {"algorithm_diagram", "pipeline", "result_chart", "ablation_table"}:
        score += 0.5
    return score


def _download_image(url, destination):
    ssl_ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as response:
        data = response.read()
    if len(data) < 2048:
        raise ValueError("downloaded image too small")
    destination.write_bytes(data)


def _parse_vision_response(text):
    result = {
        "vision_summary": "",
        "vision_figure_type": "unknown",
        "vision_keywords": [],
        "evidence_role": "",
    }
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "summary":
            result["vision_summary"] = value
        elif key == "figure_type":
            result["vision_figure_type"] = value or "unknown"
        elif key == "visual_keywords":
            result["vision_keywords"] = [token.strip() for token in value.split(",") if token.strip()]
        elif key == "evidence_role":
            result["evidence_role"] = value
    return result


def enrich_with_vision_metadata(topic, metadata, output_dir, max_images=6):
    if not metadata:
        return metadata

    cache_path = os.path.join(output_dir, "vision_metadata_cache.json")
    cache = load_json(cache_path, default={})
    temp_dir = Path(output_dir) / "vision_metadata_images"
    temp_dir.mkdir(parents=True, exist_ok=True)

    ranked = sorted(
        metadata,
        key=lambda item: _score_candidate_for_vision(topic, item),
        reverse=True,
    )
    selected = ranked[:max_images]

    for item in selected:
        dedup_key = item.get("dedup_key", item["image_id"])
        if dedup_key in cache:
            item.update(cache[dedup_key])
            continue

        ext = ".png"
        lower_url = item["url"].lower()
        if ".jpg" in lower_url or ".jpeg" in lower_url:
            ext = ".jpg"
        local_path = temp_dir / f"{hashlib.md5(dedup_key.encode()).hexdigest()[:12]}{ext}"
        try:
            _download_image(item["url"], local_path)
            response = chat_with_image(
                VISION_METADATA_MLLM_MODEL,
                VISION_SYSTEM_PROMPT,
                VISION_USER_PROMPT.format(topic=topic),
                str(local_path),
                max_tokens=300,
            )
            parsed = _parse_vision_response(response)
        except (urllib.error.URLError, ValueError, OSError):
            parsed = {
                "vision_summary": "",
                "vision_figure_type": "unknown",
                "vision_keywords": [],
                "evidence_role": "",
            }
        cache[dedup_key] = parsed
        item.update(parsed)

    save_json(cache_path, cache)
    save_json(os.path.join(output_dir, "vision_metadata_preview.json"), selected)
    return metadata
