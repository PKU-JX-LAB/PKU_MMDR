import re


def _tokenize(value):
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", " ", value or "").lower()
    return {token for token in cleaned.split() if len(token) > 1}


SECTION_HEADER_RE = re.compile(
    r"""(?imx)
    ^
    (?:
        \*\*Section\s+\d+\s+Title:\*\*\s*(?P<title_a>.+?)\s*$
        |
        \*\*Section\s+\d+:\s*(?P<title_b>.+?)\*\*\s*$
        |
        \*\*Section\s+\d+\*\*\s*$\n\*\*Title:\*\*\s*(?P<title_f>.+?)\s*$
        |
        \*\*Section:\s*(?P<title_c>.+?)\*\*\s*$
        |
        \#\#?\s*Section\s+\d+:\s*(?P<title_d>.+?)\s*$
        |
        \#\#?\s*Section\s+\d+\s+Title:\s*(?P<title_e>.+?)\s*$
    )
    """
)

SUMMARY_LINE_RE = re.compile(r"(?im)^\*\*Summary:\*\*\s*(.*)$")
EVIDENCE_LINE_RE = re.compile(r"(?im)^Evidence:\s*\[([^\]]*)\]")
GAP_LINE_RE = re.compile(r"(?im)^Gap:\s*(.+)$")
CITATION_RE = re.compile(r"<citation>(.*?)</citation>")
NUMBERED_SECTION_RE = re.compile(r"(?m)^#\s+(\d+)\.\s*(.+)$")


def _clean_title(raw_title):
    title = (raw_title or "").strip()
    title = re.sub(r"\*\*$", "", title).strip()
    return title


def _extract_summary(block_text):
    text = block_text.strip()
    if not text:
        return ""

    raw_no_meta = re.sub(r"(?m)^Evidence:.*$", "", text)
    raw_no_meta = re.sub(r"(?m)^Gap:.*$", "", raw_no_meta)
    raw_no_meta = re.sub(r"<citation>.*?</citation>", "", raw_no_meta)

    text = re.sub(r"(?m)^#{1,3}\s+.*$", "", raw_no_meta)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if not text:
        text = re.sub(r"\n{3,}", "\n\n", raw_no_meta).strip()

    summary_match = SUMMARY_LINE_RE.search(text)
    if summary_match:
        summary_start = summary_match.end()
        summary = text[summary_start:].strip()
        if summary:
            return summary
        inline_summary = summary_match.group(1).strip()
        if inline_summary:
            return inline_summary

    return text


def _extract_citation_ids(block_text):
    all_ids = []
    for match in CITATION_RE.finditer(block_text):
        raw = match.group(1).strip()
        for token in raw.split(","):
            token = token.strip()
            if token.startswith("id "):
                num = re.sub(r"^id\s+", "", token)
                all_ids.append(f"L{num}")
            elif token.startswith("L"):
                all_ids.append(token)
            elif token.isdigit():
                all_ids.append(f"L{token}")
    return all_ids if all_ids else None


def _extract_evidence_ids(block_text):
    match = EVIDENCE_LINE_RE.search(block_text)
    if not match:
        return None
    raw = match.group(1).strip()
    if not raw:
        return []
    return [token.strip() for token in raw.split(",") if token.strip()]


def _extract_gap(block_text):
    match = GAP_LINE_RE.search(block_text)
    return match.group(1).strip() if match else None


def parse_outline(outline_text):
    numbered_matches = list(NUMBERED_SECTION_RE.finditer(outline_text))
    top_level = [(match, match.group(2).strip()) for match in numbered_matches]
    if len(top_level) >= 2:
        sections = []
        for idx, (match, title) in enumerate(top_level):
            start = match.end()
            end = top_level[idx + 1][0].start() if idx + 1 < len(top_level) else len(outline_text)
            content = outline_text[start:end]
            summary = _extract_summary(content)
            section = {"title": title, "summary": summary}
            citation_ids = _extract_citation_ids(content)
            if citation_ids is not None:
                section["evidence_ids"] = citation_ids
            evidence_ids = _extract_evidence_ids(content)
            if evidence_ids is not None:
                section.setdefault("evidence_ids", []).extend(evidence_ids)
            gap = _extract_gap(content)
            if gap is not None:
                section["gap"] = gap
            sections.append(section)
        return sections

    matches = list(SECTION_HEADER_RE.finditer(outline_text))
    if not matches:
        return [{"title": "Full Report", "summary": outline_text}]

    sections = []
    for idx, match in enumerate(matches):
        title = _clean_title(
            match.group("title_a")
            or match.group("title_b")
            or match.group("title_f")
            or match.group("title_c")
            or match.group("title_d")
            or match.group("title_e")
        )
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(outline_text)
        content = outline_text[start:end]
        summary = _extract_summary(content)
        section = {"title": title or f"Section {idx + 1}", "summary": summary}
        evidence_ids = _extract_evidence_ids(content)
        if evidence_ids is not None:
            section["evidence_ids"] = evidence_ids
        gap = _extract_gap(content)
        if gap is not None:
            section["gap"] = gap
        sections.append(section)

    return sections


def route_learnings(section, all_learnings, id_map=None):
    if id_map is None or "evidence_ids" not in section:
        return all_learnings
    evidence_ids = section["evidence_ids"]
    if not evidence_ids:
        print(f"  [route_learnings] Section '{section.get('title')}' has empty Evidence - returning no learnings")
        return ""
    routed = [id_map[eid] for eid in evidence_ids if eid in id_map]
    if not routed:
        print(
            f"  [route_learnings] WARNING: Section '{section.get('title')}' evidence IDs not found in id_map - returning no learnings"
        )
        return ""
    return "\n".join(f"- {learning}" for learning in routed)


def _format_blind_image_candidates(image_pool, used_images, max_images):
    available = []
    max_images = max_images if isinstance(max_images, int) and max_images > 0 else len(image_pool)
    for image_id in image_pool:
        if image_id in used_images:
            continue
        available.append(f"- {image_id} | placeholder only")
        if len(available) >= max_images:
            break
    if not available:
        return "None (All images have been used or no images available)"
    return "\n".join(available)


def _format_weak_metadata_image_candidates(
    section,
    image_pool,
    used_images,
    image_metadata,
    max_images=1,
):
    max_images = max_images if isinstance(max_images, int) and max_images > 0 else max(1, len(image_pool))
    metadata_by_id = {
        item.get("image_id"): item for item in (image_metadata or []) if item.get("image_id")
    }
    if not metadata_by_id:
        return "None (Weak metadata unavailable for original images)"

    section_text = f"{section.get('title', '')} {section.get('summary', '')}"
    section_tokens = _tokenize(section_text)
    ranked_images = []

    for image_id, url in image_pool.items():
        if image_id in used_images:
            continue
        item = metadata_by_id.get(image_id, {})
        alt_text = item.get("alt_text", "")
        page_title = item.get("page_title", "")
        surrounding_text = item.get("surrounding_text", "")
        page_url = item.get("page_url", "")
        source_domain = item.get("source_domain", "")

        title_tokens = _tokenize(f"{alt_text} {page_title}")
        nearby_tokens = _tokenize(surrounding_text)
        url_tokens = _tokenize(f"{url} {page_url} {source_domain}")

        title_overlap = len(section_tokens & title_tokens)
        nearby_overlap = len(section_tokens & nearby_tokens)
        url_overlap = len(section_tokens & url_tokens)
        score = title_overlap * 3.0 + nearby_overlap * 1.5 + url_overlap * 0.5
        if score <= 0:
            continue

        ranked_images.append(
            (
                score,
                image_id,
                url,
                {
                    "alt_text": alt_text,
                    "page_title": page_title,
                    "surrounding_text": surrounding_text,
                    "source_domain": source_domain,
                },
            )
        )

    ranked_images.sort(key=lambda x: (-x[0], x[1]))
    selected_images = ranked_images[:max_images]
    if not selected_images:
        return "None (No weak-metadata image matched this section)"

    available_images = []
    for _, image_id, url, item in selected_images:
        nearby = re.sub(r"\s+", " ", (item.get("surrounding_text", "") or "").strip())
        if len(nearby) > 180:
            nearby = nearby[:177].rstrip() + "..."
        alt_text = re.sub(r"\s+", " ", (item.get("alt_text", "") or "").strip()) or "-"
        page_title = re.sub(r"\s+", " ", (item.get("page_title", "") or "").strip()) or "-"
        source_domain = item.get("source_domain", "") or "-"
        nearby = nearby or "-"
        available_images.append(
            f"- {image_id} | alt: {alt_text} | page_title: {page_title} | source: {source_domain} | nearby_text: {nearby} | URL hint: {url}"
        )

    return "\n".join(available_images)


def route_images(section, image_pool, used_images=None, image_metadata=None, max_images=4, selection_mode="semantic"):
    if not image_pool:
        return "None"

    if used_images is None:
        used_images = set()

    selection_mode = (selection_mode or "semantic").strip().lower()
    if selection_mode == "blind":
        return _format_blind_image_candidates(image_pool, used_images, max_images)
    if selection_mode == "weak_metadata":
        return _format_weak_metadata_image_candidates(
            section,
            image_pool,
            used_images,
            image_metadata,
            max_images=max_images,
        )

    metadata_by_id = {
        item.get("image_id"): item for item in (image_metadata or []) if item.get("image_id")
    }
    section_text = f"{section.get('title', '')} {section.get('summary', '')}"
    section_tokens = _tokenize(section_text)
    approved_candidates = [
        item for item in (image_metadata or [])
        if item.get("image_id") in image_pool
        and item.get("should_use")
        and item.get("image_id") not in used_images
    ]
    candidate_ids = {item["image_id"] for item in approved_candidates} if approved_candidates else None

    def score_image(img_id, url):
        item = metadata_by_id.get(img_id, {})
        if candidate_ids is not None and img_id not in candidate_ids:
            return float("-inf")

        keyword_tokens = set(item.get("keywords", []))
        title_tokens = _tokenize(item.get("source_title", ""))
        summary_tokens = _tokenize(item.get("summary", ""))
        claim_tokens = _tokenize(item.get("final_selection", {}).get("claim_support", ""))
        integration_tokens = _tokenize(item.get("final_selection", {}).get("integration_note", ""))
        url_tokens = _tokenize(url)
        overlap = len(
            section_tokens & (keyword_tokens | title_tokens | summary_tokens | claim_tokens | integration_tokens | url_tokens)
        )
        figure_type = item.get("figure_type", "unknown")
        figure_bonus = 0
        lowered_section = section_text.lower()
        if any(token in lowered_section for token in ("algorithm", "流程", "pipeline", "framework", "架构")) and figure_type in {"algorithm_diagram", "pipeline"}:
            figure_bonus += 3
        if any(token in lowered_section for token in ("result", "benchmark", "performance", "实验", "accuracy", "对比")) and figure_type in {"result_chart", "ablation_table"}:
            figure_bonus += 2
        credibility = float(item.get("credibility_score", 0.0) or 0.0)
        final_score = float(item.get("final_score", 0.0) or 0.0)
        topic_score = float(item.get("topic_relevance_score", 0.0) or 0.0)
        context_score = float(item.get("context_score", 0.0) or 0.0)
        recommended_section = item.get("recommended_section", "")
        recommended_tokens = _tokenize(recommended_section)
        section_bonus = 0
        if recommended_tokens and (section_tokens & recommended_tokens):
            section_bonus += 3
        elif recommended_section:
            section_bonus -= 1
        return overlap * 3 + figure_bonus + credibility + final_score * 2 + topic_score + context_score * 0.5 + section_bonus

    ranked_images = []
    for img_id, url in image_pool.items():
        if img_id in used_images:
            continue
        score = score_image(img_id, url)
        if score == float("-inf"):
            continue
        ranked_images.append((score, img_id, url, metadata_by_id.get(img_id, {})))

    ranked_images.sort(key=lambda x: (-x[0], x[1]))
    selected_images = ranked_images[:max_images]

    available_images = []
    for score, img_id, url, item in selected_images:
        figure_type = item.get("figure_type", "unknown")
        source_domain = item.get("source_domain", "")
        summary = item.get("summary", "")
        final_score = item.get("final_score", 0)
        recommended_section = item.get("recommended_section", "")
        available_images.append(
            f"- {img_id} | type: {figure_type} | source: {source_domain} | relevance: {score:.1f} | final_score: {final_score} | recommended_section: {recommended_section} | summary: {summary} | URL hint: {url}"
        )

    if not available_images:
        if candidate_ids is not None:
            return "None (No approved source images matched this section)"
        return "None (All images have been used or no images available)"

    return "\n".join(available_images)


def route_images_legacy_true_only(section, image_pool, used_images=None, image_metadata=None, max_images=1):
    if not image_pool:
        return "None"

    if used_images is None:
        used_images = set()

    approved_candidates = [
        item for item in (image_metadata or [])
        if item.get("image_id") in image_pool
        and item.get("should_use")
        and item.get("image_id") not in used_images
    ]
    if not approved_candidates:
        return "None (No approved source images available for this section)"

    section_text = f"{section.get('title', '')} {section.get('summary', '')}"
    section_tokens = _tokenize(section_text)
    ranked_images = []

    for item in approved_candidates:
        image_id = item.get("image_id")
        url = image_pool.get(image_id, "")

        recommended_tokens = _tokenize(item.get("recommended_section", ""))
        title_tokens = _tokenize(item.get("page_title", "")) | _tokenize(item.get("source_title", ""))
        alt_tokens = _tokenize(item.get("alt_text", ""))
        summary_tokens = _tokenize(item.get("summary", ""))
        keyword_tokens = set(item.get("keywords", []))

        recommended_overlap = len(section_tokens & recommended_tokens)
        title_overlap = len(section_tokens & title_tokens)
        alt_overlap = len(section_tokens & alt_tokens)
        summary_overlap = len(section_tokens & summary_tokens)
        keyword_overlap = len(section_tokens & keyword_tokens)

        score = (
            recommended_overlap * 4.0
            + title_overlap * 3.0
            + alt_overlap * 2.5
            + summary_overlap * 1.5
            + keyword_overlap * 0.5
        )
        if score <= 0:
            continue

        ranked_images.append((score, image_id, url, item))

    ranked_images.sort(key=lambda x: (-x[0], x[1]))
    selected_images = ranked_images[:max(1, max_images)]
    if not selected_images:
        return "None (No approved source images matched this section)"

    available_images = []
    for score, image_id, url, item in selected_images:
        source_domain = item.get("source_domain", "")
        recommended_section = item.get("recommended_section", "")
        summary = item.get("summary", "")
        available_images.append(
            f"- {image_id} | source: {source_domain} | local_match: {score:.1f} | "
            f"recommended_section: {recommended_section} | summary: {summary} | URL hint: {url}"
        )

    return "\n".join(available_images)


def route_global_images(topic, outline, image_pool, image_metadata=None, max_images=None, selection_mode="semantic"):
    pseudo_section = {
        "title": topic or "Full Report",
        "summary": outline or "",
    }
    return route_images(
        pseudo_section,
        image_pool,
        used_images=set(),
        image_metadata=image_metadata,
        max_images=max_images,
        selection_mode=selection_mode,
    )


def route_images_from_ranked(ranked_images):
    if not ranked_images:
        return "None (No strongly relevant images found for this section)"
    return "\n".join(
        f"- {item['image_id']} (type: {item.get('figure_type', 'unknown')}, score: {item.get('score', 0):.2f}, hint: {item.get('url', '')})"
        for item in ranked_images
    )
