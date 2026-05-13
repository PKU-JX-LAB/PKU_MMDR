import os
import re
from urllib.parse import urlparse, parse_qsl

from .artifact_utils import save_json
from .image_vision_metadata import enrich_with_vision_metadata


FIGURE_TYPE_KEYWORDS = {
    "algorithm_diagram": {"algorithm", "pseudocode", "schematic"},
    "pipeline": {"pipeline", "workflow", "flow", "framework", "architecture"},
    "result_chart": {"result", "benchmark", "performance", "curve", "plot", "chart"},
    "ablation_table": {"ablation", "table"},
    "qualitative_example": {"example", "case", "sample", "qualitative"},
}


def _normalize_tokens(value):
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", value or "").lower()
    return {token for token in cleaned.split() if len(token) > 2}


def _infer_figure_type(tokens):
    best_type = "unknown"
    best_score = 0
    for figure_type, keywords in FIGURE_TYPE_KEYWORDS.items():
        score = len(tokens & keywords)
        if score > best_score:
            best_type = figure_type
            best_score = score
    return best_type


def _normalize_url(url):
    parsed = urlparse(url)
    filtered_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith(("utm_", "ref", "source"))]
    normalized_path = re.sub(r"/+", "/", parsed.path or "")
    query_part = "&".join(f"{k}={v}" for k, v in filtered_query)
    return f"{parsed.netloc.lower()}{normalized_path}?{query_part}".rstrip("?")


def _build_dedup_key(url, filename):
    normalized_url = _normalize_url(url)
    filename_key = re.sub(r"[^a-zA-Z0-9]+", "", (filename or "").lower())
    if filename_key:
        return f"{normalized_url}|{filename_key}"
    return normalized_url


def build_image_metadata(image_pool, output_dir, topic="", pipeline_config=None, image_references=None):
    pipeline_config = pipeline_config or {}
    references_by_id = {
        item.get("image_id"): item for item in (image_references or []) if item.get("image_id")
    }
    metadata = []
    for image_id, url in image_pool.items():
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        source_domain = parsed.netloc.lower()
        tokens = _normalize_tokens(url)
        reference = references_by_id.get(image_id, {})
        alt_text = reference.get("alt_text", "")
        page_title = reference.get("page_title", "")
        surrounding_text = reference.get("surrounding_text", "")
        tokens |= _normalize_tokens(alt_text)
        tokens |= _normalize_tokens(page_title)
        tokens |= _normalize_tokens(surrounding_text)
        source_title = filename or image_id
        summary = f"Image from {source_domain} with filename hint `{filename}`."
        if alt_text:
            summary += f" Alt text: {alt_text}."
        if surrounding_text:
            summary += f" Nearby context: {surrounding_text[:220]}."
        normalized_url = _normalize_url(url)
        metadata.append(
            {
                "image_id": image_id,
                "url": url,
                "normalized_url": normalized_url,
                "source_domain": source_domain,
                "source_title": source_title,
                "caption": filename,
                "alt_text": alt_text,
                "page_title": page_title,
                "page_url": reference.get("page_url", ""),
                "query": reference.get("query", ""),
                "context_before": reference.get("context_before", ""),
                "context_after": reference.get("context_after", ""),
                "surrounding_text": surrounding_text,
                "summary": summary,
                "keywords": sorted(tokens),
                "figure_type": _infer_figure_type(tokens),
                "dedup_key": _build_dedup_key(url, filename),
                "credibility_score": 0.9 if any(
                    domain in source_domain for domain in ("arxiv.org", "openreview.net", "acm.org", "ieee.org")
                ) else 0.6,
            }
        )
    save_json(os.path.join(output_dir, "image_metadata_base.json"), metadata)
    if pipeline_config.get("enable_vision_metadata"):
        metadata = enrich_with_vision_metadata(
            topic,
            metadata,
            output_dir,
            max_images=pipeline_config.get("max_vision_metadata_images", 6),
        )
        for item in metadata:
            vision_keywords = item.get("vision_keywords", [])
            if vision_keywords:
                merged = sorted(set(item.get("keywords", [])) | set(vision_keywords))
                item["keywords"] = merged
            if item.get("vision_summary"):
                item["summary"] = item["vision_summary"]
            if item.get("vision_figure_type") and item.get("vision_figure_type") != "unknown":
                item["figure_type"] = item["vision_figure_type"]
    metadata_path = os.path.join(output_dir, "image_metadata.json")
    save_json(metadata_path, metadata)
    return metadata
