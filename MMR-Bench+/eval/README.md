# Evaluation Reproduction

This directory recreates the public evaluation setup described in the **Multimodal DeepResearcher** paper using only details that are available from the paper and appendix.

What this matches from the paper:
- `MultimodalReportBench` style pairwise report evaluation
- `GPT-4.1` style automatic judge
- 5 report metrics on a `1-5` scale with `0.5` increments
- chart evaluation with 5 chart metrics on a `1-10` scale
- randomized pair order for both automatic and human evaluation
- human evaluation pack prep and aggregation for 20 sampled topics / 5 annotators

What is still an assumption because the original code is not public:
- The appendix PDF text corrupts several XML tags, so the script uses valid XML tags with underscores such as `report_a` and `visualization_quality`.
- The paper says report evaluation includes report visuals via base64 images, but the public repo does not ship the private experiment packaging code. This script expects you to provide the images in the manifest.
- The paper says chart evaluation uses the original design specification plus the chart image. Those design specs are not in the public repo, so you need to supply them yourself.
- The paper reports win/loss/tie after comparing scores. This script computes the winner per metric by directly comparing the two scores and computes `overall` from the mean of the 5 metric scores.
- The optional `report-single` mode is a practical extension for cases where you only have one report per topic. It uses the paper's rubric but is not the paper's original pairwise protocol.

## Requirements

The script uses:
- `requests`
- `pypdf` only if your manifest points to `.pdf` report files

It talks to an OpenAI-compatible `chat/completions` endpoint.
By default, the evaluator uses `stream=True` and concatenates streamed chunks. This is intentional because some compatible providers return empty text for non-streaming GPT-5/Codex calls.

Set env vars before running:

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:EVAL_MODEL="gpt-4.1"
```

## Report Manifest

Create a JSON file like [examples/report_manifest.template.json](examples/report_manifest.template.json).

Expected shape:

```json
{
  "pairs": [
    {
      "pair_id": "topic-001",
      "topic": "Language-based AI systems have grown rapidly in recent years",
      "learnings_path": "../eval_data/topic-001/learnings.md",
      "systems": [
        {
          "name": "ours",
          "report_path": "../eval_data/topic-001/ours/report.md",
          "images_dir": "../eval_data/topic-001/ours/report_images"
        },
        {
          "name": "baseline",
          "report_path": "../eval_data/topic-001/baseline/report.md",
          "images_dir": "../eval_data/topic-001/baseline/report_images"
        }
      ]
    }
  ]
}
```

Notes:
- `learnings_path` is the internet research evidence used by the judge, matching the paper setup.
- `report_path` can be `.md`, `.mdx`, `.txt`, `.html`, `.json`, `.csv`, or `.pdf`.
- For visuals, you can use `image_paths`, `images_dir`, or `image_glob`.
- Report page screenshots or chart screenshots are both acceptable inputs; the paper only states that report visuals are passed as base64 images.

## Run Report Evaluation

```powershell
python MMR-Bench+/eval/paper_eval.py report `
  --manifest MMR-Bench+/eval/examples/report_manifest.template.json `
  --output evaluation_runs/report_eval.json
```

The output JSON contains:
- per-pair raw judge responses
- per-metric scores for both systems
- per-metric winners and ties
- raw score means
- win/loss/tie percentages in the same style as Table 1

## Run Single-Report Evaluation

If you do not want to compare against a baseline yet, use `report-single`. This is not the paper's original pairwise setup, but it reuses the same 5 report metrics.

Manifest shape:

```json
{
  "reports": [
    {
      "report_id": "topic-001",
      "topic": "What is Moore's Law?",
      "report_path": "../eval_data/topic-001/final_report.md",
      "images_dir": "../eval_data/topic-001/html_charts"
    }
  ]
}
```

Run it:

```powershell
python MMR-Bench+/eval/paper_eval.py report-single `
  --manifest evaluation_runs/mdr_reports_report_manifest.json `
  --output evaluation_runs/report_single_eval.json
```

## Prompt Experimentation

Judge prompts now live under [prompts/](prompts/):

- [prompts/report_pairwise_default.txt](prompts/report_pairwise_default.txt)
- [prompts/report_single_default.txt](prompts/report_single_default.txt)
- [prompts/chart_default.txt](prompts/chart_default.txt)

All automatic evaluation commands accept `--prompt-file`, so you can keep multiple prompt variants for experiments without editing Python logic.

Example:

```powershell
python MMR-Bench+/eval/paper_eval.py report-single `
  --manifest evaluation_runs/mdr_reports_report_manifest.json `
  --output evaluation_runs/report_single_eval.json `
  --prompt-file MMR-Bench+/eval/prompts/report_single_default.txt
```

## Chart Manifest

Create a JSON file like [examples/chart_manifest.template.json](examples/chart_manifest.template.json).

Expected shape:

```json
{
  "reports": [
    {
      "report_id": "topic-001-ours",
      "pair_id": "topic-001",
      "topic": "Language-based AI systems have grown rapidly in recent years",
      "system": "ours",
      "charts": [
        {
          "chart_id": "chart-0",
          "spec_path": "../eval_data/topic-001/ours/chart_specs/chart-0.md",
          "image_path": "../eval_data/topic-001/ours/chart_images/chart-0.png"
        }
      ]
    }
  ]
}
```

## Run Chart Evaluation

```powershell
python MMR-Bench+/eval/paper_eval.py chart `
  --manifest MMR-Bench+/eval/examples/chart_manifest.template.json `
  --output evaluation_runs/chart_eval.json
```

This follows the paper's chart setup:
1. score each chart individually
2. average scores across charts in each report
3. average report means per system, matching the Table 3 reporting style

## Build A Chart Manifest From `multimodal_deepresearcher_reports`

If your data comes from a directory of generated reports (one folder per topic, as produced by the reproduction pipeline), you can auto-build a chart manifest:

```powershell
python MMR-Bench+/eval/build_mdr_reports_chart_manifest.py `
  --dataset-root .\path\to\multimodal_deepresearcher_reports `
  --output evaluation_runs/mdr_reports_chart_manifest.json `
  --spec-dir evaluation_runs/extracted_chart_specs `
  --mismatch-report evaluation_runs/mdr_reports_chart_manifest_mismatches.json
```

This builder:
- treats each topic directory as one `ours` report
- uses `final_report.md` as the report artifact
- extracts each `<visualization>...</visualization>` block from `textual_report.md` as the chart design spec
- pairs those specs with `html_charts/html_*_screenshot.png`

Important:
- this is enough for the paper-style **chart evaluation**
- it is **not enough** for full paper-style **report pairwise evaluation**, because the dataset still does not contain baseline reports or learnings

## Build A Single-Report Manifest From `multimodal_deepresearcher_reports`

```powershell
python MMR-Bench+/eval/build_mdr_reports_report_manifest.py `
  --dataset-root .\path\to\multimodal_deepresearcher_reports `
  --output evaluation_runs/mdr_reports_report_manifest.json
```

This manifest is intended for `report-single`.

## Generate `Learnings` From Report Links

If you want a closer approximation to the paper's report-evaluation setup, you can generate `learnings` by crawling the external links already cited inside each `final_report.md`.

This is still an approximation:
- the paper generates learnings from SERP results during the research stage
- this script instead revisits links already cited in the finished report

But it follows the paper's **learning generation prompt style** by:
- reading full fetched source contents
- extracting dense, reference-rich learnings
- keeping exact numbers, entities, dates, and table/list information when possible

Fetch only, no model call:

```powershell
python MMR-Bench+/eval/generate_learnings_from_report_links.py `
  --manifest evaluation_runs/mdr_reports_report_manifest.json `
  --output-manifest evaluation_runs/mdr_reports_report_manifest_with_learnings.json `
  --learnings-dir evaluation_runs/generated_learnings `
  --links-dir evaluation_runs/fetched_sources `
  --report-meta evaluation_runs/generated_learnings_meta.json `
  --max-reports 3 `
  --fetch-only
```

Generate learnings with a model:

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_BASE_URL="https://api.openai.com/v1"

python MMR-Bench+/eval/generate_learnings_from_report_links.py `
  --manifest evaluation_runs/mdr_reports_report_manifest.json `
  --output-manifest evaluation_runs/mdr_reports_report_manifest_with_learnings.json `
  --learnings-dir evaluation_runs/generated_learnings `
  --links-dir evaluation_runs/fetched_sources `
  --report-meta evaluation_runs/generated_learnings_meta.json `
  --model gpt-5.3-codex `
  --base-url $env:OPENAI_BASE_URL `
  --api-key $env:OPENAI_API_KEY `
  --max-reports 3
```

Then run single-report evaluation with the updated manifest:

```powershell
python MMR-Bench+/eval/paper_eval.py report-single `
  --manifest evaluation_runs/mdr_reports_report_manifest_with_learnings.json `
  --output evaluation_runs/report_single_eval.json `
  --model gpt-5.3-codex `
  --base-url $env:OPENAI_BASE_URL
```

## Package Single-Report Results By Topic

If you prefer the experiment outputs to be organized like the dataset itself, with one folder per topic containing only that topic's evaluation artifacts, you can package the results like this:

```powershell
python MMR-Bench+/eval/package_single_report_eval_by_topic.py `
  --eval-json evaluation_runs/report_single_eval.json `
  --fetch-meta-json evaluation_runs/generated_learnings_meta.json `
  --output-dir evaluation_runs/report_single_eval_by_topic
```

Each topic folder contains:
- `summary.json`
- `report_single_eval.json`
- `learnings_fetch_meta.json` when provided
- `learnings.md` when available
- `fetched_sources/` copied from the link-fetch cache when available

## Human Evaluation

Prepare the blind assignment:

```powershell
python MMR-Bench+/eval/paper_eval.py prepare-human `
  --manifest MMR-Bench+/eval/examples/report_manifest.template.json `
  --out-dir evaluation_runs/human_pack `
  --count 20 `
  --seed 42
```

This creates:
- `human_eval_assignment.csv`
- `human_eval_key.json`

Annotators should fill each `*_choice` column with:
- `left`
- `right`
- `tie`

Then aggregate:

```powershell
python MMR-Bench+/eval/paper_eval.py aggregate-human `
  --key evaluation_runs/human_pack/human_eval_key.json `
  --annotations-glob "evaluation_runs/human_annotations/*.csv" `
  --output evaluation_runs/human_summary.json
```

## Smoke Test

```powershell
python MMR-Bench+/eval/paper_eval.py self-test
```

## Working With This Repo

The public repo only includes demo reports and HTML charts. It does not include:
- the private `MultimodalReportBench` packaging code
- the original baseline generations
- the original chart design specifications

So the script here gives you a faithful evaluation scaffold, but you still need to provide:
- report pairs (`ours` vs `baseline`)
- learnings for each topic
- rendered images
- chart design specs

