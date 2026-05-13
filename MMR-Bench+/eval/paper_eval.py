#!/usr/bin/env python
"""Paper-faithful evaluation scaffold for Multimodal DeepResearcher."""

from __future__ import annotations

import argparse
import base64
import csv
import glob
import json
import mimetypes
import os
import random
import re
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

import requests

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


REPORT_METRICS = [
    "informativeness_and_depth",
    "coherence_and_organization",
    "verifiability",
    "visualization_quality",
    "visualization_consistency",
]

EVALUATION_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = EVALUATION_DIR / "prompts"
DEFAULT_REPORT_PROMPT_PATH = PROMPTS_DIR / "report_pairwise_default.txt"
DEFAULT_SINGLE_REPORT_PROMPT_PATH = PROMPTS_DIR / "report_single_default.txt"
DEFAULT_CHART_PROMPT_PATH = PROMPTS_DIR / "chart_default.txt"

CHART_METRICS = [
    "readability",
    "layout",
    "aesthetics",
    "data_faithfulness",
    "goal_compliance",
]

METRIC_LABELS = {
    "informativeness_and_depth": "Informativeness and Depth",
    "coherence_and_organization": "Coherence and Organization",
    "verifiability": "Verifiability",
    "visualization_quality": "Visualization Quality",
    "visualization_consistency": "Visualization Consistency",
    "original_image_integration": "Original Image Integration",
    "readability": "Readability",
    "layout": "Layout",
    "aesthetics": "Aesthetics",
    "data_faithfulness": "Data Faithfulness",
    "goal_compliance": "Goal Compliance",
}

TAG_ALIASES = {
    "evaluation": ["evaluation"],
    "report": ["report"],
    "report_a": ["report_a", "report a"],
    "report_b": ["report_b", "report b"],
    "score": ["score"],
    "justification": ["justification"],
    "informativeness_and_depth": ["informativeness_and_depth", "informativeness"],
    "coherence_and_organization": ["coherence_and_organization", "coherence"],
    "verifiability": ["verifiability"],
    "visualization_quality": ["visualization_quality", "visualization quality"],
    "visualization_consistency": [
        "visualization_consistency",
        "visualization consistency",
    ],
    "original_image_integration": [
        "original_image_integration",
        "original image integration",
    ],
    "readability": ["readability"],
    "layout": ["layout"],
    "aesthetics": ["aesthetics"],
    "data_faithfulness": ["data_faithfulness", "data faithfulness"],
    "goal_compliance": ["goal_compliance", "goal compliance"],
}

def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".mdx", ".json", ".html", ".csv"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError("Reading PDF reports requires the `pypdf` package.")
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
    raise ValueError(f"Unsupported text file type: {path}")


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def resolve_prompt_path(path_value: str | None, default_path: Path) -> Path:
    if not path_value:
        return default_path
    prompt_path = Path(path_value)
    if not prompt_path.is_absolute():
        prompt_path = (Path.cwd() / prompt_path).resolve()
    return prompt_path


def load_prompt_schema(prompt_path: Path) -> dict[str, Any]:
    schema_path = prompt_path.with_suffix(".json")
    if not schema_path.exists():
        return {}
    return load_json(schema_path)


def resolve_report_metrics(prompt_path: Path) -> list[str]:
    schema = load_prompt_schema(prompt_path)
    metrics = schema.get("report_metrics")
    if not metrics:
        return REPORT_METRICS[:]
    return [str(metric) for metric in metrics]


def resolve_chart_metrics(prompt_path: Path) -> list[str]:
    schema = load_prompt_schema(prompt_path)
    metrics = schema.get("chart_metrics")
    if not metrics:
        return CHART_METRICS[:]
    return [str(metric) for metric in metrics]


def trim_text(value: str, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    clipped = value[:max_chars].rstrip()
    return f"{clipped}\n\n[TRUNCATED AFTER {max_chars} CHARACTERS]"


def resolve_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def resolve_image_paths(root: Path, payload: dict[str, Any], limit: int) -> list[Path]:
    images: list[Path] = []
    for image_path in payload.get("image_paths", []):
        resolved = resolve_path(root, image_path)
        if resolved:
            images.append(resolved)

    images_dir = resolve_path(root, payload.get("images_dir"))
    if images_dir and images_dir.exists():
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            images.extend(sorted(images_dir.glob(ext)))

    image_glob = payload.get("image_glob")
    if image_glob:
        images.extend(sorted(root.glob(image_glob)))

    unique: list[Path] = []
    seen = set()
    for image in images:
        key = str(image.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(image)
        if limit and len(unique) >= limit:
            break
    return unique


def resolve_named_image_paths(
    root: Path,
    payload: dict[str, Any],
    key: str,
    limit: int,
) -> list[Path]:
    images: list[Path] = []
    for image_path in payload.get(key, []):
        resolved = resolve_path(root, image_path)
        if resolved:
            images.append(resolved)

    unique: list[Path] = []
    seen = set()
    for image in images:
        resolved_key = str(image.resolve())
        if resolved_key in seen:
            continue
        seen.add(resolved_key)
        unique.append(image)
        if limit and len(unique) >= limit:
            break
    return unique


def encode_image_as_data_url(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def normalize_output(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:xml)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_tag_block(text: str, tag_key: str) -> str:
    aliases = TAG_ALIASES[tag_key]
    for alias in aliases:
        pattern = re.compile(
            rf"<{re.escape(alias)}>\s*(.*?)\s*</{re.escape(alias)}>",
            flags=re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    raise ValueError(f"Could not locate tag `{tag_key}` in judge response.")


def maybe_extract_tag_block(text: str, tag_key: str) -> str | None:
    try:
        return extract_tag_block(text, tag_key)
    except ValueError:
        return None


def parse_score(block: str) -> float:
    score_block = extract_tag_block(block, "score")
    match = re.search(r"-?\d+(?:\.\d+)?", score_block)
    if not match:
        raise ValueError(f"Could not parse numeric score from `{score_block}`.")
    return float(match.group(0))


def parse_report_response(
    raw_text: str,
    report_metrics: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    text = normalize_output(raw_text)
    report_data: dict[str, dict[str, dict[str, Any]]] = {}
    for report_key in ("report_a", "report_b"):
        report_block = extract_tag_block(text, report_key)
        metrics: dict[str, dict[str, Any]] = {}
        for metric in report_metrics:
            metric_block = extract_tag_block(report_block, metric)
            metrics[metric] = {
                "score": parse_score(metric_block),
                "justification": maybe_extract_tag_block(metric_block, "justification") or "",
            }
        report_data[report_key] = metrics
    return report_data


def parse_chart_response(
    raw_text: str,
    chart_metrics: list[str],
) -> dict[str, dict[str, Any]]:
    text = normalize_output(raw_text)
    result: dict[str, dict[str, Any]] = {}
    for metric in chart_metrics:
        metric_block = extract_tag_block(text, metric)
        result[metric] = {
            "score": parse_score(metric_block),
            "justification": maybe_extract_tag_block(metric_block, "justification") or "",
        }
    return result


def parse_single_report_response(
    raw_text: str,
    report_metrics: list[str],
) -> dict[str, dict[str, Any]]:
    text = normalize_output(raw_text)
    report_block = extract_tag_block(text, "report")
    metrics: dict[str, dict[str, Any]] = {}
    for metric in report_metrics:
        metric_block = extract_tag_block(report_block, metric)
        metrics[metric] = {
            "score": parse_score(metric_block),
            "justification": maybe_extract_tag_block(metric_block, "justification") or "",
        }
    return metrics


def compare_scores(a_score: float, b_score: float, tolerance: float = 1e-9) -> str:
    if abs(a_score - b_score) <= tolerance:
        return "tie"
    return "a" if a_score > b_score else "b"


def mean_score(metric_payload: dict[str, dict[str, Any]], metrics: list[str]) -> float:
    return mean(metric_payload[metric]["score"] for metric in metrics)


def get_api_key(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable `{env_name}` is not set.")
    return value


def join_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def call_chat_completions(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_content: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> str:
    return call_chat_completions_streaming(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        user_content=user_content,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def call_chat_completions_streaming(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_content: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> str:
    url = f"{join_base_url(base_url)}/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    max_attempts = 5
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        chunks: list[str] = []
        try:
            with requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=300,
                verify=False,
            ) as response:
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:
                    status_code = response.status_code
                    if status_code in {400, 401, 403, 404}:
                        raise
                    raise RuntimeError(
                        f"Transient HTTP {status_code} from judge model endpoint."
                    ) from exc
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line or not raw_line.startswith("data: "):
                        continue
                    data = raw_line[6:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        piece = delta.get("content")
                        if isinstance(piece, str) and piece:
                            chunks.append(piece)
            merged = "".join(chunks).strip()
            if not merged:
                raise RuntimeError("Streaming fallback returned no text content.")
            return merged
        except (
            requests.RequestException,
            RuntimeError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            delay = min(20.0, 2.0 * attempt) + random.uniform(0.0, 1.0)
            eprint(
                f"Model call attempt {attempt}/{max_attempts} failed: {exc}. "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)
    if last_error is None:
        raise RuntimeError("Model call failed for an unknown reason.")
    raise last_error


def build_report_user_content(
    *,
    topic: str,
    learnings_text: str,
    report_a_text: str,
    report_a_images: list[Path],
    report_a_source_images: list[Path],
    report_a_generated_images: list[Path],
    report_b_text: str,
    report_b_images: list[Path],
    report_b_source_images: list[Path],
    report_b_generated_images: list[Path],
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": textwrap.dedent(
                f"""
                ## Topic
                {topic}

                ## Learnings
                {learnings_text}
                """
            ).strip(),
        },
        {"type": "text", "text": f"<report_a>\n{report_a_text}\n</report_a>"},
    ]
    if report_a_source_images:
        content.append(
            {
                "type": "text",
                "text": "The following images for report_a are original/source images inserted into the report.",
            }
        )
        for image_path in report_a_source_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_as_data_url(image_path),
                        "detail": "high",
                    },
                }
            )
    if report_a_generated_images:
        content.append(
            {
                "type": "text",
                "text": "The following images for report_a are generated charts or rendered report visuals, not original/source images.",
            }
        )
        for image_path in report_a_generated_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_as_data_url(image_path),
                        "detail": "high",
                    },
                }
            )
    remaining_a = [
        path for path in report_a_images
        if str(path.resolve()) not in {str(p.resolve()) for p in report_a_source_images + report_a_generated_images}
    ]
    for image_path in remaining_a:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": encode_image_as_data_url(image_path),
                    "detail": "high",
                },
            }
        )
    content.append({"type": "text", "text": f"<report_b>\n{report_b_text}\n</report_b>"})
    if report_b_source_images:
        content.append(
            {
                "type": "text",
                "text": "The following images for report_b are original/source images inserted into the report.",
            }
        )
        for image_path in report_b_source_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_as_data_url(image_path),
                        "detail": "high",
                    },
                }
            )
    if report_b_generated_images:
        content.append(
            {
                "type": "text",
                "text": "The following images for report_b are generated charts or rendered report visuals, not original/source images.",
            }
        )
        for image_path in report_b_generated_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_as_data_url(image_path),
                        "detail": "high",
                    },
                }
            )
    remaining_b = [
        path for path in report_b_images
        if str(path.resolve()) not in {str(p.resolve()) for p in report_b_source_images + report_b_generated_images}
    ]
    for image_path in remaining_b:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": encode_image_as_data_url(image_path),
                    "detail": "high",
                },
            }
        )
    return content


def build_chart_user_content(*, chart_id: str, design_spec: str, image_path: Path) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": textwrap.dedent(
                f"""
                ## Chart ID
                {chart_id}

                ## Design Specification
                {design_spec}
                """
            ).strip(),
        },
        {
            "type": "image_url",
            "image_url": {
                "url": encode_image_as_data_url(image_path),
                "detail": "high",
            },
        },
    ]


def build_single_report_user_content(
    *,
    topic: str,
    learnings_text: str | None,
    report_text: str,
    report_images: list[Path],
    source_images: list[Path],
    generated_images: list[Path],
) -> list[dict[str, Any]]:
    intro = f"## Topic\n{topic}\n"
    if learnings_text:
        intro += f"\n## Learnings\n{learnings_text}\n"
    content: list[dict[str, Any]] = [
        {"type": "text", "text": intro.strip()},
        {"type": "text", "text": f"<report>\n{report_text}\n</report>"},
    ]
    if source_images:
        content.append(
            {
                "type": "text",
                "text": "The following images are original/source images inserted into the report.",
            }
        )
        for image_path in source_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_as_data_url(image_path),
                        "detail": "high",
                    },
                }
            )
    if generated_images:
        content.append(
            {
                "type": "text",
                "text": "The following images are generated charts or rendered report visuals, not original/source images.",
            }
        )
        for image_path in generated_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_as_data_url(image_path),
                        "detail": "high",
                    },
                }
            )
    remaining = [
        path for path in report_images
        if str(path.resolve()) not in {str(p.resolve()) for p in source_images + generated_images}
    ]
    for image_path in remaining:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": encode_image_as_data_url(image_path),
                    "detail": "high",
                },
            }
        )
    return content


def summarize_pair_results(pair_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not pair_results:
        return {"metric_stats": {}, "raw_score_means": {}}

    systems = pair_results[0]["systems"]
    report_metrics = pair_results[0]["report_metrics"]
    system_a = systems[0]
    system_b = systems[1]
    metric_stats: dict[str, Any] = {}

    for metric in report_metrics + ["overall"]:
        a_wins = 0
        b_wins = 0
        ties = 0
        for pair_result in pair_results:
            winner = pair_result["winners"][metric]
            if winner == system_a:
                a_wins += 1
            elif winner == system_b:
                b_wins += 1
            else:
                ties += 1
        total = len(pair_results)
        metric_stats[metric] = {
            f"{system_a}_win_pct": round(a_wins * 100.0 / total, 2),
            f"{system_b}_win_pct": round(b_wins * 100.0 / total, 2),
            "tie_pct": round(ties * 100.0 / total, 2),
            "counts": {system_a: a_wins, system_b: b_wins, "tie": ties},
        }

    raw_score_means: dict[str, dict[str, float]] = {}
    for system_name in systems:
        raw_score_means[system_name] = {}
        for metric in report_metrics:
            scores = [pair["scores"][system_name][metric]["score"] for pair in pair_results]
            raw_score_means[system_name][metric] = round(mean(scores), 4)
        overall_scores = [pair["overall_scores"][system_name] for pair in pair_results]
        raw_score_means[system_name]["overall"] = round(mean(overall_scores), 4)

    return {"metric_stats": metric_stats, "raw_score_means": raw_score_means}


def summarize_chart_results(report_results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for report_result in report_results:
        grouped.setdefault(report_result["system"], []).append(report_result)

    chart_metrics = report_results[0]["chart_metrics"] if report_results else []
    summary: dict[str, dict[str, float]] = {}
    for system_name, items in grouped.items():
        summary[system_name] = {}
        for metric in chart_metrics:
            report_means = [item["metric_means"][metric] for item in items]
            summary[system_name][metric] = round(mean(report_means), 4)
    return {"system_report_mean_scores": summary}


def summarize_single_report_results(report_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not report_results:
        return {"metric_means": {}, "overall_mean": None}

    report_metrics = report_results[0]["report_metrics"]
    metric_means = {}
    for metric in report_metrics:
        metric_means[metric] = round(mean(item["scores"][metric]["score"] for item in report_results), 4)
    overall_mean = round(mean(item["overall_score"] for item in report_results), 4)
    return {"metric_means": metric_means, "overall_mean": overall_mean}


def require_exists(path: Path | None, label: str) -> Path:
    if path is None or not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def evaluate_reports(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    manifest_root = manifest_path.parent
    manifest = load_json(manifest_path)
    pair_specs = manifest.get("pairs", [])
    if not pair_specs:
        raise ValueError("Report manifest must contain a non-empty `pairs` list.")

    api_key = get_api_key(args.api_key_env)
    report_prompt_path = resolve_prompt_path(args.prompt_file, DEFAULT_REPORT_PROMPT_PATH)
    report_system_prompt = load_prompt(report_prompt_path)
    report_metrics = resolve_report_metrics(report_prompt_path)
    rng = random.Random(args.seed)
    pair_results: list[dict[str, Any]] = []

    for index, pair_spec in enumerate(pair_specs, start=1):
        systems = pair_spec.get("systems", [])
        if len(systems) != 2:
            raise ValueError("Each report pair must contain exactly two systems.")

        shuffled = systems[:]
        rng.shuffle(shuffled)
        report_a_spec, report_b_spec = shuffled

        topic = pair_spec["topic"]
        pair_id = pair_spec.get("pair_id", f"pair_{index:03d}")
        learnings_path = require_exists(resolve_path(manifest_root, pair_spec["learnings_path"]), "Learnings path")
        learnings_text = trim_text(load_text(learnings_path), args.max_learnings_chars)

        report_a_path = require_exists(
            resolve_path(manifest_root, report_a_spec.get("report_path") or report_a_spec.get("text_path")),
            "Report A path",
        )
        report_b_path = require_exists(
            resolve_path(manifest_root, report_b_spec.get("report_path") or report_b_spec.get("text_path")),
            "Report B path",
        )

        report_a_text = trim_text(load_text(report_a_path), args.max_report_chars)
        report_b_text = trim_text(load_text(report_b_path), args.max_report_chars)
        report_a_images = resolve_image_paths(manifest_root, report_a_spec, args.max_images_per_report)
        report_b_images = resolve_image_paths(manifest_root, report_b_spec, args.max_images_per_report)
        report_a_source_images = resolve_named_image_paths(
            manifest_root, report_a_spec, "source_image_paths", args.max_images_per_report
        )
        report_a_generated_images = resolve_named_image_paths(
            manifest_root, report_a_spec, "generated_image_paths", args.max_images_per_report
        )
        report_b_source_images = resolve_named_image_paths(
            manifest_root, report_b_spec, "source_image_paths", args.max_images_per_report
        )
        report_b_generated_images = resolve_named_image_paths(
            manifest_root, report_b_spec, "generated_image_paths", args.max_images_per_report
        )

        user_content = build_report_user_content(
            topic=topic,
            learnings_text=learnings_text,
            report_a_text=report_a_text,
            report_a_images=report_a_images,
            report_a_source_images=report_a_source_images,
            report_a_generated_images=report_a_generated_images,
            report_b_text=report_b_text,
            report_b_images=report_b_images,
            report_b_source_images=report_b_source_images,
            report_b_generated_images=report_b_generated_images,
        )

        eprint(f"[report {index}/{len(pair_specs)}] Evaluating {pair_id} with {args.model}")
        raw_response = call_chat_completions(
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
            system_prompt=report_system_prompt,
            user_content=user_content,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        parsed = parse_report_response(raw_response, report_metrics)

        order = {"report_a": report_a_spec["name"], "report_b": report_b_spec["name"]}
        scores: dict[str, dict[str, dict[str, Any]]] = {
            report_a_spec["name"]: parsed["report_a"],
            report_b_spec["name"]: parsed["report_b"],
        }
        systems_order = [systems[0]["name"], systems[1]["name"]]
        overall_scores = {
            report_a_spec["name"]: mean_score(parsed["report_a"], report_metrics),
            report_b_spec["name"]: mean_score(parsed["report_b"], report_metrics),
        }

        winners: dict[str, str] = {}
        for metric in report_metrics:
            metric_winner = compare_scores(
                parsed["report_a"][metric]["score"],
                parsed["report_b"][metric]["score"],
            )
            winners[metric] = (
                order["report_a"] if metric_winner == "a" else order["report_b"] if metric_winner == "b" else "tie"
            )
        overall_winner = compare_scores(
            overall_scores[report_a_spec["name"]],
            overall_scores[report_b_spec["name"]],
        )
        winners["overall"] = (
            order["report_a"] if overall_winner == "a" else order["report_b"] if overall_winner == "b" else "tie"
        )

        pair_results.append(
            {
                "pair_id": pair_id,
                "topic": topic,
                "systems": systems_order,
                "report_metrics": report_metrics,
                "presentation_order": order,
                "scores": scores,
                "overall_scores": overall_scores,
                "winners": winners,
                "artifact_paths": {
                    report_a_spec["name"]: {
                        "report_path": str(report_a_path),
                        "image_paths": [str(path) for path in report_a_images],
                        "source_image_paths": [str(path) for path in report_a_source_images],
                        "generated_image_paths": [str(path) for path in report_a_generated_images],
                    },
                    report_b_spec["name"]: {
                        "report_path": str(report_b_path),
                        "image_paths": [str(path) for path in report_b_images],
                        "source_image_paths": [str(path) for path in report_b_source_images],
                        "generated_image_paths": [str(path) for path in report_b_generated_images],
                    },
                    "learnings_path": str(learnings_path),
                },
                "raw_response": raw_response,
            }
        )
        if args.delay_seconds:
            time.sleep(args.delay_seconds)

    output = {
        "mode": "report_evaluation",
        "paper_alignment": {
            "judge_model": args.model,
            "scoring_scale": "1-5 with 0.5 increments",
            "pairwise": True,
            "randomized_order": True,
            "report_metrics": report_metrics,
        },
        "config": {
            "manifest": str(manifest_path),
            "prompt_file": str(report_prompt_path),
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "seed": args.seed,
            "max_images_per_report": args.max_images_per_report,
            "max_report_chars": args.max_report_chars,
            "max_learnings_chars": args.max_learnings_chars,
        },
        "pair_results": pair_results,
        "summary": summarize_pair_results(pair_results),
    }
    save_json(Path(args.output).resolve(), output)
    eprint(f"Saved report evaluation results to {Path(args.output).resolve()}")


def evaluate_single_reports(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    manifest_root = manifest_path.parent
    manifest = load_json(manifest_path)
    report_specs = manifest.get("reports", [])
    if not report_specs:
        raise ValueError("Single-report manifest must contain a non-empty `reports` list.")

    api_key = get_api_key(args.api_key_env)
    report_prompt_path = resolve_prompt_path(args.prompt_file, DEFAULT_SINGLE_REPORT_PROMPT_PATH)
    report_system_prompt = load_prompt(report_prompt_path)
    report_metrics = resolve_report_metrics(report_prompt_path)
    report_results: list[dict[str, Any]] = []

    for index, report_spec in enumerate(report_specs, start=1):
        report_id = report_spec.get("report_id", f"report_{index:03d}")
        topic = report_spec["topic"]
        report_path = require_exists(
            resolve_path(manifest_root, report_spec.get("report_path") or report_spec.get("text_path")),
            "Report path",
        )
        report_text = trim_text(load_text(report_path), args.max_report_chars)
        report_images = resolve_image_paths(manifest_root, report_spec, args.max_images_per_report)
        source_images = resolve_named_image_paths(
            manifest_root, report_spec, "source_image_paths", args.max_images_per_report
        )
        generated_images = resolve_named_image_paths(
            manifest_root, report_spec, "generated_image_paths", args.max_images_per_report
        )

        learnings_text = None
        learnings_value = report_spec.get("learnings_path")
        if learnings_value:
            learnings_path = require_exists(resolve_path(manifest_root, learnings_value), "Learnings path")
            learnings_text = trim_text(load_text(learnings_path), args.max_learnings_chars)
        else:
            learnings_path = None

        user_content = build_single_report_user_content(
            topic=topic,
            learnings_text=learnings_text,
            report_text=report_text,
            report_images=report_images,
            source_images=source_images,
            generated_images=generated_images,
        )

        eprint(f"[single-report {index}/{len(report_specs)}] Evaluating {report_id} with {args.model}")
        raw_response = call_chat_completions(
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
            system_prompt=report_system_prompt,
            user_content=user_content,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        parsed = parse_single_report_response(raw_response, report_metrics)
        overall_score = mean_score(parsed, report_metrics)

        report_results.append(
            {
                "report_id": report_id,
                "topic": topic,
                "report_metrics": report_metrics,
                "scores": parsed,
                "overall_score": overall_score,
                "artifact_paths": {
                    "report_path": str(report_path),
                    "image_paths": [str(path) for path in report_images],
                    "source_image_paths": [str(path) for path in source_images],
                    "generated_image_paths": [str(path) for path in generated_images],
                    "learnings_path": str(learnings_path) if learnings_path else None,
                },
                "raw_response": raw_response,
            }
        )
        if args.delay_seconds:
            time.sleep(args.delay_seconds)

    output = {
        "mode": "single_report_evaluation",
        "paper_alignment": {
            "derived_from_paper_report_rubric": True,
            "pairwise": False,
            "baseline_required": False,
            "scoring_scale": "1-5 with 0.5 increments",
            "judge_model": args.model,
            "report_metrics": report_metrics,
        },
        "config": {
            "manifest": str(manifest_path),
            "prompt_file": str(report_prompt_path),
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "max_images_per_report": args.max_images_per_report,
            "max_report_chars": args.max_report_chars,
            "max_learnings_chars": args.max_learnings_chars,
        },
        "report_results": report_results,
        "summary": summarize_single_report_results(report_results),
    }
    save_json(Path(args.output).resolve(), output)
    eprint(f"Saved single-report evaluation results to {Path(args.output).resolve()}")


def evaluate_charts(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    manifest_root = manifest_path.parent
    manifest = load_json(manifest_path)
    report_specs = manifest.get("reports", [])
    if not report_specs:
        raise ValueError("Chart manifest must contain a non-empty `reports` list.")

    api_key = get_api_key(args.api_key_env)
    chart_prompt_path = resolve_prompt_path(args.prompt_file, DEFAULT_CHART_PROMPT_PATH)
    chart_system_prompt = load_prompt(chart_prompt_path)
    chart_metrics = resolve_chart_metrics(chart_prompt_path)
    report_results: list[dict[str, Any]] = []

    for report_index, report_spec in enumerate(report_specs, start=1):
        report_id = report_spec["report_id"]
        system_name = report_spec["system"]
        chart_results: list[dict[str, Any]] = []
        charts = report_spec.get("charts", [])
        if not charts:
            raise ValueError(f"Report `{report_id}` does not define any charts.")

        for chart_index, chart_spec in enumerate(charts, start=1):
            chart_id = chart_spec.get("chart_id", f"{report_id}_chart_{chart_index:03d}")
            spec_path = require_exists(resolve_path(manifest_root, chart_spec["spec_path"]), "Chart spec path")
            image_path = require_exists(resolve_path(manifest_root, chart_spec["image_path"]), "Chart image path")
            design_spec = trim_text(load_text(spec_path), args.max_spec_chars)
            user_content = build_chart_user_content(
                chart_id=chart_id,
                design_spec=design_spec,
                image_path=image_path,
            )

            eprint(
                f"[chart {report_index}/{len(report_specs)}:{chart_index}/{len(charts)}] "
                f"Evaluating {report_id} / {chart_id} with {args.model}"
            )
            raw_response = call_chat_completions(
                api_key=api_key,
                base_url=args.base_url,
                model=args.model,
                system_prompt=chart_system_prompt,
                user_content=user_content,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            parsed = parse_chart_response(raw_response, chart_metrics)
            chart_results.append(
                {
                    "chart_id": chart_id,
                    "chart_metrics": chart_metrics,
                    "scores": parsed,
                    "artifact_paths": {
                        "spec_path": str(spec_path),
                        "image_path": str(image_path),
                    },
                    "raw_response": raw_response,
                }
            )
            if args.delay_seconds:
                time.sleep(args.delay_seconds)

        metric_means = {
            metric: round(mean(item["scores"][metric]["score"] for item in chart_results), 4)
            for metric in chart_metrics
        }
        report_results.append(
            {
                "report_id": report_id,
                "pair_id": report_spec.get("pair_id"),
                "topic": report_spec.get("topic"),
                "system": system_name,
                "chart_metrics": chart_metrics,
                "metric_means": metric_means,
                "chart_results": chart_results,
            }
        )

    output = {
        "mode": "chart_evaluation",
        "paper_alignment": {
            "judge_model": args.model,
            "scoring_scale": "1-10",
            "per_chart_scoring": True,
            "report_level_average": True,
            "chart_metrics": chart_metrics,
        },
        "config": {
            "manifest": str(manifest_path),
            "prompt_file": str(chart_prompt_path),
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "max_spec_chars": args.max_spec_chars,
        },
        "report_results": report_results,
        "summary": summarize_chart_results(report_results),
    }
    save_json(Path(args.output).resolve(), output)
    eprint(f"Saved chart evaluation results to {Path(args.output).resolve()}")


def prepare_human_eval(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    manifest_root = manifest_path.parent
    manifest = load_json(manifest_path)
    pair_specs = manifest.get("pairs", [])
    if not pair_specs:
        raise ValueError("Report manifest must contain a non-empty `pairs` list.")

    count = min(args.count, len(pair_specs))
    rng = random.Random(args.seed)
    sampled = rng.sample(pair_specs, count)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    key: dict[str, Any] = {}

    for index, pair_spec in enumerate(sampled, start=1):
        systems = pair_spec["systems"][:]
        rng.shuffle(systems)
        left_spec, right_spec = systems
        pair_id = pair_spec.get("pair_id", f"pair_{index:03d}")

        left_path = require_exists(
            resolve_path(manifest_root, left_spec.get("report_path") or left_spec.get("text_path")),
            "Left report path",
        )
        right_path = require_exists(
            resolve_path(manifest_root, right_spec.get("report_path") or right_spec.get("text_path")),
            "Right report path",
        )

        row = {
            "annotator_id": "",
            "pair_id": pair_id,
            "topic": pair_spec["topic"],
            "learnings_path": str(require_exists(resolve_path(manifest_root, pair_spec["learnings_path"]), "Learnings path")),
            "left_report_path": str(left_path),
            "right_report_path": str(right_path),
        }
        for metric in REPORT_METRICS + ["overall"]:
            row[f"{metric}_choice"] = ""
            row[f"{metric}_comment"] = ""
        rows.append(row)

        key[pair_id] = {
            "topic": pair_spec["topic"],
            "left_system": left_spec["name"],
            "right_system": right_spec["name"],
            "left_report_path": str(left_path),
            "right_report_path": str(right_path),
        }

    assignment_path = out_dir / "human_eval_assignment.csv"
    with assignment_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    key_path = out_dir / "human_eval_key.json"
    save_json(key_path, key)
    eprint(f"Saved human evaluation assignment to {assignment_path}")
    eprint(f"Saved human evaluation key to {key_path}")


def aggregate_human_eval(args: argparse.Namespace) -> None:
    key_path = Path(args.key).resolve()
    key = load_json(key_path)

    annotation_paths = [Path(path).resolve() for path in sorted(glob.glob(args.annotations_glob))]
    if not annotation_paths:
        raise FileNotFoundError(f"No annotation CSV matched glob: {args.annotations_glob}")

    aggregate_counts = {metric: {} for metric in REPORT_METRICS + ["overall"]}
    annotator_preferences: dict[str, dict[str, int]] = {}
    total_rows = 0

    for csv_path in annotation_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                pair_id = row["pair_id"]
                blind_key = key[pair_id]
                annotator_id = row.get("annotator_id", "").strip() or csv_path.stem
                annotator_preferences.setdefault(annotator_id, {})

                for metric in REPORT_METRICS + ["overall"]:
                    choice = row.get(f"{metric}_choice", "").strip().lower()
                    if not choice:
                        continue
                    if choice not in {"left", "right", "tie"}:
                        raise ValueError(
                            f"Invalid choice `{choice}` in {csv_path} for {pair_id} / {metric}. "
                            "Use left, right, or tie."
                        )
                    resolved = (
                        blind_key["left_system"]
                        if choice == "left"
                        else blind_key["right_system"]
                        if choice == "right"
                        else "tie"
                    )
                    aggregate_counts[metric][resolved] = aggregate_counts[metric].get(resolved, 0) + 1
                    if metric == "overall" and resolved != "tie":
                        annotator_preferences[annotator_id][resolved] = (
                            annotator_preferences[annotator_id].get(resolved, 0) + 1
                        )
                total_rows += 1

    summary: dict[str, Any] = {}
    for metric, counts in aggregate_counts.items():
        total = sum(counts.values())
        summary[metric] = {
            "counts": counts,
            "percentages": {
                label: round(value * 100.0 / total, 2) if total else 0.0
                for label, value in counts.items()
            },
        }

    output = {
        "mode": "human_evaluation_aggregation",
        "paper_alignment": {
            "pairwise": True,
            "same_metrics_as_report_eval": True,
            "intended_annotator_count": 5,
            "intended_topic_count": 20,
        },
        "config": {
            "key": str(key_path),
            "annotations_glob": args.annotations_glob,
        },
        "annotation_files": [str(path.resolve()) for path in annotation_paths],
        "summary": summary,
        "annotator_preferences": annotator_preferences,
        "rows_read": total_rows,
    }
    save_json(Path(args.output).resolve(), output)
    eprint(f"Saved human evaluation summary to {Path(args.output).resolve()}")


def run_self_test(_: argparse.Namespace) -> None:
    mock_report_xml = """
    <evaluation>
      <report_a>
        <informativeness_and_depth><score>4.5</score><justification>A</justification></informativeness_and_depth>
        <coherence_and_organization><score>4</score><justification>A</justification></coherence_and_organization>
        <verifiability><score>5</score><justification>A</justification></verifiability>
        <visualization_quality><score>4.5</score><justification>A</justification></visualization_quality>
        <visualization_consistency><score>4.5</score><justification>A</justification></visualization_consistency>
      </report_a>
      <report_b>
        <informativeness_and_depth><score>4</score><justification>B</justification></informativeness_and_depth>
        <coherence_and_organization><score>3.5</score><justification>B</justification></coherence_and_organization>
        <verifiability><score>4</score><justification>B</justification></verifiability>
        <visualization_quality><score>4</score><justification>B</justification></visualization_quality>
        <visualization_consistency><score>4</score><justification>B</justification></visualization_consistency>
      </report_b>
    </evaluation>
    """
    mock_chart_xml = """
    <evaluation>
      <readability><score>9</score><justification>A</justification></readability>
      <layout><score>9.5</score><justification>A</justification></layout>
      <aesthetics><score>8.5</score><justification>A</justification></aesthetics>
      <data_faithfulness><score>10</score><justification>A</justification></data_faithfulness>
      <goal_compliance><score>9</score><justification>A</justification></goal_compliance>
    </evaluation>
    """
    parsed_report = parse_report_response(mock_report_xml, REPORT_METRICS)
    parsed_chart = parse_chart_response(mock_chart_xml, CHART_METRICS)
    assert parsed_report["report_a"]["verifiability"]["score"] == 5.0
    assert parsed_chart["layout"]["score"] == 9.5
    print("Self-test passed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce the public evaluation setup from the Multimodal DeepResearcher paper."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report", help="Run automatic report evaluation.")
    report_parser.add_argument("--manifest", required=True, help="Path to the report manifest JSON.")
    report_parser.add_argument("--output", required=True, help="Where to save the evaluation JSON.")
    report_parser.add_argument("--model", default=os.environ.get("EVAL_MODEL", "gpt-4.1"))
    report_parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    report_parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    report_parser.add_argument("--seed", type=int, default=42)
    report_parser.add_argument("--temperature", type=float, default=0.0)
    report_parser.add_argument("--max-tokens", type=int, default=4000)
    report_parser.add_argument("--max-images-per-report", type=int, default=12)
    report_parser.add_argument("--max-report-chars", type=int, default=30000)
    report_parser.add_argument("--max-learnings-chars", type=int, default=20000)
    report_parser.add_argument("--delay-seconds", type=float, default=0.0)
    report_parser.add_argument(
        "--prompt-file",
        default=str(DEFAULT_REPORT_PROMPT_PATH),
        help="Path to the pairwise report judge prompt file.",
    )
    report_parser.set_defaults(func=evaluate_reports)

    single_report_parser = subparsers.add_parser(
        "report-single", help="Run single-report scoring with the paper's report rubric."
    )
    single_report_parser.add_argument("--manifest", required=True, help="Path to the single-report manifest JSON.")
    single_report_parser.add_argument("--output", required=True, help="Where to save the evaluation JSON.")
    single_report_parser.add_argument("--model", default=os.environ.get("EVAL_MODEL", "gpt-4.1"))
    single_report_parser.add_argument(
        "--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    single_report_parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    single_report_parser.add_argument("--temperature", type=float, default=0.0)
    single_report_parser.add_argument("--max-tokens", type=int, default=2500)
    single_report_parser.add_argument("--max-images-per-report", type=int, default=12)
    single_report_parser.add_argument("--max-report-chars", type=int, default=30000)
    single_report_parser.add_argument("--max-learnings-chars", type=int, default=20000)
    single_report_parser.add_argument("--delay-seconds", type=float, default=0.0)
    single_report_parser.add_argument(
        "--prompt-file",
        default=str(DEFAULT_SINGLE_REPORT_PROMPT_PATH),
        help="Path to the single-report judge prompt file.",
    )
    single_report_parser.set_defaults(func=evaluate_single_reports)

    chart_parser = subparsers.add_parser("chart", help="Run automatic chart evaluation.")
    chart_parser.add_argument("--manifest", required=True, help="Path to the chart manifest JSON.")
    chart_parser.add_argument("--output", required=True, help="Where to save the evaluation JSON.")
    chart_parser.add_argument("--model", default=os.environ.get("EVAL_MODEL", "gpt-4.1"))
    chart_parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    chart_parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    chart_parser.add_argument("--temperature", type=float, default=0.0)
    chart_parser.add_argument("--max-tokens", type=int, default=2000)
    chart_parser.add_argument("--max-spec-chars", type=int, default=12000)
    chart_parser.add_argument("--delay-seconds", type=float, default=0.0)
    chart_parser.add_argument(
        "--prompt-file",
        default=str(DEFAULT_CHART_PROMPT_PATH),
        help="Path to the chart judge prompt file.",
    )
    chart_parser.set_defaults(func=evaluate_charts)

    human_prepare_parser = subparsers.add_parser(
        "prepare-human", help="Create a blinded CSV pack for pairwise human evaluation."
    )
    human_prepare_parser.add_argument("--manifest", required=True, help="Path to the report manifest JSON.")
    human_prepare_parser.add_argument("--out-dir", required=True, help="Directory to write the CSV pack.")
    human_prepare_parser.add_argument("--count", type=int, default=20, help="Number of topics to sample.")
    human_prepare_parser.add_argument("--seed", type=int, default=42)
    human_prepare_parser.set_defaults(func=prepare_human_eval)

    human_aggregate_parser = subparsers.add_parser(
        "aggregate-human", help="Aggregate completed human annotation CSV files."
    )
    human_aggregate_parser.add_argument("--key", required=True, help="Key JSON produced by prepare-human.")
    human_aggregate_parser.add_argument(
        "--annotations-glob",
        required=True,
        help="Glob for completed annotation CSV files, e.g. 'evaluation_runs/human/*.csv'.",
    )
    human_aggregate_parser.add_argument("--output", required=True, help="Where to save the summary JSON.")
    human_aggregate_parser.set_defaults(func=aggregate_human_eval)

    self_test_parser = subparsers.add_parser("self-test", help="Run parser smoke tests.")
    self_test_parser.set_defaults(func=run_self_test)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
