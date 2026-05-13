import os
import re

from .artifact_utils import save_json


def check_section_grounding(section_title, section_content, selected_images, output_dir=None):
    issues = []
    used_ids = sorted(set(re.findall(r"Image_\d+", section_content)))
    selected_ids = {item["image_id"] for item in selected_images}

    for image_id in used_ids:
        if image_id not in selected_ids:
            issues.append({"image_id": image_id, "problem": "image_not_in_ranked_set"})

    for item in selected_images:
        image_id = item["image_id"]
        if image_id not in used_ids:
            continue
        mentions = len(re.findall(re.escape(image_id), section_content))
        if mentions < 1:
            issues.append({"image_id": image_id, "problem": "missing_reference"})

    result = {
        "section_title": section_title,
        "used_images": used_ids,
        "issues": issues,
        "pass": len(issues) == 0,
    }
    if output_dir:
        path = os.path.join(output_dir, "section_grounding_check.json")
        existing = []
        if os.path.exists(path):
            import json
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(result)
        save_json(path, existing)
    return result


def prune_ungrounded_images(section_content, allowed_image_ids):
    allowed = set(allowed_image_ids)

    def repl(match):
        image_id = match.group(1)
        if image_id in allowed:
            return match.group(0)
        return ""

    return re.sub(r"\[(Image_\d+)(?::[^\]]*)?\]", repl, section_content)
