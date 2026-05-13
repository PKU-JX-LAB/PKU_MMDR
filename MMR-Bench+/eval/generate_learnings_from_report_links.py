#!/usr/bin/env python
"""Generate learnings from links cited in final reports.

This approximates the paper's research-stage learnings generation by:
1. Extracting external links from each report
2. Fetching source contents from those links
3. Summarizing the fetched contents with the paper's learning-generation prompt
4. Writing `learnings.md` files and an updated manifest with `learnings_path`
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

from paper_eval import call_chat_completions


LEARNING_GENERATION_PROMPT = """
Given the following contents from a SERP search for the query<query>{query}</query>, generate a list of learnings from the contents.
Return a maximum of {learning_num} learnings, but feel free to return less if the contents are clear. Make sure each learning is unique and not similar to each other. The learnings should be concise and to the point, as detailed and information dense as possible.
Please seamlessly incorporate references to external sources using Markdown hyperlinks.
Make sure to include any entities like people, places, companies, products, things, etc in the learnings, as well as any exact metrics, numbers, or dates. The learnings will be used to research the topic further.
Extract all meaningful data available in the contents, including any tables or lists, and explictly contain them in the learnings.
In addition, return a list of follow-up questions to research the topic further, max of {question_num}.
<contents>
{contents}
</contents>
""".strip()

LEARNING_SYSTEM_PROMPT = (
    "You are an expert researcher who extracts information-dense learnings from web contents."
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def slugify_url(url: str) -> str:
    cleaned = re.sub(r"^https?://", "", url.strip())
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned)
    return cleaned[:120].strip("_") or "source"


def build_cache_filename(idx: int, url: str) -> str:
    slug = slugify_url(url)
    short_slug = slug[:32].rstrip("._-") or "source"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"{idx:02d}_{short_slug}_{digest}.txt"


def extract_links_from_markdown(text: str) -> list[str]:
    urls = re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)\)", text)
    bare_urls = re.findall(r"(?<!\()https?://[^\s)>]+", text)
    ordered: list[str] = []
    seen = set()
    for url in urls + bare_urls:
        normalized = url.rstrip(".,);]")
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def trim_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + f"\n\n[TRUNCATED AFTER {max_chars} CHARACTERS]"


def fetch_url(url: str, timeout: int) -> tuple[str, str]:
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except requests.exceptions.SSLError:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            verify=False,
            headers=REQUEST_HEADERS,
        )
        response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    final_url = response.url
    if "pdf" in content_type or final_url.lower().endswith(".pdf"):
        if PdfReader is None:
            raise RuntimeError("PDF extraction requires the `pypdf` package.")
        reader = PdfReader(io.BytesIO(response.content))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        return final_url, text

    response.encoding = response.encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.extract()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        meta = meta_tag["content"].strip()

    body_text = soup.get_text("\n", strip=True)
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if meta:
        parts.append(f"Description: {meta}")
    if body_text:
        parts.append("Body:\n" + body_text)
    return final_url, "\n\n".join(parts).strip()


def build_contents_bundle(
    source_records: list[dict[str, str]],
    *,
    max_total_chars: int,
    max_chars_per_source: int,
) -> str:
    pieces: list[str] = []
    total = 0
    for idx, record in enumerate(source_records, start=1):
        content = trim_text(record["content"], max_chars_per_source)
        block = (
            f"## Source {idx}\n"
            f"Original URL: {record['original_url']}\n"
            f"Resolved URL: {record['resolved_url']}\n"
            f"Content:\n{content}"
        )
        if max_total_chars > 0 and total + len(block) > max_total_chars:
            remaining = max_total_chars - total
            if remaining <= 0:
                break
            block = trim_text(block, remaining)
        pieces.append(block)
        total += len(block)
        if max_total_chars > 0 and total >= max_total_chars:
            break
    return "\n\n".join(pieces).strip()


def generate_learnings_text(
    *,
    api_key: str,
    base_url: str,
    model: str,
    topic: str,
    contents: str,
    learning_num: int,
    question_num: int,
    max_tokens: int,
) -> str:
    prompt = LEARNING_GENERATION_PROMPT.format(
        query=topic,
        learning_num=learning_num,
        question_num=question_num,
        contents=contents,
    )
    return call_chat_completions(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=LEARNING_SYSTEM_PROMPT,
        user_content=[{"type": "text", "text": prompt}],
        temperature=0.0,
        max_tokens=max_tokens,
    )


def process_report(
    report_spec: dict[str, Any],
    *,
    links_dir: Path,
    learnings_dir: Path,
    api_key: str | None,
    base_url: str | None,
    model: str,
    max_links_per_report: int,
    max_chars_per_source: int,
    max_total_chars: int,
    timeout: int,
    learning_num: int,
    question_num: int,
    max_tokens: int,
    fetch_only: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report_id = report_spec["report_id"]
    report_path = Path(report_spec["report_path"]).resolve()
    text = report_path.read_text(encoding="utf-8", errors="ignore")
    links = extract_links_from_markdown(text)
    if max_links_per_report > 0:
        links = links[:max_links_per_report]

    report_links_dir = links_dir / report_id
    report_links_dir.mkdir(parents=True, exist_ok=True)
    source_records = []
    failures = []
    for idx, url in enumerate(links, start=1):
        try:
            resolved_url, content = fetch_url(url, timeout)
            cache_path = report_links_dir / build_cache_filename(idx, url)
            cache_path.write_text(content, encoding="utf-8")
            source_records.append(
                {
                    "original_url": url,
                    "resolved_url": resolved_url,
                    "content": content,
                    "cache_path": str(cache_path.resolve()),
                }
            )
        except Exception as exc:  # pragma: no cover - network dependent
            failures.append({"url": url, "error": str(exc)})

    learnings_path = learnings_dir / report_id / "learnings.md"
    learnings_path.parent.mkdir(parents=True, exist_ok=True)
    contents_bundle = build_contents_bundle(
        source_records,
        max_total_chars=max_total_chars,
        max_chars_per_source=max_chars_per_source,
    )

    if fetch_only:
        learnings_text = contents_bundle
    else:
        if not api_key or not base_url:
            raise RuntimeError("API key and base URL are required unless --fetch-only is used.")
        learnings_text = generate_learnings_text(
            api_key=api_key,
            base_url=base_url,
            model=model,
            topic=report_spec["topic"],
            contents=contents_bundle,
            learning_num=learning_num,
            question_num=question_num,
            max_tokens=max_tokens,
        )
    learnings_path.write_text(learnings_text + "\n", encoding="utf-8")

    updated_spec = dict(report_spec)
    updated_spec["learnings_path"] = str(learnings_path.resolve())
    meta = {
        "report_id": report_id,
        "report_path": str(report_path),
        "link_count": len(links),
        "fetched_count": len(source_records),
        "failure_count": len(failures),
        "failures": failures,
        "learnings_path": str(learnings_path.resolve()),
        "source_records": [
            {
                "original_url": record["original_url"],
                "resolved_url": record["resolved_url"],
                "cache_path": record["cache_path"],
            }
            for record in source_records
        ],
    }
    return updated_spec, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate learnings from report-cited links.")
    parser.add_argument("--manifest", required=True, help="Input single-report manifest JSON.")
    parser.add_argument("--output-manifest", required=True, help="Output manifest JSON with learnings_path fields.")
    parser.add_argument("--learnings-dir", required=True, help="Directory to write generated learnings.")
    parser.add_argument("--links-dir", required=True, help="Directory to cache fetched source texts.")
    parser.add_argument("--report-meta", required=True, help="Path to save per-report fetch metadata JSON.")
    parser.add_argument("--model", default="gpt-5.3-codex")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-reports", type=int, default=0, help="0 means all reports.")
    parser.add_argument("--max-links-per-report", type=int, default=8)
    parser.add_argument("--max-chars-per-source", type=int, default=20000)
    parser.add_argument("--max-total-chars", type=int, default=120000)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--learning-num", type=int, default=12)
    parser.add_argument("--question-num", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=3000)
    parser.add_argument("--fetch-only", action="store_true", help="Fetch and cache sources without calling the model.")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest).resolve())
    reports = manifest.get("reports", [])
    if args.max_reports > 0:
        reports = reports[: args.max_reports]

    links_dir = Path(args.links_dir).resolve()
    learnings_dir = Path(args.learnings_dir).resolve()
    updated_reports = []
    metas = []

    for idx, report_spec in enumerate(reports, start=1):
        print(f"[{idx}/{len(reports)}] Processing {report_spec['report_id']}")
        updated_spec, meta = process_report(
            report_spec,
            links_dir=links_dir,
            learnings_dir=learnings_dir,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
            max_links_per_report=args.max_links_per_report,
            max_chars_per_source=args.max_chars_per_source,
            max_total_chars=args.max_total_chars,
            timeout=args.timeout,
            learning_num=args.learning_num,
            question_num=args.question_num,
            max_tokens=args.max_tokens,
            fetch_only=args.fetch_only,
        )
        updated_reports.append(updated_spec)
        metas.append(meta)

    output_manifest = dict(manifest)
    output_manifest["reports"] = updated_reports
    output_manifest.setdefault("meta", {})
    output_manifest["meta"]["learnings_generated"] = True
    output_manifest["meta"]["fetch_only"] = args.fetch_only
    save_json(Path(args.output_manifest).resolve(), output_manifest)
    save_json(Path(args.report_meta).resolve(), metas)
    print(f"Saved manifest to {Path(args.output_manifest).resolve()}")
    print(f"Saved metadata to {Path(args.report_meta).resolve()}")


if __name__ == "__main__":
    main()
