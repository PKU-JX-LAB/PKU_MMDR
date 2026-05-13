import os
import sys
import argparse
import json
import datetime
import warnings
import urllib3

warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

from core.config import (
    ABLATION_MODE,
    ACTIVE_ABLATION_LABEL,
    ADAPTIVE_OUTLINE,
    ENABLE_SECTION_BY_SECTION_GENERATION,
    IMAGE_PIPELINE_CONFIG,
)
from core.artifact_utils import load_json, save_json
from core.generate import generate_draft_report, generate_draft_report_by_section, process_report
from core.image_metadata import build_image_metadata
from core.image_enrichment_pipeline import run_image_enrichment_pipeline
from core.plan import generate_plan
from core.research import do_research


def _load_nonempty_text(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return content if content.strip() else None


def _reconstruct_learning_id_map_from_learnings(learnings_text):
    learning_items = []
    inside_questions = False

    for raw_line in (learnings_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "<questions>" in line:
            inside_questions = True
            continue
        if "</questions>" in line:
            inside_questions = False
            continue
        if inside_questions:
            continue

        normalized = line.lstrip("- *").strip()
        if normalized and len(normalized) > 20:
            learning_items.append(normalized)

    if not learning_items:
        return None
    return {f"L{idx}": text for idx, text in enumerate(learning_items, start=1)}


def _load_existing_research_artifacts(output_dir):
    learnings = _load_nonempty_text(os.path.join(output_dir, "learnings.txt"))
    if not learnings:
        return None

    adaptive_outline = _load_nonempty_text(os.path.join(output_dir, "adaptive_outline.md")) if ADAPTIVE_OUTLINE else None
    learning_id_map = None
    if ADAPTIVE_OUTLINE:
        learning_id_map = load_json(os.path.join(output_dir, "learning_id_map.json"), default=None)
        if not learning_id_map:
            learning_id_map = _reconstruct_learning_id_map_from_learnings(learnings)

    return {
        "learnings": learnings,
        "adaptive_outline": adaptive_outline,
        "learning_id_map": learning_id_map,
    }


def run_pipeline(topic, output_dir, update_progress=None, resume_from_research=False):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Runtime ablation mode: {ACTIVE_ABLATION_LABEL}")
    save_json(
        os.path.join(output_dir, "image_pipeline_config.json"),
        {
            "ablation_mode": ABLATION_MODE,
            "planning_mode": "text_only",
            "image_pipeline_config": IMAGE_PIPELINE_CONFIG,
        },
    )

    print("\n" + "=" * 50)
    print("PHASE 1: RESEARCH")
    print("=" * 50)
    research_adaptive_outline = None
    learning_id_map = None
    restored = None

    if resume_from_research:
        restored = _load_existing_research_artifacts(output_dir)
        if restored:
            print("Resuming from existing research artifacts in output directory.")
            learnings = restored["learnings"]
            research_adaptive_outline = restored.get("adaptive_outline")
            learning_id_map = restored.get("learning_id_map")
            if ADAPTIVE_OUTLINE and not research_adaptive_outline:
                print("Adaptive outline file not found; planning will fall back to regenerated outline.")
            if ADAPTIVE_OUTLINE and not learning_id_map:
                print("Learning ID map could not be restored; section routing may fall back to broader context.")
        else:
            print("No reusable research artifacts found. Running research phase from scratch.")

    if restored is None:
        research_result = do_research(topic, output_dir)

        # Adaptive outline: do_research returns (learnings, outline, id_map) tuple
        if ADAPTIVE_OUTLINE:
            learnings, research_adaptive_outline, learning_id_map = research_result
            print("Adaptive outline enabled; outline co-evolved during research.")
        else:
            learnings = research_result
    elif ADAPTIVE_OUTLINE and research_adaptive_outline:
        print("Adaptive outline restored from previous research run.")

    with open(os.path.join(output_dir, "learnings.txt"), "w", encoding="utf-8") as f:
        f.write(learnings)

    image_pool = {}
    mapping_path = os.path.join(output_dir, "images_mapping.json")
    if os.path.exists(mapping_path):
        with open(mapping_path, "r", encoding="utf-8") as f:
            image_pool = json.load(f)
    image_references = load_json(os.path.join(output_dir, "image_references.json"), default=[])

    image_metadata = None
    planning_figure_text = ""
    if IMAGE_PIPELINE_CONFIG.get("enable_image_metadata") and image_pool:
        image_metadata = build_image_metadata(
            image_pool,
            output_dir,
            topic=topic,
            pipeline_config=IMAGE_PIPELINE_CONFIG,
            image_references=image_references,
        )
        if IMAGE_PIPELINE_CONFIG.get("enable_contextual_image_pipeline"):
            image_metadata, planning_figure_text = run_image_enrichment_pipeline(
                topic,
                learnings,
                output_dir,
                image_metadata,
                pipeline_config=IMAGE_PIPELINE_CONFIG,
                outline=research_adaptive_outline,
            )
            save_json(os.path.join(output_dir, "image_metadata.json"), image_metadata)

    print("\n" + "=" * 50)
    print("PHASE 2: PLANNING")
    print("=" * 50)
    if ADAPTIVE_OUTLINE and research_adaptive_outline:
        import re as _re

        outline = research_adaptive_outline
        outline_clean = _re.sub(r"<citation>.*?</citation>", "", outline)
        outline_clean = _re.sub(r"(?m)^Evidence:.*$\n?", "", outline_clean)
        outline_clean = _re.sub(r"(?m)^Gap:.*$\n?", "", outline_clean)
        outline_clean = _re.sub(r"\n{3,}", "\n\n", outline_clean).strip()
        print("Using adaptive outline from research phase (citations preserved for routing).")
        _, style_guide = generate_plan(topic, learnings, figure_plan_text=planning_figure_text)
    else:
        outline, style_guide = generate_plan(topic, learnings, figure_plan_text=planning_figure_text)
    with open(os.path.join(output_dir, "outline.txt"), "w", encoding="utf-8") as f:
        f.write(outline_clean if (ADAPTIVE_OUTLINE and research_adaptive_outline) else outline)
    with open(os.path.join(output_dir, "style_guide.txt"), "w", encoding="utf-8") as f:
        f.write(style_guide)

    print("\n" + "=" * 50)
    print("PHASE 3 & 4: REPORT & CHART GENERATION")
    print("=" * 50)
    if ENABLE_SECTION_BY_SECTION_GENERATION:
        draft_report = generate_draft_report_by_section(
            topic,
            outline,
            learnings,
            image_pool,
            style_guide,
            image_metadata=image_metadata,
            pipeline_config=IMAGE_PIPELINE_CONFIG,
            output_dir=output_dir,
            learning_id_map=learning_id_map,
        )
    else:
        print("Section-by-section generation ablation enabled. Falling back to global generation.")
        draft_report = generate_draft_report(
            topic,
            outline,
            learnings,
            style_guide,
            image_pool=image_pool,
            image_metadata=image_metadata,
            pipeline_config=IMAGE_PIPELINE_CONFIG,
            output_dir=output_dir,
        )
    with open(os.path.join(output_dir, "draft_report.md"), "w", encoding="utf-8") as f:
        f.write(draft_report)

    final_report = process_report(draft_report, output_dir)
    print("\nMultimodal DeepResearcher pipeline completed successfully!")
    return final_report


class _TeeStream:
    def __init__(self, stream, log_file):
        self._stream = stream
        self._log = log_file

    def write(self, data):
        self._stream.write(data)
        self._log.write(data)
        self._log.flush()

    def flush(self):
        self._stream.flush()
        self._log.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def main():
    parser = argparse.ArgumentParser(description="Multimodal DeepResearcher")
    parser.add_argument("--topic", type=str, required=True, help="Research topic")
    parser.add_argument("--output_dir", type=str, default="./output", help="Output directory")
    parser.add_argument(
        "--ablation",
        type=str,
        choices=["none", "section_generation", "image_enrichment", "weak_metadata", "adaptive_outline"],
        default=ABLATION_MODE,
        help="Ablation mode. Also supports MDR_ABLATION_MODE environment variable.",
    )
    parser.add_argument(
        "--early-stop",
        action="store_true",
        default=False,
        help="Enable outline maturity early-stop (adaptive outline only).",
    )
    parser.add_argument(
        "--resume-from-research",
        action="store_true",
        default=False,
        help="Reuse existing learnings.txt / adaptive_outline.md in output_dir instead of re-running research.",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(args.output_dir, f"run_{timestamp}.log")
    log_file = open(log_path, "a", encoding="utf-8")
    sys.stdout = _TeeStream(sys.__stdout__, log_file)
    sys.stderr = _TeeStream(sys.__stderr__, log_file)
    print(f"Logging to {log_path}")

    try:
        run_pipeline(args.topic, args.output_dir, resume_from_research=args.resume_from_research)
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        log_file.close()


if __name__ == "__main__":
    main()
