import os
import re

from .artifact_utils import save_json


def _tokenize(text):
    return {token for token in re.findall(r"[a-zA-Z0-9]{3,}", (text or "").lower())}


def rank_images_for_section(
    *,
    section,
    sec_learnings,
    image_pool,
    image_metadata,
    used_images=None,
    used_dedup_keys=None,
    max_images=2,
    output_dir=None,
    enable_dedup=True,
):
    if used_images is None:
        used_images = set()
    if used_dedup_keys is None:
        used_dedup_keys = set()
    section_tokens = _tokenize(section.get("title", "")) | _tokenize(section.get("summary", "")) | _tokenize(sec_learnings)
    ranked = []
    for item in image_metadata:
        image_id = item.get("image_id")
        dedup_key = item.get("dedup_key", image_id)
        if image_id in used_images or image_id not in image_pool:
            continue
        if enable_dedup and dedup_key in used_dedup_keys:
            continue
        keywords = set(item.get("keywords", []))
        item_text_tokens = _tokenize(item.get("summary", "")) | _tokenize(item.get("evidence_role", "")) | _tokenize(item.get("text", "")) | _tokenize(" ".join(keywords))
        
        # INCREASE BASE SCORE BY MATCHING KEYWORDS HEAVILY
        keyword_matches = len(section_tokens & item_text_tokens)
        
        # STRICT RELEVANCE: If there is zero textual overlap with the section, it's irrelevant.
        if keyword_matches < 2:
            continue
            
        score = (keyword_matches * 2.0) + item.get("credibility_score", 0)

        # FAVOR HIGHLY RELEVANT ARCHITECTURE DIAGRAMS
        if item.get("figure_type") in {"algorithm_diagram", "pipeline", "architecture", "hardware", "schematic"}:
            score += 3.0
        elif item.get("figure_type") in {"result_chart", "ablation_table", "benchmark"}:
            score += 2.0

        # Add score based on evidence role length to prefer images with deep analysis
        evidence_len = len(item.get("evidence_role", ""))
        if evidence_len > 20:
            score += 1.0

        # ONLY INCLUDE IF IT HAS SOME RELEVANCE
        if score > 4.0:
            ranked.append(
                {
                    "image_id": image_id,
                    "score": score,
                    "url": image_pool[image_id],
                    "figure_type": item.get("figure_type", "unknown"),
                    "dedup_key": dedup_key,
                    "summary": item.get("summary", ""),
                    "evidence_role": item.get("evidence_role", ""),
                }
            )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    if enable_dedup:
        unique_ranked = []
        seen_keys = set()
        for item in ranked:
            dedup_key = item.get("dedup_key", item["image_id"])
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            unique_ranked.append(item)
        ranked = unique_ranked
    selected = ranked[:max_images]
    if output_dir:
        path = os.path.join(output_dir, "section_image_ranking.json")
        existing = []
        if os.path.exists(path):
            import json
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(
            {
                "section_title": section.get("title", ""),
                "selected_images": selected,
                "candidate_count": len(ranked),
            }
        )
        save_json(path, existing)
    return selected


def format_ranked_images(ranked_images):
    if not ranked_images:
        return "None (No strongly relevant images found for this section)"
    return "\n".join(
        f"- {item['image_id']} (type: {item['figure_type']}, score: {item['score']:.2f}, hint: {item['url']})"
        for item in ranked_images
    )
