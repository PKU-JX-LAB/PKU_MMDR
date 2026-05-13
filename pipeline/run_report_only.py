import argparse
import os
import shutil

from core.artifact_utils import load_json, save_json
from core.config import (
    ABLATION_MODE,
    ACTIVE_ABLATION_LABEL,
    ENABLE_SECTION_BY_SECTION_GENERATION,
    IMAGE_PIPELINE_CONFIG,
)
from core.generate import generate_draft_report, generate_draft_report_by_section, process_report


def _read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _backup_if_exists(path):
    if not os.path.exists(path):
        return
    backup_path = f"{path}.bak"
    shutil.copyfile(path, backup_path)
    print(f"Backed up existing file to {backup_path}")


def rerun_report_only(topic, output_dir):
    print("\n" + "=" * 50)
    print("REPORT-ONLY RERUN")
    print("=" * 50)
    print(f"Runtime ablation mode: {ACTIVE_ABLATION_LABEL}")

    learnings_path = os.path.join(output_dir, "learnings.txt")
    outline_path = os.path.join(output_dir, "outline.txt")
    style_guide_path = os.path.join(output_dir, "style_guide.txt")
    mapping_path = os.path.join(output_dir, "images_mapping.json")
    image_metadata_path = os.path.join(output_dir, "image_metadata.json")

    if not os.path.exists(learnings_path):
        raise FileNotFoundError(f"Missing learnings file: {learnings_path}")
    if not os.path.exists(outline_path):
        raise FileNotFoundError(f"Missing outline file: {outline_path}")
    if not os.path.exists(style_guide_path):
        raise FileNotFoundError(f"Missing style guide file: {style_guide_path}")

    learnings = _read_text(learnings_path)
    outline = _read_text(outline_path)
    style_guide = _read_text(style_guide_path)
    image_pool = load_json(mapping_path, default={})
    image_metadata = load_json(image_metadata_path, default=None)

    save_json(
        os.path.join(output_dir, "report_only_rerun_config.json"),
        {
            "topic": topic,
            "ablation_mode": ABLATION_MODE,
            "image_pipeline_config": IMAGE_PIPELINE_CONFIG,
            "has_image_pool": bool(image_pool),
            "has_image_metadata": bool(image_metadata),
        },
    )

    draft_path = os.path.join(output_dir, "draft_report.md")
    final_path = os.path.join(output_dir, "final_report.md")
    _backup_if_exists(draft_path)
    _backup_if_exists(final_path)

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
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(draft_report)

    final_report = process_report(draft_report, output_dir)
    print("\nReport-only rerun completed successfully!")
    return final_report


def main():
    parser = argparse.ArgumentParser(description="Rerun only the report generation stage.")
    parser.add_argument("--topic", required=True, help="Original topic used for this run.")
    parser.add_argument("--output_dir", required=True, help="Existing run directory.")
    parser.add_argument(
        "--ablation",
        choices=["none", "section_generation", "image_enrichment"],
        default=ABLATION_MODE,
        help="Ablation mode. Also supports MDR_ABLATION_MODE environment variable.",
    )
    args = parser.parse_args()
    rerun_report_only(args.topic, args.output_dir)


if __name__ == "__main__":
    main()
