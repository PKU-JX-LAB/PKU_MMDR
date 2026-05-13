import gradio as gr
import os
import shutil
import argparse


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEXTJS_REPORT_DIR = os.path.join(BASE_DIR, "frontend", "data", "report")
NEXTJS_CHART_DIR = os.path.join(BASE_DIR, "frontend", "public", "html_charts")
NEXTJS_PROJECTS_DATA_PATH = os.path.join(BASE_DIR, "frontend", "data", "projectsData.ts")

def generate_report(topic, progress=gr.Progress()):
    if not topic.strip():
        return "Please enter a research topic first!", ""
        

    import re

    safe_topic_name = re.sub(r'[^a-zA-Z0-9]', '-', topic).strip('-')

    safe_topic_name = re.sub(r'-+', '-', safe_topic_name)[:30]
    

    if not safe_topic_name:
        import uuid
        safe_topic_name = f"report-{str(uuid.uuid4())[:8]}"
    output_dir = os.path.join(os.getcwd(), f"output_{safe_topic_name}")
    

    def update_progress(msg):

        return msg
        
    try:

        yield "Running deep web search and information extraction (Research Phase)...", ""
        
        os.makedirs(output_dir, exist_ok=True)
        

        print("\n" + "="*50)
        print("PHASE 1: RESEARCH")
        print("="*50)
        from core.research import do_research
        from core.config import ADAPTIVE_OUTLINE
        research_result = do_research(topic, output_dir)
        research_adaptive_outline = None
        learning_id_map = None
        if ADAPTIVE_OUTLINE:
            learnings, research_adaptive_outline, learning_id_map = research_result
        else:
            learnings = research_result
        with open(os.path.join(output_dir, "learnings.txt"), "w", encoding="utf-8") as f:
            f.write(learnings)
            
        yield "Building the report outline and visual specification (Planning Phase)...", ""
        

        print("\n" + "="*50)
        print("PHASE 2: PLANNING")
        print("="*50)
        from core.plan import generate_plan
        from core.config import (
            ACTIVE_ABLATION_LABEL,
            ENABLE_SECTION_BY_SECTION_GENERATION,
            IMAGE_PIPELINE_CONFIG,
        )
        from core.image_metadata import build_image_metadata
        from core.image_enrichment_pipeline import run_image_enrichment_pipeline
        from core.artifact_utils import load_json, save_json
        print(f"Runtime ablation mode: {ACTIVE_ABLATION_LABEL}")
        
        image_pool = {}
        mapping_path = os.path.join(output_dir, "images_mapping.json")
        if os.path.exists(mapping_path):
            import json
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

        if ADAPTIVE_OUTLINE and research_adaptive_outline:
            outline = research_adaptive_outline
            import re as _re
            outline_clean = _re.sub(r"<citation>.*?</citation>", "", outline)
            outline_clean = _re.sub(r"(?m)^Evidence:.*$\n?", "", outline_clean)
            outline_clean = _re.sub(r"(?m)^Gap:.*$\n?", "", outline_clean)
            outline_clean = _re.sub(r"\n{3,}", "\n\n", outline_clean).strip()
            _, style_guide = generate_plan(topic, learnings, figure_plan_text=planning_figure_text)
        else:
            outline, style_guide = generate_plan(topic, learnings, figure_plan_text=planning_figure_text)
        with open(os.path.join(output_dir, "outline.txt"), "w", encoding="utf-8") as f:
            f.write(outline_clean if (ADAPTIVE_OUTLINE and research_adaptive_outline) else outline)
        with open(os.path.join(output_dir, "style_guide.txt"), "w", encoding="utf-8") as f:
            f.write(style_guide)
            
        yield "Drafting the long-form report and creating the initial charts (Drafting Report)...", ""
        

        print("\n" + "="*50)
        print("PHASE 3 & 4: REPORT & CHART GENERATION")
        print("="*50)
                
        from core.generate import generate_draft_report, generate_draft_report_by_section, process_report
        if ENABLE_SECTION_BY_SECTION_GENERATION:
            draft_report = generate_draft_report_by_section(
                topic, outline, learnings, image_pool, style_guide,
                image_metadata=image_metadata, pipeline_config=IMAGE_PIPELINE_CONFIG, output_dir=output_dir,
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
            
        yield "Refining interactive D3.js charts with the Actor-Critic loop (Refining Charts)...", ""
        final_report_content = process_report(draft_report, output_dir)
        
        # Write final_report.md
        with open(os.path.join(output_dir, "final_report.md"), "w", encoding="utf-8") as f:
            f.write(final_report_content)
            
        print("\n Multimodal DeepResearcher pipeline completed successfully!")
        
        yield "Syncing the generated results to the frontend site (Deploying to Next.js)...", ""
        

        target_chart_dir = os.path.join(NEXTJS_CHART_DIR, safe_topic_name)
        if os.path.exists(target_chart_dir):
            shutil.rmtree(target_chart_dir)
        os.makedirs(target_chart_dir, exist_ok=True)
        
        for file in os.listdir(output_dir):
            if file.endswith(".html"):
                shutil.copy(os.path.join(output_dir, file), os.path.join(target_chart_dir, file))
                

        mdx_content = f"""---
title: '{topic}'
date: '{__import__('datetime').datetime.now().strftime("%Y-%m-%d")}'
tags: ['AI-Generated', 'Research']
draft: false
summary: 'Interactive multimodal research report.'
---

{final_report_content}
"""

        import re
        mdx_content = re.sub(
            r'<HTMLRenderer htmlFile="([^"]+)" />', 
            f'<HTMLRenderer htmlFile="{safe_topic_name}/\\1" />', 
            mdx_content
        )
        

        target_mdx_path = os.path.join(NEXTJS_REPORT_DIR, f"{safe_topic_name}.mdx")
        with open(target_mdx_path, "w", encoding="utf-8") as f:
            f.write(mdx_content)
            

        with open(NEXTJS_PROJECTS_DATA_PATH, "r", encoding="utf-8") as f:
            projects_data = f.read()
            

        if f"href: '/report/{safe_topic_name}'" not in projects_data:
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
                
        preview_url = f"http://localhost:3000/report/{safe_topic_name}"
        success_msg = f" Generation succeeded! The full pipeline has completed."
        
        yield success_msg, preview_url

    except Exception as e:
        import traceback
        yield f"An error occurred during generation: {str(e)}\n\n{traceback.format_exc()}", ""


with gr.Blocks(title="Multimodal DeepResearcher", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Multimodal DeepResearcher")
    gr.Markdown("Enter a research topic below. The system will complete the following stages in order: **Research -> Outline Planning -> Report Writing -> D3.js Chart Generation -> Frontend Sync**.")
    
    with gr.Row():
        topic_input = gr.Textbox(label="Research Topic", placeholder="For example: Global humanoid robotics industry status and future trends in 2024", scale=4)
        submit_btn = gr.Button("Generate Report", variant="primary", scale=1)
        
    with gr.Row():
        status_output = gr.Textbox(label="Run Status", lines=5)
        
    with gr.Row():
        gr.Markdown("### Report Link")
        url_output = gr.Markdown("Waiting for generation...")
        
    submit_btn.click(
        fn=generate_report,
        inputs=[topic_input],
        outputs=[status_output, url_output]
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multimodal DeepResearcher Gradio UI")
    parser.add_argument(
        "--ablation",
        choices=["none", "section_generation", "image_enrichment", "weak_metadata", "adaptive_outline"],
        default=None,
        help="Ablation mode. Also supports MDR_ABLATION_MODE environment variable.",
    )
    parser.add_argument(
        "--early-stop",
        action="store_true",
        default=False,
        help="Enable outline maturity early-stop (adaptive outline only).",
    )
    parser.parse_known_args()
    print("Starting the Web UI...")
    demo.launch(server_name="127.0.0.1", server_port=7860)
