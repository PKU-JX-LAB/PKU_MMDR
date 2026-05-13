import glob
import json
import os
import re
import subprocess
import urllib3
from urllib.parse import urlparse

import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

topic = "NVIDIA Blackwell architecture vs AMD Rubin performance and memory capabilities"


def run_loop():
    print(f"Generating E2E report for: {topic}")

    try:
        from app import generate_report

        for msg, _ in generate_report(topic):
            pass
        print("Generation complete!")
    except Exception as e:
        print(f"Generation failed: {e}")

    dirs = glob.glob("output_*")
    dirs.sort(key=os.path.getmtime, reverse=True)
    out_dir = dirs[0]
    print(f"Using output dir: {out_dir}")

    mapping_path = os.path.join(out_dir, "images_mapping.json")
    report_path = os.path.join(out_dir, "final_report.md")

    with open(report_path, "r", encoding="utf-8") as f:
        report_content = f.read()

    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    used_images = re.findall(r"!\[(Image_\d+)\]", report_content)
    used_images = list(set(used_images))
    print(f"Images used in report: {used_images}")

    downloaded_images = []
    for key in used_images:
        if key in mapping:
            url = mapping[key]
            try:
                res = requests.get(url, timeout=15, verify=False)
                res.raise_for_status()
                ext = os.path.splitext(urlparse(url).path)[1]
                if not ext:
                    ext = ".png"
                filename = f"{key}{ext}"
                filepath = os.path.join(out_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(res.content)
                downloaded_images.append(filepath)
            except Exception:
                pass

    manifest_rel = os.path.join("evaluation_runs", "auto_manifest.json")
    output_rel = os.path.join("evaluation_runs", "auto_eval_result.json")
    manifest_abs = os.path.join("..", "..", "MMR-Bench+", "eval", manifest_rel)
    os.makedirs(os.path.dirname(manifest_abs), exist_ok=True)

    manifest = {
        "reports": [
            {
                "report_id": "auto_eval_report_final",
                "topic": topic,
                "report_path": f"../../pipeline/{report_path}",
                "learnings_path": f"../../pipeline/{out_dir}/learnings.txt",
                "source_image_paths": [f"../../pipeline/{p}" for p in downloaded_images],
                "generated_image_paths": [],
            }
        ]
    }
    charts = glob.glob(os.path.join(out_dir, "*_screenshot.png"))
    manifest["reports"][0]["generated_image_paths"] = [
        f"../../pipeline/{p}" for p in charts
    ]

    with open(manifest_abs, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running evaluation.")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    cmd = [
        "python",
        "paper_eval.py",
        "report-single",
        "--manifest",
        manifest_rel,
        "--output",
        output_rel,
        "--model",
        "gpt-4o",
        "--base-url",
        base_url,
        "--prompt-file",
        "prompts/report_single_default.txt",
    ]
    print("Running evaluator...")
    eval_dir = os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "MMR-Bench+", "eval")
    subprocess.run(cmd, cwd=eval_dir, check=True)

    eval_result_path = os.path.join(eval_dir, output_rel)
    with open(eval_result_path, "r", encoding="utf-8") as f:
        res = json.load(f)

    overall = res.get("summary", {}).get("overall_mean", 0)
    img_score = 0
    try:
        img_score = res.get("report_results", [])[0]["scores"]["original_image_integration"]["score"]
    except Exception:
        pass

    print(f"\n=== FINAL OVERALL SCORE: {overall} ===")
    print(f"=== ORIGINAL IMAGE INTEGRATION SCORE: {img_score} ===")

    if overall >= 4.0:
        print("SUCCESS! Target score reached.")
    else:
        print("FAILED! Score is < 4.0.")
    return overall


if __name__ == "__main__":
    run_loop()


