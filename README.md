# Multimodal DeepResearcher Reproduction and Evaluation

This repository contains a reproduction of the **Multimodal DeepResearcher** paper together with benchmarking and evaluation assets. Starting from a research topic, it can automatically generate an end-to-end multimodal research report with text, interactive D3.js charts, and webpage images.

## Project Structure

```
├── pipeline/                  # Core Python pipeline (entrypoints + core modules + eval helpers)
├── MMR-Bench+/            # Benchmark datasets + evaluation framework
│   ├── query_data/            #   Evaluation topic sets
│   └── eval/                  #   LLM-as-Judge evaluation scripts
└── README.md
```

***

## 1. `pipeline` - Core Pipeline Reproduction

### Overview

`pipeline/` is the full Python implementation of the paper, containing a four-stage agentic pipeline from web search to final report output.

The current layout separates user-facing entry scripts from reusable internals:

- `pipeline/main.py`, `pipeline/app.py`, `pipeline/run_report_only.py`, `pipeline/automate_pipeline.py`: entrypoints
- `pipeline/core/`: core reusable modules (research/planning/generation/config/tools)
- `pipeline/eval/`: local helper scripts for run-and-eval workflows

### Pipeline Architecture

```
User enters a topic
    │
    ▼
Phase 1: Research (research.py)
    Iterative web search -> Firecrawl crawling -> LLM extraction of learnings + images
    Outputs: learnings.txt, images_mapping.json
    │
    ▼
Phase 1.5: Image Enrichment (image_metadata.py + image_enrichment_pipeline.py)
    Five-stage funnel: Heuristic -> Context -> Topic -> OCR -> Final
    ~100 source images -> ~6 high-quality images
    │
    ▼
Phase 2: Planning (plan.py)
    One LLM call -> outline (outline.txt) + visualization style guide (style_guide.txt)
    │
    ▼
Phase 3: Drafting (generate.py + router.py + prompt_builders.py)
    Section-by-section generation with exclusive image assignment
    Output: draft_report.md (with <visualization> FDV blocks + [Image_X] placeholders)
    │
    ▼
Phase 4: Chart Generation + Assembly (generate.py)
    Actor-Critic loop: FDV -> D3.js code -> Selenium screenshot -> Critic review -> iterative refinement
    Replace FDV blocks with chart_X.html and [Image_X] with real URLs
    Output: final_report.md + chart_0.html, chart_1.html, ...
```

### Key Files

| File | Purpose |
| --- | --- |
| `pipeline/main.py` | CLI entry point that connects all phases |
| `pipeline/app.py` | Gradio web entry point with progress display and frontend sync |
| `pipeline/core/config.py` | Central configuration for model names, API keys, hyperparameters, and image-pipeline switches |
| `pipeline/core/llm_utils.py` | Unified LLM invocation layer for text and multimodal calls, with streaming and retries |
| `pipeline/core/research.py` | Phase 1: iterative search, image extraction/filtering, and learning extraction |
| `pipeline/core/image_metadata.py` | Base image metadata construction, including `figure_type` inference, dedup keys, and confidence scores |
| `pipeline/core/image_enrichment_pipeline.py` | Five-stage image refinement funnel |
| `pipeline/core/image_vision_metadata.py` | MLLM-based image analysis: download -> OCR -> evidence extraction |
| `pipeline/core/plan.py` | Phase 2: outline + style guide generation, including format normalization |
| `pipeline/core/exemplar.py` | FDV extraction from exemplar chart images into structured design specs |
| `pipeline/core/router.py` | Outline parsing plus routing of learnings/images to each section |
| `pipeline/core/prompt_builders.py` | Builds the LLM prompt for each section |
| `pipeline/core/image_ranker.py` | Scores and ranks candidate images per section |
| `pipeline/core/image_grounding_check.py` | Validates whether referenced image IDs are legal |
| `pipeline/core/generate.py` | Phase 3 and 4 core: section drafting, Actor-Critic chart generation, and final assembly |
| `pipeline/core/prompts.py` | All 11 system/user prompt pairs |
| `pipeline/automate_pipeline.py` | Automatically syncs generated outputs to the Next.js frontend |
| `pipeline/run_report_only.py` | Re-runs only report generation, skipping Research and Planning |

### Key Innovations

1. **SVS (Structured Visualization Specification)**: decomposes chart design into four structured components (Layout / Scale / Data / Marks) for controllable "design -> code" generation
2. **Actor-Critic chart generation loop**: Actor generates D3.js code -> Selenium renders screenshots -> MLLM Critic reviews visually -> iterative correction for up to three rounds
3. **Template Fallback Detection**: keyword and month-axis pattern detection prevents the LLM from collapsing into generic chart templates
4. **Text-image decoupling**: the `[Image_X]` placeholder mechanism supports independent multi-stage filtering, routing, and deduplication
5. **Five-stage image enrichment pipeline**: refines about 100 raw images into a high-quality subset
6. **Visual Landmark Anchoring**: forces the LLM to describe concrete visual evidence instead of vague boilerplate references

### Quick Start

**CLI:**

```bash
cd pipeline
python main.py --topic "Global AI chip development trends in 2024" --output_dir ./output
python main.py --topic "Global AI chip development trends in 2024" --output_dir ./output --ablation section_generation
python main.py --topic "Global AI chip development trends in 2024" --output_dir ./output --ablation image_enrichment
```

**Gradio Web UI:**

```bash
cd pipeline
python app.py
python app.py --ablation section_generation
python app.py --ablation image_enrichment
# Open http://localhost:7860, enter a topic, and click Generate Report
```

**With the frontend site:**

```bash
cd frontend
npm install && npm run dev
npm run dev:ablate-section
npm run dev:ablate-image
# Open http://localhost:3000/projects/
```

### How To Launch Ablations

By default, no ablation is applied:

- Backend full model: `python main.py --topic "Your topic" --output_dir ./output`
- Gradio full model: `python app.py`
- Frontend full model: `npm run dev`

For the **section-by-section deep generation ablation (STORM-like Section-by-Section Generation)**, use:

- Backend CLI: `python main.py --topic "Your topic" --output_dir ./output --ablation section_generation`
- Backend with frontend sync: `python automate_pipeline.py "Your topic" --ablation section_generation`
- Gradio: `python app.py --ablation section_generation`
- Frontend: `npm run dev:ablate-section`

For the **context-aware image enrichment pipeline ablation (Contextual Image Enrichment Pipeline)**, use:

- Backend CLI: `python main.py --topic "Your topic" --output_dir ./output --ablation image_enrichment`
- Backend with frontend sync: `python automate_pipeline.py "Your topic" --ablation image_enrichment`
- Gradio: `python app.py --ablation image_enrichment`
- Frontend: `npm run dev:ablate-image`

The unified underlying environment variable is `MDR_ABLATION_MODE`, with these values:

- `none`: default full model, no ablation
- `section_generation`: disables section-by-section deep generation and falls back to one-shot global generation
- `image_enrichment`: disables image metadata construction, contextual image enrichment, and image reranking

### Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `MDR_API_KEY` | OpenAI-compatible API key | _(required, no default)_ |
| `MDR_BASE_URL` | Base API URL | `https://api.openai.com/v1` |
| `MDR_ABLATION_MODE` | Ablation mode switch, commonly `none` / `section_generation` / `image_enrichment` | `none` |
| `FIRECRAWL_API_KEY` | Firecrawl search API key | _(required for web search, no default)_ |
| `MDR_TEXT_MODEL` | Text model | `gpt-4o-mini` |
| `MDR_VISION_MODEL` | Vision model | `gpt-4o` |
| `MDR_TEMPERATURE` | Generation temperature | `0.7` |
| `MDR_RETRIES` | LLM retry count | `3` |

### Output Directory Structure

```
output_{topic}/
├── learnings.txt              # Extracted learnings
├── images_mapping.json        # Image_ID -> URL mapping
├── image_references.json      # Full image provenance metadata
├── image_metadata.json        # Enriched image metadata
├── image_pipeline/            # Intermediate artifacts from each image-selection stage
├── adaptive_outline.md        # Live outline with evidence citations (enabled by default)
├── outline.txt                # Report outline
├── style_guide.txt            # Visualization style guide
├── draft_report.md            # Draft report (with FDV blocks + image placeholders)
├── chart_0.html               # Generated interactive D3.js chart
├── chart_0_screenshot.png     # Critic review screenshot
├── ...
└── final_report.md            # Final multimodal report
```

***

## 2. `MMR-Bench+` - Benchmark Dataset

### Overview

`MMR-Bench+/` provides standardized datasets for evaluating multimodal report generation systems, including two topic sets.

### Datasets

#### `mmdr_topics101.jsonl` - 101 General Topics

This set covers English research topics across **12 domains**:

| Domain | Example Topic |
| --- | --- |
| Technology & Media | *Since 2010, the training computation of notable AI systems has doubled every six months* |
| Agriculture & Food | *Global cereal production has grown much faster than population* |
| Healthcare | *Obesity rates have increased on every continent* |
| Energy | *Why did renewables become so cheap so fast?* |
| Climate & Environment | *Which countries have contributed the most to historical CO2 emissions?* |
| Population | *Global average life expectancy has more than doubled since 1900* |
| Education | *Nearly half of teenagers globally cannot read with comprehension* |
| Economy & Work | *Is globalization an engine of economic development?* |
| Travel | *Global sales of combustion engine cars have peaked* |
| Public Sector | *Public social spending has increased very substantially in the 20th century* |

Data format:

```json
{"id": "TOPIC-001", "idx": 1, "topic": "Technology & Media",
 "prompt": "Every global region has seen a steep rise in mobile phone subscriptions",
 "language": "en", "source": "Modalmodel Deepresearch Bench"}
```

#### `mmdr_sfq60.jsonl` - 60 Specialized Deep Topics (MMDR+)

This set covers high-difficulty Chinese research topics in **four major domains**, and each topic **explicitly requires citations to original paper figures**:

| Domain | Count | Difficulty | Examples |
| --- | --- | --- | --- |
| AI & Machine Learning | 15 | medium~hard | *GRPO variant comparison, MoE evolution, RAG architecture routes* |
| Systems & Hardware | 10 | medium~hard | *AI training-cluster interconnects, HBM evolution, chiplet design* |
| Biomedicine & Health | 5 | medium~hard | *AlphaFold evolution, CRISPR editing comparison, CAR-T manufacturing* |
| More domains | 30 | medium~hard | *Including quantum error correction, optical interconnects, liquid cooling, and more* |

Data format:

```json
{"id": "SFQ-001", "idx": 1, "topic": "AI & Machine Learning", "difficulty": "medium",
 "prompt": "Please write a survey report on the five major GRPO variants...",
 "language": "zh", "source": "MMDR+"}
```

### `baseline_outputs/`

This directory stores outputs from baseline models such as `TongyiDeepresearch-30B-A3B` for comparison and evaluation.

***

## 3. Evaluation - Automatic Evaluation Framework

### Overview

`MMR-Bench+/eval/` reproduces the paper's LLM-as-Judge evaluation framework and supports both report evaluation and chart evaluation.

### Evaluation Dimensions

**Report evaluation (5 dimensions, scores 1-5):**

| Dimension | What It Measures |
| --- | --- |
| Informativeness & Depth | Content richness and detail density |
| Coherence & Organization | Structural organization and text-figure integration |
| Verifiability | Citations and evidence support |
| Visualization Quality | Chart design quality |
| Visualization Consistency | Style consistency across charts |

**Chart evaluation (5 dimensions, scores 1-10):**

| Dimension | What It Measures |
| --- | --- |
| Readability | Readability of titles, labels, and colors |
| Layout | Layout quality, including overlap avoidance |
| Aesthetics | Visual appeal |
| Data Faithfulness | Fidelity to the data |
| Goal Compliance | Whether the design specification is satisfied |

### Evaluation Modes

| Mode | Command | Description |
| --- | --- | --- |
| Report Pairwise | `report` | A/B comparison evaluation using the original paper protocol |
| Report Single | `report-single` | Absolute scoring for a single report |
| Chart Evaluation | `chart` | Scores each chart, then aggregates by report/system |

### Running Evaluations

```powershell
# Set environment variables
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"

# Report pairwise evaluation
python MMR-Bench+/eval/paper_eval.py report `
  --manifest manifest.json --output result.json

# Single-report evaluation
python MMR-Bench+/eval/paper_eval.py report-single `
  --manifest manifest.json --output result.json

# Chart evaluation
python MMR-Bench+/eval/paper_eval.py chart `
  --manifest chart_manifest.json --output chart_result.json

# Custom evaluation prompt
python MMR-Bench+/eval/paper_eval.py report-single `
  --manifest manifest.json --output result.json `
  --prompt-file MMR-Bench+/eval/prompts/report_single_default.txt
```

***

## Dependencies

- Python 3.9+
- `openai`, `requests`, `Pillow`, `numpy`, `selenium` (used for chart screenshot rendering)
- Microsoft Edge (Selenium headless browser)
- Node.js + npm (optional, for frontend presentation)

## Acknowledgements

This project is inspired by [DataNarrative](https://github.com/saidul-islam98/DataNarrative), [PPT Agent](https://github.com/icip-cas/PPTAgent), [deep-research](https://github.com/dzhng/deep-research), [node-DeepResearch](https://github.com/jina-ai/), and [manus](https://manus.im/).

