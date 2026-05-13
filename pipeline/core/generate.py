import os
import re
import time
import json
import traceback
from .config import (
    GLOBAL_REPORT_LLM_MODEL,
    REPORT_LLM_MODEL,
    CHART_ACTOR_MODEL,
    CHART_CRITIC_MLLM_MODEL,
    MAX_RETRIES,
    MAX_GENERATED_CHARTS,
    IMAGE_PIPELINE_CONFIG,
    ENABLE_REPORT_PREPROCESS,
    ENABLE_FINAL_REPORT_POLISH,
)
from .llm_utils import chat_with_model, chat_with_image
from .prompts import (
    REPORT_GENERATION_SYSTEM_PROMPT, REPORT_GENERATION_USER_PROMPT,
    CHART_ACTOR_SYSTEM_PROMPT, CHART_ACTOR_USER_PROMPT,
    CHART_CRITIC_SYSTEM_PROMPT, CHART_CRITIC_USER_PROMPT,
    CHART_REGEN_USER_PROMPT, CHART_SELECTION_SYSTEM_PROMPT, CHART_SELECTION_USER_PROMPT
)
from .prompt_builders import build_section_prompt
from .image_ranker import rank_images_for_section
from .image_grounding_check import check_section_grounding, prune_ungrounded_images
from .final_report_rewrite import rewrite_report_content
from .artifact_utils import save_json

try:
    from .page_render import render_page
except ImportError:
    print("Warning: Could not import page_render. Selenium might not be configured properly.")

    def render_page(folder_path, page_file_name, screenshot_folder):
        return None, "Selenium not configured", 0, 0


def _detect_template_chart_issue(html_code, chart_design):
    html_lower = (html_code or "").lower()
    design_lower = (chart_design or "").lower()
    phrase_patterns = {
        "monthly performance": r"\bmonthly performance\b",
        "sample data": r"\bsample data\b",
        "demonstration": r"\bdemonstration\b",
        "actual results": r"\bactual results\b",
        "values shown in thousands": r"\bvalues shown in thousands\b",
    }
    hit_terms = [
        label for label, pattern in phrase_patterns.items()
        if re.search(pattern, html_lower)
    ]
    month_hits = re.findall(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
        html_lower,
    )
    if len(set(month_hits)) >= 4:
        hit_terms.append("month-axis-template")
    if hit_terms:
        return (
            "Design-spec mismatch / template fallback: the HTML contains generic chart-template "
            f"terms {hit_terms}. Do not use placeholder monthly/target/sample content; implement the provided specification exactly."
        )

    flow_like = any(
        term in design_lower
        for term in [
            "pipeline",
            "flow",
            "flowchart",
            "diagram",
            "schematic",
            "rounded boxes",
            "no quantitative axes",
            "no numeric axes",
        ]
    )
    generic_axis_chart = (
        bool(re.search(r"\bperformance \(thousands\)\b", html_lower))
        or bool(re.search(r"\bline chart\b", html_lower))
        or "axisbottom" in html_lower
        or "axisleft" in html_lower
        or len(set(month_hits)) >= 4
    )
    if flow_like and generic_axis_chart:
        return (
            "Design-spec mismatch: the specification requires a pipeline / schematic / no-axis diagram, "
            "but the HTML looks like a generic axis-based line chart. Rebuild the visualization as the specified flowchart."
        )
    return None


def _collect_visualization_replacements(report_content):
    replacements = []
    occupied_ranges = []
    full_pattern = re.compile(r"<visualization>.*?</visualization>", re.DOTALL)
    for match in full_pattern.finditer(report_content):
        replacements.append((match.start(), match.group(0), match.group(0)))
        occupied_ranges.append((match.start(), match.end()))

    start_positions = [m.start() for m in re.finditer(r"<visualization>", report_content)]
    boundary_pattern = re.compile(r"\n## |\n### |\n# |<visualization>|\Z", re.DOTALL)

    def covered(start_pos):
        return any(start <= start_pos < end for start, end in occupied_ranges)

    for start in start_positions:
        if covered(start):
            continue
        content_start = start + len("<visualization>")
        boundary = boundary_pattern.search(report_content, content_start)
        end = boundary.start() if boundary else len(report_content)
        block_body = report_content[content_start:end].strip()
        if block_body.startswith("{"):
            normalized = f"<visualization>\n{block_body}\n</visualization>"
            raw_block = report_content[start:end]
            replacements.append((start, raw_block, normalized))

    replacements.sort(key=lambda item: item[0])
    return [(raw_block, normalized) for _, raw_block, normalized in replacements]

def extract_code(resp: str, language: str = "html") -> str:
    try:
        if f"```{language}" in resp:
            code = resp.split(f"```{language}")[1].split("```")[0].strip()
        else:
            code = resp.split("```")[1].split("```")[0].strip()
    except Exception as e:
        code = resp if resp is not None else ""
    return code

def _detect_template_chart_issue(html_code, chart_design):
    html_lower = (html_code or "").lower()
    design_lower = (chart_design or "").lower()
    phrase_patterns = {
        "monthly performance": r"\bmonthly performance\b",
        "sample data": r"\bsample data\b",
        "demonstration": r"\bdemonstration\b",
        "actual results": r"\bactual results\b",
        "values shown in thousands": r"\bvalues shown in thousands\b",
    }
    hit_terms = [
        label for label, pattern in phrase_patterns.items()
        if re.search(pattern, html_lower)
    ]
    month_hits = re.findall(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
        html_lower,
    )
    if len(set(month_hits)) >= 4:
        hit_terms.append("month-axis-template")
    if hit_terms:
        return (
            "Design-spec mismatch / template fallback: the HTML contains generic chart-template "
            f"terms {hit_terms}. Do not use placeholder monthly/target/sample content; implement the provided specification exactly."
        )

    flow_like = any(
        term in design_lower
        for term in [
            "pipeline",
            "flow",
            "flowchart",
            "diagram",
            "schematic",
            "rounded boxes",
            "no quantitative axes",
            "no numeric axes",
        ]
    )
    generic_axis_chart = (
        bool(re.search(r"\bperformance \(thousands\)\b", html_lower))
        or bool(re.search(r"\bline chart\b", html_lower))
        or "axisbottom" in html_lower
        or "axisleft" in html_lower
        or len(set(month_hits)) >= 4
    )
    if flow_like and generic_axis_chart:
        return (
            "Design-spec mismatch: the specification requires a pipeline / schematic / no-axis diagram, "
            "but the HTML looks like a generic axis-based line chart. Rebuild the visualization as the specified flowchart."
        )
    return None

def _strip_leading_duplicate_section_heading(section_content, section_title):
    content = (section_content or "").lstrip()
    if not content:
        return ""
    title_pattern = re.escape((section_title or "").strip())
    duplicate_patterns = [
        rf"^(?:##|###)\s*{title_pattern}\s*\n+",
        rf"^\*\*(?:##\s*)?{title_pattern}\*\*\s*\n+",
        rf"^{title_pattern}\s*\n+",
    ]
    changed = True
    while changed and content:
        changed = False
        for pattern in duplicate_patterns:
            new_content, count = re.subn(pattern, "", content, count=1, flags=re.IGNORECASE)
            if count:
                content = new_content.lstrip()
                changed = True
    return content.strip()


def _chinese_numeral_to_int(text):
    text = (text or "").strip()
    if not text:
        return None
    direct = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    if text in direct:
        return direct[text]
    if text.startswith("十"):
        tail = text[1:]
        tail_value = direct.get(tail, 0) if tail else 0
        return 10 + tail_value
    if "十" in text:
        parts = text.split("十", 1)
        tens = direct.get(parts[0], None)
        ones = direct.get(parts[1], 0) if parts[1] else 0
        if tens is not None:
            return tens * 10 + ones
    return None


def normalize_report_heading_styles(report_content):
    lines = (report_content or "").splitlines()
    normalized_lines = []

    for line in lines:
        match = re.match(r"^(#{3,6})\s+(.*)$", line)
        if not match:
            normalized_lines.append(line)
            continue

        hashes, title = match.groups()
        title = title.strip()

        arabic_paren = re.match(r"^(\d+)\s*[)）]\s+(.*)$", title)
        if arabic_paren:
            number, rest = arabic_paren.groups()
            normalized_lines.append(f"{hashes} {number}. {rest.strip()}")
            continue

        chinese_num = re.match(r"^([一二三四五六七八九十]+)\s*[、.．]\s*(.*)$", title)
        if chinese_num:
            raw_num, rest = chinese_num.groups()
            value = _chinese_numeral_to_int(raw_num)
            if value is not None:
                normalized_lines.append(f"{hashes} {value}. {rest.strip()}")
                continue

        chinese_paren = re.match(r"^[（(]([一二三四五六七八九十]+)[)）]\s*(.*)$", title)
        if chinese_paren:
            raw_num, rest = chinese_paren.groups()
            value = _chinese_numeral_to_int(raw_num)
            if value is not None:
                normalized_lines.append(f"{hashes} {value}. {rest.strip()}")
                continue

        normalized_lines.append(line)

    normalized = "\n".join(normalized_lines)
    normalized = re.sub(r"(?im)^##\s*Report\s*$\n?", "", normalized)
    return normalized.strip() + "\n"


REFERENCE_EXCLUDED_DOMAINS = (
    "picx.zhimg.com",
    "pica.zhimg.com",
    "pic1.zhimg.com",
    "pic4.zhimg.com",
    "zhimg.com",
    "zhihu.com",
    "zhida.zhihu.com",
)

REFERENCE_PREFERRED_DOMAINS = (
    "arxiv.org",
    "openreview.net",
    "github.com",
    "doi.org",
    "huggingface.co",
)
REFERENCE_SECTION_RE = re.compile(
    r"(?is)(?:\n|^)\#\#\s*(references|参考文献)\s*\n.*\Z"
)
EXISTING_REFERENCE_ENTRY_RE = re.compile(
    r"(?im)^\s*(\d+)\.\s+\[([^\]]+)\]\((https?://[^)]+)\)\s*$"
)
INLINE_REFERENCE_LINK_RE = re.compile(
    r"(?<!\!)\[([^\]]+)\]\((https?://[^)\s]+)\)",
    flags=re.IGNORECASE,
)
AUTOLINK_REFERENCE_RE = re.compile(r"<(https?://[^>\s]+)>", flags=re.IGNORECASE)
BARE_REFERENCE_URL_RE = re.compile(r"https?://[^\s<>)\]]+", flags=re.IGNORECASE)
PROTECTED_CITATION_SPAN_RE = re.compile(
    r"```[\s\S]*?```|<HTMLRenderer\b[^>]*\/>|!\[[^\]]*\]\([^)]+\)",
    flags=re.IGNORECASE,
)
SOURCE_ATTRIBUTION_LINE_RE = re.compile(
    r"^\s*(?:Sources?|Definition source)\b.*?:\s*(.*)$",
    flags=re.IGNORECASE,
)
CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")


def _looks_like_image_url(url):
    url_lower = url.lower()
    return any(url_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"])


def _is_reference_candidate(url):
    url_lower = url.lower().strip()
    if not url_lower.startswith(("http://", "https://")):
        return False
    if _looks_like_image_url(url_lower):
        return False
    return not any(domain in url_lower for domain in REFERENCE_EXCLUDED_DOMAINS)


def _normalize_reference_url(url):
    cleaned = url.strip().rstrip(").,;")
    cleaned = cleaned.replace("http://", "https://", 1)
    if "arxiv.org/pdf/" in cleaned:
        cleaned = cleaned.replace("/pdf/", "/abs/")
        if cleaned.endswith(".pdf"):
            cleaned = cleaned[:-4]
    return cleaned


def _clean_reference_label(label, url):
    label = re.sub(r"\s+", " ", (label or "").strip())
    if label and not re.fullmatch(r"https?://\S+", label):
        return label
    return _normalize_reference_url(url)


def _extract_markdown_links(text):
    entries = []
    for label, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text or ""):
        if _is_reference_candidate(url):
            entries.append((_clean_reference_label(label, url), _normalize_reference_url(url)))
    return entries


def _extract_arxiv_entries(text):
    entries = []
    for arxiv_id in sorted(set(re.findall(r"arXiv:(\d{4}\.\d{4,5})", text or "", flags=re.IGNORECASE))):
        url = f"https://arxiv.org/abs/{arxiv_id}"
        entries.append((f"arXiv:{arxiv_id}", url))
    return entries


def _reference_priority(url):
    url_lower = url.lower()
    for idx, domain in enumerate(REFERENCE_PREFERRED_DOMAINS):
        if domain in url_lower:
            return idx
    return len(REFERENCE_PREFERRED_DOMAINS)


def _is_body_citation_candidate(url):
    url_lower = (url or "").lower().strip()
    if not url_lower.startswith(("http://", "https://")):
        return False
    return not any(domain in url_lower for domain in REFERENCE_EXCLUDED_DOMAINS)


def _detect_references_heading(report_content):
    if re.search(r"(?im)^##\s*参考文献\s*$", report_content or ""):
        return "参考文献"
    if re.search(r"(?im)^##\s*references\s*$", report_content or ""):
        return "References"
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", report_content or ""))
    return "参考文献" if chinese_chars >= 80 else "References"


def _strip_existing_references_section(report_content):
    return REFERENCE_SECTION_RE.sub("", report_content or "").rstrip()


def _extract_existing_references(report_content):
    match = REFERENCE_SECTION_RE.search(report_content or "")
    if not match:
        return []

    references = []
    for item in EXISTING_REFERENCE_ENTRY_RE.finditer(match.group(0)):
        _, label, url = item.groups()
        normalized_url = _normalize_reference_url(url)
        if not _is_body_citation_candidate(normalized_url):
            continue
        references.append(
            {
                "url": normalized_url,
                "label": _clean_reference_label(label, normalized_url) or normalized_url,
            }
        )
    return references


def _protect_non_citation_spans(report_content):
    protected_parts = []
    cursor = 0
    placeholders = []
    for idx, match in enumerate(PROTECTED_CITATION_SPAN_RE.finditer(report_content or ""), start=1):
        protected_parts.append(report_content[cursor:match.start()])
        token = f"[[PROTECTED_SPAN_{idx:03d}]]"
        protected_parts.append(token)
        placeholders.append((token, match.group(0)))
        cursor = match.end()
    protected_parts.append((report_content or "")[cursor:])
    return "".join(protected_parts), placeholders


def _restore_protected_spans(report_content, placeholders):
    restored = report_content
    for token, raw_text in placeholders:
        restored = restored.replace(token, raw_text)
    return restored


def _choose_reference_label(current_label, candidate_label, url):
    normalized_url = _normalize_reference_url(url)
    clean_candidate = _clean_reference_label(candidate_label, normalized_url)
    if not clean_candidate:
        return current_label or normalized_url

    current_is_url = bool(re.fullmatch(r"https?://\S+", current_label or ""))
    candidate_is_url = bool(re.fullmatch(r"https?://\S+", clean_candidate))
    if not current_label:
        return clean_candidate
    if current_is_url and not candidate_is_url:
        return clean_candidate
    return current_label


def _convert_links_to_numbered_citations(report_content):
    heading = _detect_references_heading(report_content)
    existing_references = _extract_existing_references(report_content)
    body_without_refs = _strip_existing_references_section(report_content)
    protected_body, placeholders = _protect_non_citation_spans(body_without_refs)

    references = []
    references_by_url = {}

    for existing in existing_references:
        entry = {
            "index": len(references) + 1,
            "url": existing["url"],
            "label": existing["label"],
        }
        references_by_url[existing["url"]] = entry
        references.append(entry)

    def register_reference(url, label=""):
        normalized_url = _normalize_reference_url(url)
        if not _is_body_citation_candidate(normalized_url):
            return None

        entry = references_by_url.get(normalized_url)
        if entry is None:
            entry = {
                "index": len(references) + 1,
                "url": normalized_url,
                "label": _clean_reference_label(label, normalized_url),
            }
            if not entry["label"]:
                entry["label"] = normalized_url
            references_by_url[normalized_url] = entry
            references.append(entry)
        else:
            entry["label"] = _choose_reference_label(entry.get("label", ""), label, normalized_url)
        return entry["index"]

    def replace_inline_link(match):
        label, url = match.groups()
        index = register_reference(url, label)
        if index is None:
            return match.group(0)
        return f"[{index}]"

    converted_body = INLINE_REFERENCE_LINK_RE.sub(replace_inline_link, protected_body)

    def replace_autolink(match):
        url = match.group(1)
        index = register_reference(url, "")
        if index is None:
            return match.group(0)
        return f"[{index}]"

    converted_body = AUTOLINK_REFERENCE_RE.sub(replace_autolink, converted_body)

    def replace_bare_url(match):
        url = match.group(0)
        trailing = ""
        while url and url[-1] in ".,;:":
            trailing = url[-1] + trailing
            url = url[:-1]

        index = register_reference(url, "")
        if index is None:
            return match.group(0)
        return f"[{index}]{trailing}"

    converted_body = BARE_REFERENCE_URL_RE.sub(replace_bare_url, converted_body)
    converted_body = _restore_protected_spans(converted_body, placeholders)

    if not references:
        return report_content

    reference_lines = [f"## {heading}", ""]
    for entry in references:
        reference_lines.append(f"{entry['index']}. [{entry['label']}]({entry['url']})")
    references_block = "\n".join(reference_lines).strip()
    return converted_body.rstrip() + "\n\n" + references_block + "\n"


def _inline_source_attribution_lines(report_content):
    lines = (report_content or "").splitlines()
    rewritten = []

    def append_citations_to_previous(citations):
        if not citations:
            return False
        for idx in range(len(rewritten) - 1, -1, -1):
            previous = rewritten[idx]
            if not previous.strip():
                continue

            hard_break = previous.endswith("  ")
            previous_core = previous[:-2].rstrip() if hard_break else previous.rstrip()
            existing = set(CITATION_MARKER_RE.findall(previous_core))
            new_markers = [f"[{num}]" for num in citations if num not in existing]
            if not new_markers:
                return True

            spacer = "" if previous_core.endswith((" ", "\t")) else " "
            rewritten[idx] = previous_core + spacer + "".join(new_markers) + ("  " if hard_break else "")
            return True
        return False

    for line in lines:
        match = SOURCE_ATTRIBUTION_LINE_RE.match(line)
        if not match:
            rewritten.append(line)
            continue

        citation_numbers = []
        seen = set()
        for number in CITATION_MARKER_RE.findall(match.group(1)):
            if number in seen:
                continue
            seen.add(number)
            citation_numbers.append(number)

        if append_citations_to_previous(citation_numbers):
            continue

        fallback = "".join(f"[{num}]" for num in citation_numbers)
        if fallback:
            rewritten.append(fallback)

    cleaned = "\n".join(rewritten)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned


def cleanup_report_for_publication(report_content, output_dir=None):
    print("=== Cleaning Report For Publication ===")
    cleaned = report_content or ""

    block_patterns = [
        r"(?ms)^###\s*建议插图清单.*?(?=^\#|\Z)",
        r"(?ms)^###\s*本报告中满足“至少 ?\d+ 张原始图引用”的说明.*?(?=^\#|\Z)",
        r"(?ms)^\*\*图\s*\d+（原始引用[^*]*建议插入：.*?(?=\n\s*\n|\Z)",
        r"(?ms)^\*\*原始图引用\s*#?\d+.*?(?=\n\s*\n|\Z)",
        r"(?ms)^>\s*说明：由于当前写作环境.*?(?=\n\s*\n|\Z)",
    ]
    for pattern in block_patterns:
        cleaned = re.sub(pattern, "", cleaned)

    line_patterns = [
        r"(?im)^\s*#{2,3}\s*图如何支撑分析.*\n?",
        r"(?im)^\s*#{2,3}\s*本报告中满足“至少 ?\d+ 张原始图引用”的说明.*\n?",
        r"(?im)^.*建议插入：.*\n?",
        r"(?im)^.*本节的支撑点是[:：].*\n?",
        r"(?im)^.*支撑点在于[:：].*\n?",
        r"(?im)^.*直接证据价值[:：].*\n?",
        r"(?im)^.*排版时请将下述图.*\n?",
        r"(?im)^.*引用原图（不改动）.*\n?",
    ]
    for pattern in line_patterns:
        cleaned = re.sub(pattern, "", cleaned)

    cleaned = re.sub(r"（原始图引用\s*#?\d+）", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"

    if output_dir and cleaned.strip() != (report_content or "").strip():
        pre_cleanup_path = os.path.join(output_dir, "final_report_pre_cleanup.md")
        with open(pre_cleanup_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    return cleaned


def append_references_section(report_content, learnings_text):
    if re.search(r"(?im)^##\s*(references|参考文献)\s*$", report_content or ""):
        return report_content

    candidates = []
    candidates.extend(_extract_markdown_links(report_content))
    candidates.extend(_extract_arxiv_entries(report_content))
    candidates.extend(_extract_markdown_links(learnings_text))
    candidates.extend(_extract_arxiv_entries(learnings_text))

    unique = []
    seen = set()
    for label, url in candidates:
        normalized = _normalize_reference_url(url)
        if normalized in seen or not _is_reference_candidate(normalized):
            continue
        seen.add(normalized)
        unique.append((label, normalized))

    unique.sort(key=lambda item: (_reference_priority(item[1]), item[1]))
    if not unique:
        return report_content

    lines = ["## 参考文献", ""]
    for idx, (label, url) in enumerate(unique[:20], start=1):
        lines.append(f"{idx}. [{label}]({url})")
    references_block = "\n".join(lines).strip()
    return report_content.rstrip() + "\n\n" + references_block + "\n"


def preprocess_report_for_polish(report_content, output_dir):
    print("=== Preprocessing Final Report For Polish ===")
    preprocessed = cleanup_report_for_publication(report_content, output_dir)

    learnings_path = os.path.join(output_dir, "learnings.txt")
    learnings_text = ""
    if os.path.exists(learnings_path):
        with open(learnings_path, "r", encoding="utf-8") as f:
            learnings_text = f.read()

    preprocessed = append_references_section(preprocessed, learnings_text)
    preprocessed = normalize_report_heading_styles(preprocessed)

    preprocessed_path = os.path.join(output_dir, "final_report_preprocess_for_polish.md")
    with open(preprocessed_path, "w", encoding="utf-8") as f:
        f.write(preprocessed)

    return preprocessed


def polish_final_report(report_content, output_dir, topic_hint=""):
    current_report = report_content
    if ENABLE_REPORT_PREPROCESS:
        current_report = preprocess_report_for_polish(report_content, output_dir)
    if not ENABLE_FINAL_REPORT_POLISH:
        return current_report

    try:
        rewritten = rewrite_report_content(
            current_report,
            output_dir,
            topic_hint=topic_hint,
        )
    except Exception as exc:
        print("=== Final report polish failed; falling back to preprocessed report ===")
        print(f"Polish error: {exc}")
        traceback_text = traceback.format_exc()
        print(traceback_text)

        polish_error_path = os.path.join(output_dir, "final_report_polish_error.log")
        with open(polish_error_path, "w", encoding="utf-8") as f:
            f.write(traceback_text)

        fallback_path = os.path.join(output_dir, "final_report_polish_fallback.md")
        with open(fallback_path, "w", encoding="utf-8") as f:
            f.write(current_report)

        return current_report

    polished_path = os.path.join(output_dir, "final_report_post_rewrite.md")
    with open(polished_path, "w", encoding="utf-8") as f:
        f.write(rewritten)

    return rewritten

def _build_global_image_prompt_block(available_images, max_images, image_selection_mode="semantic"):
    selection_mode = (image_selection_mode or "semantic").strip().lower()
    if available_images:
        cap_line = (
            f"- Usually insert no more than {max_images} source images across the whole report.\n"
            if max_images is not None
            else "- Insert only clearly relevant source images; avoid decorative or repetitive image usage.\n"
        )
        if selection_mode == "weak_metadata":
            hint_line = "- Only weak metadata is available for these source images: alt text, page title, source/domain hint, URL hint, and nearby webpage text."
            grounding_line = "- No OCR, direct image understanding, or model-based image reranking has been performed, so do not infer unseen visual details."
        else:
            hint_line = "- Treat `type`, `source`, `relevance`, `recommended_section`, and `summary` as lightweight hints, not as facts to copy verbatim."
            grounding_line = "- When inserting an image, explain what nearby claim or comparison it supports."
        return f"""
### Optional Source Image Placeholders For This Report
{available_images}

### Additional Source Image Rules
- The list above is the only allowed source-image pool for this full-report generation pass.
- Use only the image IDs listed above. If none are useful, it is acceptable to use no source image in a section.
{hint_line}
{cap_line.strip()}
{grounding_line}
- This image list overrides the generic instruction to insert at least one image per section.
""".strip()
    return """
### Optional Source Image Placeholders For This Report
None

### Additional Source Image Rules
- No approved source-image candidates are available for this full-report generation pass.
- Do not output any [Image_X] placeholder in this report.
""".strip()


def _select_global_image_candidates(
    topic,
    outline,
    image_pool,
    image_metadata,
    pipeline_config,
    output_dir=None,
):
    if not pipeline_config.get("enable_global_image_selection"):
        return "", None
    if not image_pool or not image_metadata:
        if output_dir:
            save_json(
                os.path.join(output_dir, "global_image_selection.json"),
                {
                    "enabled": True,
                    "max_images": pipeline_config.get("max_global_selected_images"),
                    "selected_image_ids": [],
                    "selected_images": [],
                    "available_images_text": "",
                    "reason": "missing_image_pool_or_metadata",
                },
            )
        return "", []

    from .router import route_global_images

    max_images = pipeline_config.get("max_global_selected_images")
    available_images = route_global_images(
        topic,
        outline,
        image_pool,
        image_metadata=image_metadata,
        max_images=max_images,
        selection_mode=pipeline_config.get("image_selection_mode", "semantic"),
    )
    allowed_image_ids = sorted(set(re.findall(r"Image_\d+", available_images)))

    if output_dir:
        metadata_by_id = {
            item.get("image_id"): item for item in (image_metadata or []) if item.get("image_id")
        }
        selected_images = []
        for image_id in allowed_image_ids:
            item = metadata_by_id.get(image_id, {})
            selected_images.append(
                {
                    "image_id": image_id,
                    "figure_type": item.get("figure_type", "unknown"),
                    "source_domain": item.get("source_domain", ""),
                    "recommended_section": item.get("recommended_section", ""),
                    "final_score": item.get("final_score", 0),
                    "topic_relevance_score": item.get("topic_relevance_score", 0),
                    "context_score": item.get("context_score", 0),
                    "summary": item.get("summary", ""),
                    "url": item.get("url", ""),
                }
            )
        save_json(
            os.path.join(output_dir, "global_image_selection.json"),
            {
                "enabled": True,
                "max_images": max_images,
                "selected_image_ids": allowed_image_ids,
                "selected_images": selected_images,
                "available_images_text": available_images,
            },
        )

    return available_images, allowed_image_ids


def generate_draft_report(
    topic,
    outline,
    learnings_str,
    style_guide,
    image_pool=None,
    image_metadata=None,
    pipeline_config=None,
    output_dir=None,
):
    print("=== Generating Draft Report ===")
    pipeline_config = pipeline_config or IMAGE_PIPELINE_CONFIG
    system_prompt = REPORT_GENERATION_SYSTEM_PROMPT.format(list_of_example_reports="")
    user_prompt = REPORT_GENERATION_USER_PROMPT.format(
        topic=topic,
        outline=outline,
        learning_str=learnings_str,
        visualization_style_guide=style_guide
    )
    image_selection_mode = pipeline_config.get("image_selection_mode", "semantic")

    allowed_image_ids = None
    if pipeline_config.get("enable_global_image_selection"):
        available_images, allowed_image_ids = _select_global_image_candidates(
            topic,
            outline,
            image_pool or {},
            image_metadata or [],
            pipeline_config,
            output_dir=output_dir,
        )
        user_prompt += "\n\n" + _build_global_image_prompt_block(
            available_images,
            pipeline_config.get("max_global_selected_images"),
            image_selection_mode=image_selection_mode,
        )
    
    report_content = chat_with_model(GLOBAL_REPORT_LLM_MODEL, system_prompt, user_prompt, max_tokens=6000)
    if allowed_image_ids is not None:
        report_content = prune_ungrounded_images(report_content, allowed_image_ids)
    return report_content

def generate_draft_report_by_section(
    topic,
    outline,
    learnings_str,
    image_pool,
    style_guide,
    image_metadata=None,
    pipeline_config=None,
    output_dir=None,
    learning_id_map=None,
):
    from .router import (
        parse_outline,
        route_learnings,
        route_images,
        route_images_from_ranked,
        route_images_legacy_true_only,
    )
    
    print("=== Generating Draft Report By Section (Webweaver/STORM approach) ===")
    pipeline_config = pipeline_config or IMAGE_PIPELINE_CONFIG
    
    sections = parse_outline(outline)
    if len(sections) <= 1:
        print("Outline could not be parsed into sections. Falling back to global generation.")
        return generate_draft_report(
            topic,
            outline,
            learnings_str,
            style_guide,
            image_pool=image_pool,
            image_metadata=image_metadata,
            pipeline_config=pipeline_config,
            output_dir=output_dir,
        )
        
    final_draft_parts = []
    used_images = set()
    used_dedup_keys = set()
    globally_approved_ids = {
        item.get("image_id") for item in (image_metadata or []) if item.get("should_use") and item.get("image_id")
    }
    section_image_selection_chain = (pipeline_config.get("section_image_selection_chain", "rerank") or "rerank").strip().lower()
    image_selection_mode = (pipeline_config.get("image_selection_mode", "semantic") or "semantic").strip().lower()
    
    for i, section in enumerate(sections):
        print(f"--- Generating Section {i+1}/{len(sections)}: {section['title']} ---")
        
        sec_learnings = route_learnings(section, learnings_str, id_map=learning_id_map)
        ranked_images = []
        strict_image_grounding = pipeline_config.get("enable_strict_image_prompt", False)
        preferred_max_original_images = None
        if image_selection_mode == "weak_metadata":
            weak_max_images = pipeline_config.get("max_weak_metadata_selected_images_per_section", 1)
            sec_images = route_images(
                section,
                image_pool,
                used_images,
                image_metadata=image_metadata,
                max_images=weak_max_images,
                selection_mode=image_selection_mode,
            )
            strict_image_grounding = True
            preferred_max_original_images = weak_max_images
        elif section_image_selection_chain == "legacy_true_only":
            sec_images = route_images_legacy_true_only(
                section,
                image_pool,
                used_images,
                image_metadata=image_metadata,
                max_images=pipeline_config.get("max_legacy_selected_images_per_section", 1),
            )
            strict_image_grounding = True
            preferred_max_original_images = pipeline_config.get("max_legacy_selected_images_per_section", 1)
        elif pipeline_config.get("enable_image_reranking") and image_metadata:
            ranked_images = rank_images_for_section(
                section=section,
                sec_learnings=sec_learnings,
                image_pool=image_pool,
                image_metadata=image_metadata,
                used_images=used_images,
                used_dedup_keys=used_dedup_keys,
                max_images=pipeline_config.get("max_images_per_section", 2),
                output_dir=output_dir,
                enable_dedup=pipeline_config.get("enable_image_dedup", True),
            )
            sec_images = route_images_from_ranked(ranked_images)
            preferred_max_original_images = pipeline_config.get("max_images_per_section", 2)
        else:
            sec_images = route_images(
                section,
                image_pool,
                used_images,
                image_metadata=image_metadata,
                max_images=4,
                selection_mode=image_selection_mode,
            )
            preferred_max_original_images = 2
        
        system_prompt = REPORT_GENERATION_SYSTEM_PROMPT.format(list_of_example_reports="")
        user_prompt = build_section_prompt(
            topic=topic,
            section=section,
            style_guide=style_guide,
            sec_learnings=sec_learnings,
            sec_images=sec_images,
            strict_image_grounding=strict_image_grounding,
            image_selection_mode=image_selection_mode,
            evidence_gap=section.get("gap"),
            preferred_max_original_images=preferred_max_original_images,
        )
        
        section_content = chat_with_model(REPORT_LLM_MODEL, system_prompt, user_prompt, max_tokens=3000)
        section_content = _strip_leading_duplicate_section_heading(section_content, section["title"])
        allowed_ids = sorted(set(re.findall(r"Image_\d+", sec_images)))
        if allowed_ids:
            section_content = prune_ungrounded_images(section_content, allowed_ids)
        else:
            section_content = prune_ungrounded_images(section_content, [])

        if globally_approved_ids:
            section_content = prune_ungrounded_images(section_content, sorted(globally_approved_ids))
        section_content = re.sub(
            r"(?is)#{2,3}\s*附页：材料与溯源.*?(?=(?:\n## |\Z))",
            "",
            section_content,
        )
        section_content = re.sub(
            r"(?is)#{2,3}\s*.*材料与溯源.*?(?=(?:\n## |\n### |\Z))",
            "",
            section_content,
        )
        section_content = re.sub(
            r"(?is)###\s*\d+\)\s*材料与溯源.*?(?=(?:\n### |\n## |\Z))",
            "",
            section_content,
        )
        section_content = re.sub(r"\n{3,}", "\n\n", section_content).strip()

        if pipeline_config.get("enable_image_grounding_check") and ranked_images:
            allowed_ids = [item["image_id"] for item in ranked_images]
            section_content = prune_ungrounded_images(section_content, allowed_ids)
            grounding_result = check_section_grounding(
                section["title"],
                section_content,
                ranked_images,
                output_dir=output_dir,
            )
            if not grounding_result.get("pass"):
                print(f"Grounding issues detected for section `{section['title']}`: {grounding_result['issues']}")

        used_matches = re.findall(r'(Image_\d+)', section_content)

        seen_in_section = set()
        def deduplicate_repl(match):
            img_id = match.group(1)

            if img_id in seen_in_section:
                return ""
            seen_in_section.add(img_id)
            return match.group(0)

        section_content = re.sub(r'\[(Image_\d+)(?::[^\]]*)?\]', deduplicate_repl, section_content)

        used_images.update(used_matches)

        if pipeline_config.get("enable_image_dedup") and ranked_images:
            for item in ranked_images:
                if item["image_id"] in used_matches:
                    used_dedup_keys.add(item.get("dedup_key", item["image_id"]))
        
        final_draft_parts.append(f"## {section['title']}\n\n{section_content}")
        
    full_draft_report = "\n\n".join(final_draft_parts)
    return full_draft_report

def generate_chart(fdv, output_dir, chart_idx):
    print(f"=== Generating Chart {chart_idx} ===")
    os.makedirs(output_dir, exist_ok=True)
    html_file = f"chart_{chart_idx}.html"
    html_path = os.path.join(output_dir, html_file)
    

    prompt = CHART_ACTOR_USER_PROMPT.format(chart_design=fdv)
    response = chat_with_model(CHART_ACTOR_MODEL, CHART_ACTOR_SYSTEM_PROMPT, prompt)
    html_code = extract_code(response, "html")
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_code)
        
    generated_charts = [html_code]
    satisfied = False
    

    for attempt in range(MAX_RETRIES):
        print(f"--- Chart {chart_idx} Refinement Attempt {attempt+1}/{MAX_RETRIES} ---")
        
        # Force-save the current iteration output for screenshots and validation
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_code)

        screenshot_path, error_message, w, h = render_page(output_dir, html_file, output_dir)
        
        if not screenshot_path or not os.path.exists(screenshot_path):
            print("Failed to render chart screenshot. Skipping refinement.")
            break
            

        critic_prompt = CHART_CRITIC_USER_PROMPT.format(console_message=error_message)
        feedback = chat_with_image(CHART_CRITIC_MLLM_MODEL, CHART_CRITIC_SYSTEM_PROMPT, critic_prompt, screenshot_path)
        template_issue = _detect_template_chart_issue(html_code, fdv)
        if template_issue:
            if feedback:
                feedback = f"{template_issue}\n\n{feedback}"
            else:
                feedback = template_issue
                
        if (not template_issue) and ("No issues found." in feedback or "no issues found" in feedback.lower()):
            print("Critic is satisfied with the chart.")
            satisfied = True
            break
            
        print(f"Critic Feedback: {feedback}")
        

        regen_prompt = CHART_REGEN_USER_PROMPT.format(
            chart_design=fdv,
            current_html=html_code,
            feedback=feedback,
        )
        response = chat_with_model(CHART_ACTOR_MODEL, CHART_ACTOR_SYSTEM_PROMPT, regen_prompt)
        if not response:
            print("Failed to get code from model, skipping refinement step")
            continue
            
        html_code = extract_code(response, "html")
        generated_charts.append(html_code)
        
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_code)
            

    if not satisfied and len(generated_charts) > 1:
        print("--- Chart Selection (Choosing between last two iterations) ---")
        c1 = generated_charts[-2]
        c2 = generated_charts[-1]
        
        selection_prompt = CHART_SELECTION_USER_PROMPT.format(chart_design=fdv)

        selection_prompt += f"\n\n## Chart 1:\n```html\n{c1}\n```\n\n## Chart 2:\n```html\n{c2}\n```"
        
        selection_response = chat_with_model(CHART_ACTOR_MODEL, CHART_SELECTION_SYSTEM_PROMPT, selection_prompt)
        print(f"Selection Decision:\n{selection_response}")
        
        if "<selection>first</selection>" in selection_response.lower() or "first" in selection_response.lower().split("<selection>")[-1]:
            best_code = c1
        else:
            best_code = c2
            
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(best_code)
            
    return html_file

def process_report(report_content, output_dir, topic_hint=""):
    replacements = _collect_visualization_replacements(report_content)

    final_report = report_content

    active_replacements = replacements
    skipped_replacements = []
    if MAX_GENERATED_CHARTS is not None:
        active_replacements = replacements[:MAX_GENERATED_CHARTS]
        skipped_replacements = replacements[MAX_GENERATED_CHARTS:]
        if skipped_replacements:
            print(
                f"Visualization limit reached: generating {len(active_replacements)} chart(s) "
                f"and dropping {len(skipped_replacements)} extra visualization block(s)."
            )

    for i, (raw_block, fdv) in enumerate(active_replacements):
        html_filename = generate_chart(fdv, output_dir, i)

        iframe_tag = f'\n<HTMLRenderer htmlFile="{html_filename}" />\n'
        final_report = final_report.replace(raw_block, iframe_tag, 1)

    for raw_block, _ in skipped_replacements:
        final_report = final_report.replace(raw_block, "", 1)

    # Remove stray visualization tags that do not contain a valid JSON spec.
    final_report = re.sub(r"(?im)^\s*</?visualization>\s*$", "", final_report)
    final_report = re.sub(r"(?is)<visualization>\s*(?=(?:##|###|#|\Z))", "", final_report)
    final_report = re.sub(r"\n{3,}", "\n\n", final_report)
        
    mapping_path = os.path.join(output_dir, "images_mapping.json")
    if os.path.exists(mapping_path):
        with open(mapping_path, "r", encoding="utf-8") as f:
            image_mapping = json.load(f)

        def img_repl(match):
            img_id = match.group(1)
            if img_id in image_mapping:
                url = image_mapping[img_id]
                return f"\n\n![{img_id}]({url})\n\n"
            return match.group(0)
            
        final_report = re.sub(r'\[(Image_\d+)(?::[^\]]*)?\]', img_repl, final_report)

    final_report = polish_final_report(final_report, output_dir, topic_hint=topic_hint)
    final_report = _convert_links_to_numbered_citations(final_report)
    final_report = _inline_source_attribution_lines(final_report)
        
    report_path = os.path.join(output_dir, "final_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
        
    print(f"=== Final report saved to {report_path} ===")
    return final_report
