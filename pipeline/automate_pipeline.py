import os
import shutil
import re
import argparse
import uuid
from datetime import datetime
from core.config import ABLATION_MODE, ACTIVE_ABLATION_LABEL
from main import run_pipeline


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEXTJS_REPORT_DIR = os.path.join(BASE_DIR, "frontend", "data", "report")
NEXTJS_CHART_DIR = os.path.join(BASE_DIR, "frontend", "public", "html_charts")
NEXTJS_PROJECTS_DATA_PATH = os.path.join(BASE_DIR, "frontend", "data", "projectsData.ts")

def run_automated_pipeline(topic):
    print(f"Starting multimodal report generation: {topic}")
    print(f"Runtime ablation mode: {ACTIVE_ABLATION_LABEL}")
    

    safe_topic_name = re.sub(r'[^a-zA-Z0-9]', '-', topic).strip('-')
    safe_topic_name = re.sub(r'-+', '-', safe_topic_name)[:30]
    if not safe_topic_name:
        safe_topic_name = f"report-{str(uuid.uuid4())[:8]}"
    
    output_dir = os.path.join(os.getcwd(), f"output_{safe_topic_name}")
    
    final_report_content = run_pipeline(topic, output_dir)
    
    print("Syncing results to the frontend site...")
    
    target_chart_dir = os.path.join(NEXTJS_CHART_DIR, safe_topic_name)
    if os.path.exists(target_chart_dir):
        shutil.rmtree(target_chart_dir)
    os.makedirs(target_chart_dir, exist_ok=True)
    
    for file in os.listdir(output_dir):
        if file.endswith(".html"):
            shutil.copy(os.path.join(output_dir, file), os.path.join(target_chart_dir, file))
    

    # Force the year to 2024 so that if the system clock is in the future
    # (for example, 2026), Next.js does not treat the page as a draft and hide it with a 404.
    current_date = datetime.now()
    safe_date_str = f"2024-{current_date.strftime('%m-%d')}"
    
    mdx_content = f"""---
title: '{topic}'
date: '{safe_date_str}'
tags: ['AI-Generated', 'Research']
draft: false
summary: Report
---

{final_report_content}
"""

    
    target_mdx_path = os.path.join(NEXTJS_REPORT_DIR, f"{safe_topic_name}.mdx")
    with open(target_mdx_path, "w", encoding="utf-8") as f:
        f.write(mdx_content)
        
    with open(NEXTJS_PROJECTS_DATA_PATH, "r", encoding="utf-8") as f:
        projects_data = f.read()
        
    if safe_topic_name not in projects_data:
        new_entry = f"""  {{
    title: '{topic}',
    description: `Interactive multimodal research report.`,
    imgSrc: '/static/images/time-machine.jpg',
    href: '/report/{safe_topic_name}',
  }},
"""
        projects_data = projects_data.replace("const projectsData: Project[] = [", f"const projectsData: Project[] = [\n{new_entry}")
        with open(NEXTJS_PROJECTS_DATA_PATH, "w", encoding="utf-8") as f:
            f.write(projects_data)
            
    print(f"\nGeneration succeeded! Open the report at: http://localhost:3000/report/{safe_topic_name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated MDR Pipeline")
    parser.add_argument("topic", type=str, help="Research topic")
    parser.add_argument(
        "--ablation",
        choices=["none", "section_generation", "image_enrichment"],
        default=ABLATION_MODE,
        help="Ablation mode. Also supports MDR_ABLATION_MODE environment variable.",
    )
    args = parser.parse_args()
    
    run_automated_pipeline(args.topic)
