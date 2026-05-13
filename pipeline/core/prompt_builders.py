def build_section_prompt(
    *,
    topic,
    section,
    style_guide,
    sec_learnings,
    sec_images,
    strict_image_grounding=True,
    image_selection_mode="semantic",
    evidence_gap=None,
    preferred_max_original_images=None,
):
    grounding_rules = """
- Only insert an image if it directly supports a concrete claim in this section.
- Do not use weakly related or decorative images.
- Every inserted image must be explicitly explained in the surrounding text.
- Prefer images that match the section's analytical role, such as algorithm/pipeline figures for method sections and result charts/tables for experiment sections.
- If you insert an image, explain in 1-2 sentences what specific evidence the image provides and why it matters for this section.
- If no strongly relevant image is available, do not insert any image.
""".strip()
    legacy_rules = """
- IMPORTANT: You MUST insert MULTIPLE relevant [Image_X] placeholders in this section to enrich the visual experience and heavily support your claims.
- CRITICAL IMAGE INTEGRATION RULES (Referential Anchor Grounding):
  1. DO NOT use generic filler phrases like "As shown in [Image_X]" or "Figure [Image_X] illustrates".
  2. You MUST use 'Visual Landmark Anchoring': describe specific colors, positions, trends, or module names visible in the image to connect it to your logical argument.
  3. Example (Good): "Observing the dual-die layout on the left side of [Image_X], the architecture doubles the bandwidth..."
  4. Images must be treated as core evidentiary components of your argument. Devote at least 2-3 sentences analyzing the visual details of EACH inserted image to strengthen the report's arguments.
  5. Do NOT make up image IDs that are not in your available list.
    """.strip()
    weak_metadata_rules = """
- In this setting, only weak metadata is available for original images: placeholder ID, alt text, page title, source/domain hint, URL hint, and nearby webpage text.
- No OCR, direct image understanding, or model-based image reranking has been performed.
- Insert at most 1 original image in this section.
- Insert an image only if these weak metadata cues clearly support a concrete claim in this section.
- If there is no clear metadata match, insert none.
    """.strip()
    image_selection_mode = (image_selection_mode or "semantic").strip().lower()
    if image_selection_mode == "weak_metadata":
        image_rules = weak_metadata_rules
        image_hint_rule = "- Use only the weak metadata hints provided above. Do not infer unseen visual details from the image."
        landmark_rule = "- If you insert an original image [Image_X], explain the textual connection conservatively from the provided metadata and nearby evidence only; do not claim specific visual landmarks that were not given."
    else:
        image_rules = grounding_rules if strict_image_grounding else legacy_rules
        image_hint_rule = "- Treat the available source, summary, and matching hints as ranking signals. Prefer the most relevant image(s)."
        landmark_rule = (
            '- If you insert an original image [Image_X], reference 1-2 concrete visual landmarks from that image so the connection between the image and the surrounding claim is explicit.'
            if strict_image_grounding
            else '**CRITICAL: Visual Landmark Anchoring**. If you insert ANY original image [Image_X], you MUST write 3-4 sentences in the surrounding text explicitly referencing the image\'s specific visual landmarks (e.g., "As seen in the orange highlighted blocks...", "The steep curve on the left side of the chart demonstrates...", "Notice the memory bandwidth numbers in the top right corner..."). Never just insert an image without deeply explaining its visual contents.'
        )
    gap_block = ""
    if evidence_gap:
        gap_block = f"""

**Known evidence gap for this section:** {evidence_gap}
Write conservatively about areas covered by this gap. Explicitly acknowledge limitations where evidence is insufficient rather than speculating."""
    image_count_hint = "1-2 images"
    if preferred_max_original_images == 1:
        image_count_hint = "1 image"
    elif isinstance(preferred_max_original_images, int) and preferred_max_original_images > 1:
        image_count_hint = f"{preferred_max_original_images} images"
    return f"""
You are writing a section for a research report on the topic: "{topic}".
This section is titled: "{section['title']}"
Summary/Outline of this section: "{section['summary']}"

### Guidelines:
1. Follow the Visualization Style Guide:
{style_guide}

2. Use the following research learnings as your knowledge base:
{sec_learnings}
{gap_block}

3. Citation and verifiability rules:
- For every important quantitative claim, benchmark, chronology, causal explanation, comparison, or empirical judgment, attach a supporting markdown hyperlink in the same sentence or in the immediately following sentence.
- Prefer source links already present in the provided learnings. When possible, cite the most primary or directly relevant source rather than a vague secondary summary.
- Do not rely on a single citation dumped at the end of a long paragraph to support many different claims. If a paragraph makes multiple distinct claims, distribute citations near the relevant clauses.
- Avoid vague unsupported phrasing such as "materials indicate", "studies show", "it is reported", or "the literature suggests" unless you also name the source and place a nearby link.
- If a claim is only partially supported by the provided material, explicitly narrow or soften it instead of stating it strongly.
- If you compare multiple systems, methods, periods, or regions, make sure each side of the comparison has nearby evidence rather than citing only one side.
- If a source image is being used as evidence, the surrounding text should state what claim it supports and also keep the source traceable in nearby prose.
- Keep the section auditable on its own: a careful reader should be able to verify the section's main claims without relying only on a references list at the end of the report.

4. We have decoupled the physical images from the text.
Available Image Placeholders for this section:
{sec_images}
{image_rules}
- DO NOT use the same image multiple times in the report.
- To insert an image, use the exact ID format on a new line, e.g., [Image_1]
- NEVER make up fake image IDs like [Image_99]. Only use what is provided above.
{image_hint_rule}
- Usually insert no more than {image_count_hint} in a section.

5. You may generate either:
   - a data chart, but only when REAL data and specific facts from the research learnings support it; or
   - a grounded schematic / mechanism / pipeline diagram when the section is explaining architecture, optimization flow, training stages, or method differences.
  In both cases, every element must come from the provided learnings or section context. DO NOT use dummy/fake data like "Alpha", "Beta", or "Sample Bar Chart".
6. Generate a chart or diagram only when it materially improves understanding of a comparison, trend, workflow, or mechanism that would be harder to follow in prose alone.
7. If prose or available original source images already communicate the point clearly, do not generate a chart.
8. Be conservative with generated visualizations. Most sections should contain no generated chart, and a section should usually contain at most one generated visualization.
9. A <visualization> block is valid only if it contains a complete JSON design spec and is immediately closed with </visualization>. Never output a dangling opening tag.
10. If you cannot provide a complete and grounded chart design, do not output any <visualization> tag.
11. Never place prose, headings, or bullet lists inside a <visualization> block.
12. {landmark_rule}

Write the full Markdown content for this section now:
""".strip()
