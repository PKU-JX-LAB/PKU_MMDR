import json
import os
import requests

out_dir = "output_Apple-Vision-Pro"
mapping_path = os.path.join(out_dir, "images_mapping.json")

with open(mapping_path, "r", encoding="utf-8") as f:
    mapping = json.load(f)

local_images = []
for key, url in mapping.items():
    ext = os.path.splitext(url)[1]
    if not ext or ext.lower() not in [".jpg", ".jpeg", ".png"]:
        ext = ".jpg"
    local_path = os.path.join(out_dir, f"{key}{ext}")
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(res.content)
        local_images.append(os.path.abspath(local_path))
        print(f"Downloaded {key} to {local_path}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

# If we couldn't download the specific images, maybe there are OCR images available
import glob
ocr_images = glob.glob(os.path.join(out_dir, "image_pipeline", "ocr_images", "*.*"))
for img in ocr_images:
    local_images.append(os.path.abspath(img))
    
# Unique images
local_images = list(set(local_images))

manifest = {
    "reports": [
        {
            "id": "apple_vision_pro_report",
            "topic": "Analysis of Apple Vision Pro compute-chip distribution and sensor-fusion array design",
            "report_path": os.path.abspath(os.path.join(out_dir, "final_report.md")),
            "learnings_path": os.path.abspath(os.path.join(out_dir, "learnings.txt")),
            "source_image_paths": local_images
        }
    ]
}

eval_manifest_path = os.path.abspath("../../MMR-Bench+/eval/evaluation_runs/manifest_apple.json")
os.makedirs(os.path.dirname(eval_manifest_path), exist_ok=True)
with open(eval_manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=4)
print(f"Saved manifest to {eval_manifest_path}")


