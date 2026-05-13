import hashlib
import http.client
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from .artifact_utils import ensure_dir, save_json, save_text
from .config import RESEARCH_LLM_MODEL, VISION_METADATA_MLLM_MODEL
from .llm_utils import chat_with_image, chat_with_model


IMAGE_STAGE_DIRNAME = "image_pipeline"

CONTEXT_CLASSIFIER_SYSTEM_PROMPT = """You are an expert image-reference triage assistant for research reports.
You classify image references only from metadata and nearby webpage context.
Be conservative, remove decorative/noisy images, and return strict JSON."""

TOPIC_RANKER_SYSTEM_PROMPT = """You are an expert research assistant selecting source images for a report topic.
Use the topic and learnings to decide which candidate images are worth keeping.
Return strict JSON only."""

OCR_SYSTEM_PROMPT = """You are an OCR and technical-figure understanding assistant.
Read visible text from the figure and extract structured visual evidence.
Return plain text with exactly these fields:
visible_title: ...
visible_text: ...
ocr_keywords: keyword1, keyword2, ...
ocr_summary: one sentence
deductive_evidence_atoms: Extract 3-5 key evidence atoms. For each atom, provide [Visual Feature] -> [Deductive Fact] -> [Rationale].
"""

FINAL_SELECTOR_SYSTEM_PROMPT = """You are selecting the final source images for a research report.
Use topic, learnings, metadata, and OCR-derived evidence.
Prefer representative, trustworthy, directly relevant figures.
Return strict JSON only."""


def _tokenize(value):
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", " ", value or "").lower()
    return [token for token in cleaned.split() if len(token) > 1]


def _trim_text(text, limit):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ..."


def _stage_dir(output_dir):
    path = Path(output_dir) / IMAGE_STAGE_DIRNAME
    ensure_dir(path)
    return path


def _safe_json_loads(text, fallback):
    raw = (text or "").strip()
    if not raw:
        return fallback
    candidates = [raw]
    for opener, closer in (("[", "]"), ("{", "}")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidates.append(raw[start:end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return fallback


def _batch_items(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


def _download_image(url, destination, max_attempts=3):
    ssl_ctx = ssl._create_unverified_context()
    last_error = None

    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as response:
                data = response.read()
            if len(data) < 2048:
                raise ValueError("downloaded image too small")
            destination.write_bytes(data)
            return
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ssl.SSLError,
            http.client.HTTPException,
            ValueError,
        ) as exc:
            last_error = exc
            if destination.exists():
                destination.unlink(missing_ok=True)
            if attempt < max_attempts:
                time.sleep(attempt)

    raise last_error


def _format_candidate(candidate):
    return {
        "image_id": candidate.get("image_id"),
        "url": candidate.get("url"),
        "source_domain": candidate.get("source_domain"),
        "page_title": _trim_text(candidate.get("page_title", ""), 180),
        "alt_text": _trim_text(candidate.get("alt_text", ""), 180),
        "surrounding_text": _trim_text(candidate.get("surrounding_text", ""), 260),
        "summary": _trim_text(candidate.get("summary", ""), 220),
        "figure_type_hint": candidate.get("figure_type", "unknown"),
        "credibility_score": candidate.get("credibility_score", 0),
    }


def _heuristic_prune(metadata):
    kept = []
    pruned = []
    for item in metadata:
        url_text = (item.get("url", "") or "").lower()
        alt_text = (item.get("alt_text", "") or "").lower()
        surrounding_text = (item.get("surrounding_text", "") or "").lower()
        page_title = (item.get("page_title", "") or "").lower()

        asset_signals = [
            "logo", "avatar", "profile", "social", "button", "emoji",
            "reaction", "thumbnail", "wechat", "twitter", "facebook",
            "linkedin", "icon", "favicon",
        ]
        technical_signals = [
            "figure", "algorithm", "pipeline", "workflow", "chart", "table",
            "benchmark", "experiment", "ablation", "equation", "训练", "流程",
            "算法", "实验", "结果", "图", "表",
        ]

        asset_hits = 0
        for signal in asset_signals:
            if signal in url_text:
                asset_hits += 1
            if signal in alt_text:
                asset_hits += 1
            if signal in page_title:
                asset_hits += 1

        has_technical_context = any(
            signal in surrounding_text or signal in alt_text or signal in page_title
            for signal in technical_signals
        )
        is_very_small_asset = any(token in url_text for token in ("sprite", "toolbar", "header", "footer"))

        if (asset_hits >= 2 and not has_technical_context) or (is_very_small_asset and not has_technical_context):
            pruned.append(
                {
                    "image_id": item["image_id"],
                    "reason": "heuristic_site_asset",
                    "asset_hits": asset_hits,
                }
            )
            continue
        kept.append(item)
    return kept, pruned


def _run_context_classifier(candidates, stage_dir, batch_size):
    parsed_all = []
    raw_batches = []
    prompt_template = """Classify the following image candidates from nearby webpage context only.
Return a JSON array. Each item must be:
{{
  "image_id": "...",
  "keep": true,
  "figure_type": "algorithm_diagram|pipeline|result_chart|ablation_table|equation|paper_figure|qualitative_example|title_page|decorative_or_noise|unknown",
  "is_original_source_likely": true,
  "context_score": 0-5,
  "context_summary": "...",
  "reason": "..."
}}

Candidates:
{candidates_json}
"""
    for batch_index, batch in enumerate(_batch_items(candidates, batch_size), start=1):
        candidates_json = json.dumps([_format_candidate(item) for item in batch], ensure_ascii=False, indent=2)
        prompt = prompt_template.format(candidates_json=candidates_json)
        response = chat_with_model(RESEARCH_LLM_MODEL, CONTEXT_CLASSIFIER_SYSTEM_PROMPT, prompt, max_tokens=2200)
        parsed = _safe_json_loads(response, [])
        raw_batches.append(
            {
                "batch_index": batch_index,
                "input_image_ids": [item["image_id"] for item in batch],
                "response": response,
                "parsed": parsed,
            }
        )
        if isinstance(parsed, list):
            parsed_all.extend(parsed)
    save_json(stage_dir / "image_context_screening_raw.json", raw_batches)
    save_json(stage_dir / "image_context_screening.json", parsed_all)
    return {item.get("image_id"): item for item in parsed_all if item.get("image_id")}


def _run_topic_ranker(topic, learnings_str, candidates, stage_dir, batch_size, outline=None):
    parsed_all = []
    raw_batches = []

    outline_block = ""
    if outline:
        import re as _re
        outline_clean = _re.sub(r"<citation>.*?</citation>", "", outline)
        outline_clean = _re.sub(r"(?m)^Evidence:.*$\n?", "", outline_clean)
        outline_clean = _re.sub(r"(?m)^Gap:.*$\n?", "", outline_clean)
        outline_clean = _re.sub(r"\n{3,}", "\n\n", outline_clean).strip()
        outline_block = (
            f"\nReport Outline:\n{outline_clean}\n\n"
            "For each image, align your \"recommended_section\" with an actual section title from the outline above.\n\n"
        )

    trimmed_learnings = _trim_text(learnings_str, 8000)
    for batch_index, batch in enumerate(_batch_items(candidates, batch_size), start=1):
        candidates_json = json.dumps([_format_candidate(item) for item in batch], ensure_ascii=False, indent=2)
        prompt = f"""Topic:
{topic}
{outline_block}Learnings:
{trimmed_learnings}

Rank these image candidates for relevance to the topic.
Return a JSON array. Each item must be:
{{
  "image_id": "...",
  "relevance_score": 0-5,
  "should_keep": true,
  "recommended_section": "...",
  "why_relevant": "..."
}}

Candidates:
{candidates_json}
"""
        response = chat_with_model(RESEARCH_LLM_MODEL, TOPIC_RANKER_SYSTEM_PROMPT, prompt, max_tokens=2600)
        parsed = _safe_json_loads(response, [])
        raw_batches.append(
            {
                "batch_index": batch_index,
                "input_image_ids": [item["image_id"] for item in batch],
                "response": response,
                "parsed": parsed,
            }
        )
        if isinstance(parsed, list):
            parsed_all.extend(parsed)
    save_json(stage_dir / "image_topic_screening_raw.json", raw_batches)
    save_json(stage_dir / "image_topic_screening.json", parsed_all)
    return {item.get("image_id"): item for item in parsed_all if item.get("image_id")}


def _run_ocr_stage(topic, candidates, stage_dir, max_images):
    download_dir = stage_dir / "ocr_images"
    ensure_dir(download_dir)
    results = []
    for item in candidates[:max_images]:
        local_name = hashlib.md5(item["url"].encode()).hexdigest()[:12]
        lower_url = item["url"].lower()
        ext = ".png"
        if ".jpg" in lower_url or ".jpeg" in lower_url:
            ext = ".jpg"
        local_path = download_dir / f"{local_name}{ext}"
        error = ""
        raw_response = ""
        parsed = {
            "visible_title": "",
            "visible_text": "",
            "ocr_keywords": [],
            "ocr_summary": "",
            "deductive_evidence_atoms": "",
        }
        try:
            _download_image(item["url"], local_path)
            prompt = f"""Topic: {topic}

Read this image carefully and extract OCR-like signals.
Return plain text with exactly these fields:
visible_title: ...
visible_text: ...
ocr_keywords: keyword1, keyword2, ...
ocr_summary: one sentence
deductive_evidence_atoms: Extract 3-5 key evidence atoms. Format each as: [Visual Feature] -> [Deductive Fact] -> [Rationale].
"""
            raw_response = chat_with_image(
                VISION_METADATA_MLLM_MODEL,
                OCR_SYSTEM_PROMPT,
                prompt,
                str(local_path),
                max_tokens=400,
            )
            for line in (raw_response or "").splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                if key == "visible_title":
                    parsed["visible_title"] = value
                elif key == "visible_text":
                    parsed["visible_text"] = value
                elif key == "ocr_keywords":
                    parsed["ocr_keywords"] = [token.strip() for token in value.split(",") if token.strip()]
                elif key == "ocr_summary":
                    parsed["ocr_summary"] = value
                elif key == "deductive_evidence_atoms":
                    parsed["deductive_evidence_atoms"] = value
        except Exception as exc:
            # OCR/image download is helpful but non-critical. Skip broken images
            # instead of aborting the entire report generation run.
            error = f"{type(exc).__name__}: {exc}"

        results.append(
            {
                "image_id": item["image_id"],
                "url": item["url"],
                "local_path": str(local_path) if local_path.exists() else "",
                "error": error,
                "raw_response": raw_response,
                **parsed,
            }
        )
    save_json(stage_dir / "image_ocr_results.json", results)
    return {item["image_id"]: item for item in results}


def _run_final_selector(topic, learnings_str, candidates, stage_dir, batch_size):
    parsed_all = []
    raw_batches = []
    prompt_template = """Topic:
{topic}

Learnings:
{learnings}

Select the final source images to use in the report.
Return a JSON array. Each item must be:
{{
  "image_id": "...",
  "should_use": true,
  "final_score": 0-5,
  "recommended_section": "...",
  "claim_support": "...",
  "integration_note": "..."
}}

Candidates:
{candidates_json}
"""
    trimmed_learnings = _trim_text(learnings_str, 9000)
    for batch_index, batch in enumerate(_batch_items(candidates, batch_size), start=1):
        candidates_json = json.dumps(batch, ensure_ascii=False, indent=2)
        prompt = prompt_template.format(
            topic=topic,
            learnings=trimmed_learnings,
            candidates_json=candidates_json,
        )
        response = chat_with_model(RESEARCH_LLM_MODEL, FINAL_SELECTOR_SYSTEM_PROMPT, prompt, max_tokens=2600)
        parsed = _safe_json_loads(response, [])
        raw_batches.append(
            {
                "batch_index": batch_index,
                "input_image_ids": [item["image_id"] for item in batch],
                "response": response,
                "parsed": parsed,
            }
        )
        if isinstance(parsed, list):
            parsed_all.extend(parsed)
    save_json(stage_dir / "image_final_selection_raw.json", raw_batches)
    save_json(stage_dir / "image_final_selection.json", parsed_all)
    return {item.get("image_id"): item for item in parsed_all if item.get("image_id")}


def _merge_scores(base_metadata, context_map, topic_map, ocr_map, final_map):
    merged = []
    for item in base_metadata:
        image_id = item["image_id"]
        context_info = context_map.get(image_id, {})
        topic_info = topic_map.get(image_id, {})
        ocr_info = ocr_map.get(image_id, {})
        final_info = final_map.get(image_id, {})
        merged_item = dict(item)
        merged_item.update(
            {
                "context_screening": context_info,
                "topic_screening": topic_info,
                "ocr_metadata": ocr_info,
                "final_selection": final_info,
                "figure_type": context_info.get("figure_type", item.get("figure_type", "unknown")),
                "summary": final_info.get("integration_note")
                or ocr_info.get("ocr_summary")
                or context_info.get("context_summary")
                or item.get("summary", ""),
                "keywords": sorted(
                    set(item.get("keywords", []))
                    | set(_tokenize(context_info.get("context_summary", "")))
                    | set(_tokenize(topic_info.get("why_relevant", "")))
                    | set(ocr_info.get("ocr_keywords", []))
                    | set(_tokenize(ocr_info.get("visible_text", "")))
                ),
                "evidence_role": ocr_info.get("deductive_evidence_atoms", ""),
                "recommended_section": final_info.get("recommended_section") or topic_info.get("recommended_section", ""),
                "context_score": context_info.get("context_score", 0),
                "topic_relevance_score": topic_info.get("relevance_score", 0),
                "final_score": final_info.get("final_score", 0),
                "should_use": bool(final_info.get("should_use", False)),
                "is_original_source_likely": bool(context_info.get("is_original_source_likely", False)),
            }
        )
        merged.append(merged_item)
    return merged


def build_planning_brief(selected_items, stage_dir):
    cards = []
    lines = []
    for item in selected_items:
        card = {
            "image_id": item["image_id"],
            "figure_type": item.get("figure_type", "unknown"),
            "recommended_section": item.get("recommended_section", ""),
            "final_score": item.get("final_score", 0),
            "summary": item.get("summary", ""),
            "ocr_summary": item.get("ocr_metadata", {}).get("ocr_summary", ""),
            "deductive_evidence_atoms": item.get("ocr_metadata", {}).get("deductive_evidence_atoms", ""),
            "claim_support": item.get("final_selection", {}).get("claim_support", ""),
            "integration_note": item.get("final_selection", {}).get("integration_note", ""),
            "url": item.get("url", ""),
        }
        cards.append(card)
        lines.append(
            f"- {card['image_id']} | type: {card['figure_type']} | recommended_section: {card['recommended_section']} | "
            f"score: {card['final_score']} | OCR: {card['ocr_summary']} | "
            f"EVIDENCE_ATOMS: {card['deductive_evidence_atoms']} | claim_support: {card['claim_support']}"
        )
    planning_text = "\n".join(lines) if lines else "No high-confidence image evidence selected."
    save_json(stage_dir / "image_planning_brief.json", cards)
    save_text(stage_dir / "image_planning_brief.txt", planning_text)
    return planning_text


def run_image_enrichment_pipeline(topic, learnings_str, output_dir, base_metadata, pipeline_config=None, outline=None):
    pipeline_config = pipeline_config or {}
    if not base_metadata:
        return base_metadata, ""

    stage_dir = _stage_dir(output_dir)
    save_json(stage_dir / "image_metadata_input.json", base_metadata)

    heuristically_kept, heuristic_pruned = _heuristic_prune(base_metadata)
    save_json(stage_dir / "image_heuristic_filter.json", {
        "kept_count": len(heuristically_kept),
        "pruned_count": len(heuristic_pruned),
        "pruned_items": heuristic_pruned,
    })

    context_map = _run_context_classifier(
        heuristically_kept,
        stage_dir,
        pipeline_config.get("context_screening_batch_size", 12),
    )
    context_candidates = []
    for item in heuristically_kept:
        decision = context_map.get(item["image_id"], {})
        if decision.get("keep") and decision.get("figure_type") != "decorative_or_noise":
            item = dict(item)
            item["_context_score"] = float(decision.get("context_score", 0) or 0)
            context_candidates.append(item)
    context_candidates.sort(key=lambda x: x.get("_context_score", 0), reverse=True)
    context_candidates = context_candidates[: pipeline_config.get("max_context_screened_images", 40)]
    save_json(stage_dir / "image_context_candidates.json", context_candidates)

    topic_map = _run_topic_ranker(
        topic,
        learnings_str,
        context_candidates,
        stage_dir,
        pipeline_config.get("context_screening_batch_size", 12),
        outline=outline,
    )
    topic_candidates = []
    for item in context_candidates:
        decision = topic_map.get(item["image_id"], {})
        if decision.get("should_keep"):
            item = dict(item)
            item["_topic_score"] = float(decision.get("relevance_score", 0) or 0)
            topic_candidates.append(item)
    topic_candidates.sort(key=lambda x: x.get("_topic_score", 0), reverse=True)
    topic_candidates = topic_candidates[: pipeline_config.get("max_topic_shortlist_images", 12)]
    save_json(stage_dir / "image_topic_candidates.json", topic_candidates)

    ocr_map = _run_ocr_stage(
        topic,
        topic_candidates,
        stage_dir,
        pipeline_config.get("max_ocr_images", 8),
    )

    final_selector_inputs = []
    for item in topic_candidates:
        final_selector_inputs.append(
            {
                "image_id": item["image_id"],
                "figure_type_hint": context_map.get(item["image_id"], {}).get("figure_type", item.get("figure_type", "unknown")),
                "summary": item.get("summary", ""),
                "surrounding_text": _trim_text(item.get("surrounding_text", ""), 260),
                "page_title": item.get("page_title", ""),
                "source_domain": item.get("source_domain", ""),
                "topic_relevance": topic_map.get(item["image_id"], {}),
                "ocr": ocr_map.get(item["image_id"], {}),
            }
        )
    final_map = _run_final_selector(
        topic,
        learnings_str,
        final_selector_inputs,
        stage_dir,
        pipeline_config.get("context_screening_batch_size", 12),
    )

    merged = _merge_scores(base_metadata, context_map, topic_map, ocr_map, final_map)
    merged.sort(key=lambda item: (item.get("should_use", False), item.get("final_score", 0), item.get("topic_relevance_score", 0)), reverse=True)
    selected_items = [item for item in merged if item.get("should_use")][: pipeline_config.get("max_final_selected_images", 6)]
    planning_text = build_planning_brief(selected_items, stage_dir)

    save_json(stage_dir / "image_metadata_enriched.json", merged)
    save_json(stage_dir / "image_pipeline_trace.json", {
        "input_count": len(base_metadata),
        "heuristic_kept_count": len(heuristically_kept),
        "context_candidate_count": len(context_candidates),
        "topic_candidate_count": len(topic_candidates),
        "ocr_count": len(ocr_map),
        "final_selected_count": len(selected_items),
    })
    return merged, planning_text
