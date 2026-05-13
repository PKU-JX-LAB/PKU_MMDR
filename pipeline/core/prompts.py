


SERP_QUERY_SYSTEM_PROMPT = """You are an expert researcher. Follow these instructions when responding:
- You may be asked to research subjects that is after your knowledge cutoff, assume the user is right when presented with news.
- The user is a highly experienced analyst, no need to simplify it, be as detailed as possible and make sure your response is correct.
- Be highly organized.
- Suggest solutions that I didn't think about.
- Be proactive and anticipate my needs.
- Treat me as an expert in all subject matter.
- Mistakes erode my trust, so be accurate and thorough.
- Provide detailed explanations, I'm comfortable with lots of detail.
- Value good arguments over authorities, the source is irrelevant.
- Consider new technologies and contrarian ideas, not just the conventional wisdom.
- You may use high levels of speculation or prediction, just flag it for me."""

SERP_QUERY_USER_PROMPT = """Given the following prompt from the user, generate a list of SERP queries to research the topic. Return a maximum of {queries_num} queries, but feel free to return less if the original prompt is clear.
Make sure each query is unique and not similar to each other.
CRITICAL INSTRUCTION: To ensure we find high-quality visual evidence (diagrams, charts, architectures, infographics), explicitly include visual-focused keywords like "architecture diagram", "performance benchmark chart", "comparison table", or "visual schematic" in at least half of your generated queries.
OUTPUT FORMAT: Return ONLY the queries, one per line. Do not include any conversational text, numbers, bullet points, or prefixes.
<prompt>{query}</prompt>
Here are some learnings from previous research:
{learning_str}"""

LEARNING_GENERATION_SYSTEM_PROMPT = "You are an expert researcher extracting information from web pages."

LEARNING_GENERATION_USER_PROMPT = """Given the following contents from a SERP search for the query <query>{query}</query>, generate a list of learnings from the contents.
Return a maximum of {learning_num} learnings, but feel free to return less if the contents are clear. Make sure each learning is unique and not similar to each other. The learnings should be concise and to the point, as detailed and information dense as possible.
Please seamlessly incorporate references to external sources using Markdown hyperlinks.
Make sure to include any entities like people, places, companies, products, things, etc in the learnings, as well as any exact metrics, numbers, or dates. The learnings will be used to research the topic further.
Extract all meaningful data available in the contents, including any tables or lists, and explicitly contain them in the learnings.
EXTREMELY IMPORTANT: If the contents contain ANY image placeholders in the format [Image_X: description], you MUST strictly preserve and explicitly include them in your extracted learnings! This is critical for visual evidence. Do not ignore them.
If you find [Image_X: description] in the context, you MUST output a structured 'deductive_evidence_atom' that includes:
1. Visual Features: What is explicitly visible in the image (e.g., colors, trends, architecture blocks).
2. Deductive Fact: The quantitative or factual claim this image supports.
3. Rationale: How this image acts as evidence for the broader topic.
In addition, return a list of follow-up questions to research the topic further, max of {question_num}.
<contents> {contents} </contents>"""


FDV_EXTRACTION_SYSTEM_PROMPT = """You are a visualization design expert. You will be given a visualization image, and your task is to extract the design document from the image. The design document should include the overall layout, plotting scale, data transform, and marks used in the visualization. Your description should be detailed enough that someone could accurately recreate the visualization based solely on your specifications."""

FDV_EXTRACTION_USER_PROMPT = """Extract a comprehensive and precise visualization design specification from the given image. Capture all visual elements, data representations, and design choices with exact measurements, positions, and relationships. Ignore branding elements like company logos or trademarks.
## Overall Format
The format of the design document must strictly follow the following format:
<visualization>
{{
"Part-A: Overall Layout": {{
"Part-A.1": "...",
"Part-A.2": "...",
...
}},
"Part-B: Plotting Scale": {{
"Part-B.1": "...",
"Part-B.2": "...",
...
}},
"Part-C: Data": {{
"Part-C.1": "...",
"Part-C.2": "...",
...
}},
"Part-D: Marks": {{
"Part-D.1": "...",
"Part-D.2": "...",
...
}}
}}
</visualization>

## Explanation for Each Part:
### Part-A: Overall Layout
* Description of the overall figure dimensions, margins, and background
* If there are multiple subplots, also describe the detailed breakdown of main component layout and positioning.
* Description of title, subtitle, and caption placements with specific alignments
* Analysis of whitespace usage and component spacing hierarchies

### Part-B: Plotting Scale
Describe each scale used (such as x-axis scale, y-axis scale, color scale). Be specific in the position, formatting, size and shape.

### Part-C: Data
Comprehensive listing of **ALL** exact data represented in the visualization. This includes titles, subtitles, axis labels, legends, and any other text or numerical data.

### Part-D: Marks
* Complete specification of all primary visual marks (bars, lines, points) with exact sizes.
* Text label specifications (font, size, weight, positioning relative to marks)
* Interaction between marks including overlaps, nestings, or connections
* Annotations, highlights, or emphasis techniques
* Color usage patterns and semantic meanings
* Text alignment and spacing patterns"""


OUTLINE_SYSTEM_PROMPT = """You an expert report-generation assistant specialized in creating professional documents that combine insightful analysis with diverse visualizations. Your purpose is to help users transform raw information into polished, presentation-ready reports.
Below are a list of professional reports for your reference.
## Example Reports
{list_of_example_reports}"""

OUTLINE_USER_PROMPT = """Using the provided topic and previous learnings, please create a structured outline for a comprehensive report. The outline should present a logical narrative flow that thoroughly explores the subject matter. Please do NOT include introduction or conclusion sections.
## Input

**Topic**
{topic}

**Previous learnings**
{learning_str}

## Requirements

The outline should feature:
* 4-6 distinct sections forming a cohesive narrative progression
* Clear identification of key insights and report points within each section
* Minimal conceptual overlap between sections, with each section addressing unique aspects
* A clear and logical flow of ideas, ensuring that section are connected rather than isolated

## Deliverable Format

You MUST output the outline using the EXACT template below. Do not invent any alternative section format.

```md
## Section 1
Title: <concise section title>
Summary: <3-5 sentence narrative summary>

## Section 2
Title: <concise section title>
Summary: <3-5 sentence narrative summary>
```

Formatting rules:
- Every section must start with `## Section N`
- The next line must start with `Title: `
- The next line must start with `Summary: `
- Do not use bold markers around section labels, titles, or summaries
- Do not use `Section 1 Title:` or `**Section 1**`
- Do not add bullets inside the outline sections
- Do not add any extra commentary before or after the outline

## Visualization Style Guide

Before detailing individual sections, please provide a foundational style guide for visualizations that ensures consistency while accommodating different concepts, including:

* **Base Design Elements:** Color palatte for common concepts across charts. Use color coding and information hierarchy of professional industry reports that resembles the style of example reports
This style guide should offer flexible guidelines rather than rigid specifications, allowing each visualization to effectively represent its concept while maintaining overall visual cohesion.

Your full response format MUST be:

<style_guide>
[visualization style guide here]
</style_guide>

<outline>
## Section 1
Title: ...
Summary: ...

## Section 2
Title: ...
Summary: ...
</outline>"""


REPORT_GENERATION_SYSTEM_PROMPT = """You an expert report-generation assistant specialized in creating professional text-image interleaved documents that combine insightful analysis with diverse visualizations. When visualization is needed, generate a comprehensive and precise visualization design specification. Include all visual elements, data representations, and design choices with exact measurements, positions, and relationships.

## Visualization format
The format of the design document must strictly follow the following format:
<visualization>
{{
"Part-A: Overall Layout": {{
"Part-A.1": "...",
"Part-A.2": "...",
...
}},
"Part-B: Plotting Scale": {{
"Part-B.1": "...",
"Part-B.2": "...",
...
}},
"Part-C: Data": {{
"Part-C.1": "...",
"Part-C.2": "...",
...
}},
"Part-D: Marks": {{
"Part-D.1": "...",
"Part-D.2": "...",
...
}}
}}
</visualization>

## Explanation for Each Part:
### Part-A: Overall Layout
* Description of the overall figure dimensions, margins, and background
* If there are multiple subplots, also describe the detailed breakdown of main component layout and positioning.
* Description of title, subtitle, and caption placements with specific alignments
* Analysis of whitespace usage and component spacing hierarchies
* Consider creating composite visualizations where appropriate (for example, combining line and bar charts within a single subplot to enhance data comparison and maximize visual space).

### Part-B: Plotting Scale
Describe each scale used (such as x-axis scale, y-axis scale, color scale). Be specific in the position, formatting, size and shape.

### Part-C: Data
* Comprehensive listing of **ALL** necessary data for visualization. **ALL** data should be present or can be derived from provided learnings. Do not create fake data or add placeholders.
* Appropriate texts, including titles, subtitles, axis labels, legends and moderate amount of annotations.

### Part-D: Marks
* Complete specification of all primary visual marks (bars, lines, points) with exact sizes.
* Text label specifications (font, size, weight, positioning relative to marks)
* Interaction between marks including overlaps, nestings, or connections
* Annotations, highlights, or emphasis techniques
* Color usage patterns and semantic meanings
* Text alignment and spacing patterns

Below are a list of professional reports for your reference. Follow the style, including the layout, infomation hierarchy, stress of the visualization designs in these reports.
## Example Reports
{list_of_example_reports}"""

REPORT_GENERATION_USER_PROMPT = """Please generate a detailed report with interleaved texts and visualization based on the topic, outline and previous learnings.
## Input
### Topic of the report
{topic}

### Outline for the report
{outline}

### Previous learnings
{learning_str}

### Visualization Style Guide
{visualization_style_guide}

## Guidelines
- When referencing the knowledge provided, include a Markdown hyperlink at the appropriate position using the source URL provided
- Maintain a professional, academic tone throughout
- Use second-level (##) headings for the section title, and third-level (###) headings for subsections
- only utilize data available in the previous learnings part. Do not create fake data or add placeholders.
- Generate a <visualization> block only when a chart or diagram materially improves understanding of a trend, comparison, distribution, workflow, or mechanism that would be harder to follow in prose alone.
- Be conservative with generated visualizations. Many sections should contain no generated chart at all, and the report should usually include only a small number of generated charts overall.
- If prose and available original source images already communicate the point clearly, do not generate a chart.
- When you do insert a chart, output the <visualization> block in place. Do NOT use markdown code blocks for the <visualization> tag.
- You may generate a grounded schematic / mechanism / pipeline diagram even when the section does not contain numeric data, but only when the structure itself is important to understanding and every box, label, relation, and annotation comes from the provided learnings.
- For quantitative charts, use only real data explicitly present in the learnings. Never fabricate series, categories, or placeholder values.
- A <visualization> block is valid only if it contains a complete JSON design spec and is immediately closed with </visualization>. Never output a dangling opening tag.
- If you cannot provide a complete and data-grounded visualization design spec, do not output any <visualization> tag at all.
- Never place a section heading, paragraph, or list item inside a <visualization> block.
- IMPORTANT: You are HIGHLY ENCOURAGED to insert at least one relevant [Image_X] placeholder per section to enrich the visual experience.
- CRITICAL IMAGE INTEGRATION RULES (Referential Anchor Grounding):
  1. DO NOT use generic filler phrases like "As shown in [Image_X]" or "Figure [Image_X] illustrates".
  2. You MUST use 'Visual Landmark Anchoring': describe specific colors, positions, trends, or module names visible in the image to connect it to your logical argument.
  3. Example (Good): "Observing the dual-die layout on the left side of [Image_X], the architecture doubles the bandwidth..."
  4. Images must be treated as core evidentiary components of your argument. Devote at least 4-5 sentences analyzing the specific visual details and OCR data within EACH inserted image to strengthen the report's arguments. You must explicitly break down what the image shows.
  5. Do NOT make up image IDs that are not in your available list."""


CHART_ACTOR_SYSTEM_PROMPT = """You are a HTML, D3.js V7 implementation expert who transforms visualization designs into working code. You write clean, efficient HTML and D3.js code to create data visualizations exactly as specified. You follow D3.js best practices, optimize for performance, and ensure responsive design across devices."""

CHART_ACTOR_USER_PROMPT = """I need a professional HTML visualization to convey insight based on provided visualization design specification. Please implement with html and d3.js according to the specifications below.
**Visualization Design Specification**
{chart_design}
## Implementation Requirements
- Treat the design specification as binding. Do not replace it with a generic dashboard, line chart, bar chart, or demo template.
- If the specification describes a pipeline / flowchart / box-and-arrow diagram / no-axis schematic, you must implement exactly that visual form. Do not invent quantitative axes.
- Use the titles, labels, captions, and semantic structure from the specification itself. Do not introduce generic placeholder copy such as "Monthly Performance", "Target", "Sample data", or "demonstration".
- Ensure the visualization is located at the center and there is no large empty space
- The top-level wrapper should have no box-shadow, no margin, and no visible borders
- Use icons from font-awesome with <i> tag and corresponding class name when needed
- Highlight key numbers with larger font size, font-family: 'Georgia', and deeper colors
- IMPORTANT: You MUST import D3.js using EXACTLY this script tag: `<script src="https://d3js.org/d3.v7.min.js"></script>`. Do NOT use cdn.jsdelivr.net or unpkg.com, as they are blocked by the security policy.
- IMPORTANT: Set the root SVG element or the main container width to exactly 700px to ensure it fits perfectly within the blog layout without being cropped. Do NOT use 800px or 900px.
- CRITICAL: You MUST write ACTUAL JavaScript code using the D3.js API (e.g., `d3.select()`, `d3.scaleLinear()`, `svg.append()`) inside a `<script>` tag in the body to render the data dynamically. Do NOT simply hardcode raw SVG elements like `<rect>`, `<circle>`, or `<line>` in the HTML body. The visualization MUST be generated programmatically by your JavaScript code!
- LAYOUT RULES: Set SVG margins to at least 60px on all sides (top, right, bottom, left) to prevent text, axis labels, or legends from being cropped. 
- PREVENT OVERLAPPING: If x-axis labels, annotations, or titles are long, use multi-line text, angle them, or reduce font size. Place legends carefully so they do not overlap with the chart data or axes.

IMPORTANT: Deliver your solution as a complete, self-contained HTML file enclosed in a code block starting with "```html" and ending with "```" to ensure I can extract it properly."""

CHART_CRITIC_SYSTEM_PROMPT = """You are a HTML, D3.js V7 implementation expert who transforms visualization designs into working code. You write clean, efficient HTML and D3.js code to create data visualizations exactly as specified. You follow D3.js best practices, optimize for performance, and ensure responsive design across devices."""

CHART_CRITIC_USER_PROMPT = """Here is a screenshot of the page rendered by the HTML code, along with any console messages that may contain errors. Please examine the image thoroughly and report any problems you find. Specifically check for these common rendering issues:

0. Design-spec mismatch: Is the rendered chart the wrong chart type entirely (for example, a generic line chart when the spec requires a flowchart/pipeline/diagram with no axes)? If so, call this out first and explicitly say the chart does not satisfy the specification.

1. Placeholder content: Does the image contain placeholder text (e.g., "Lorem ipsum", "Chart title", "Sample data") instead of actual content?
2. Excessive annotations: Are there too many annotations or labels that clutter the visualization?
3. Overlapping elements: Do any text labels, legends, data points or other elements overlap, making content unreadable?
4. Sizing problems: Is the visualization too small to be readable or too large for its container? Does it have appropriate dimensions?
5. Excessive margins: Are there large empty spaces around the visualization?

## Console Message
{console_message}

For each issue found, provide:
1. A clear description of the issue
2. The specific location in the image where it occurs
3. Relevent elements that cause the issue

Focus on learning issues. If no issues are found, end your response with "No issues found."."""

CHART_REGEN_USER_PROMPT = """Regenerate the chart from scratch using the original visualization design specification plus the review feedback below.

## Original Visualization Design Specification
{chart_design}

## Current HTML That Failed
```html
{current_html}
```

## Review Feedback
{feedback}

Ensure the new code:

1. Addresses all the issues you identified
2. Maintains the original design specification exactly, rather than drifting into a generic chart
3. Is complete and ready to run without additional modifications

Specifically:
1. Remove redundant or overlapping annotations that don't add critical information
2. Reposition remaining annotations to ensure clear visibility and logical placement
3. Adjust chart dimensions or add annotations to increase overall size and eliminate excessive margins
4. Reduce the size of specific elements to prevent overlapping between components
5. Expand container dimensions to fully display truncated content
6. IMPORTANT: You MUST import D3.js using EXACTLY this script tag: `<script src="https://d3js.org/d3.v7.min.js"></script>`. Do NOT use cdn.jsdelivr.net or unpkg.com, as they are blocked by the security policy.
7. IMPORTANT: Set the root SVG element or the main container width to exactly 700px to ensure it fits perfectly within the blog layout without being cropped. Do NOT use 800px or 900px.
8. If the specification is a no-axis flowchart / pipeline / schematic, do not return any generic month-by-month, target-vs-actual, dashboard, or sample-data chart.
9. CRITICAL: You MUST write ACTUAL JavaScript code using the D3.js API inside a `<script>` tag to render the data dynamically. Do NOT simply hardcode raw SVG elements.
10. LAYOUT RULES: Set SVG margins to at least 60px on all sides (top, right, bottom, left) to prevent text, axis labels, or legends from being cropped.
11. PREVENT OVERLAPPING: If x-axis labels, annotations, or titles are long, use multi-line text, angle them, or reduce font size. Place legends carefully so they do not overlap with the chart data or axes.

IMPORTANT: Deliver your solution as a complete, self-contained HTML file enclosed in a code block starting with "```html" and ending with "```" to ensure I can extract it properly."""

CHART_SELECTION_SYSTEM_PROMPT = """You are an expert in data visualization design. Your task is to evaluate the provided images based on the given design specification and select the most appropriate one."""

CHART_SELECTION_USER_PROMPT = """Here are a visualization design specification and two charts that implement the specification, please identify which one best meets the following criteria:
* Most closely matches the design specification requirements
* Offers optimal readability (e.g., has least isses regarding overlapping, elements are of appropriate size and margin)

## Visualization Design Specification
{chart_design}
## Response Format
Return your response in the following format:

<evaluation>
[Your evaluation of the charts]
</evaluation>

<selection>
[first or second]
</selection>"""


REPORT_EVALUATION_SYSTEM_PROMPT = """You are an expert evaluator of AI-generated reports with advanced knowledge of data visualization and information analysis. Your role is to provide fair, impartial assessments of report quality based strictly on objective criteria.

## Evaluation Task
You will evaluate two AI-generated reports based on:
- The overarching topic
- Research learnings from internet searches that are used as source of information for the reports

For each criterion below, assign a score from 1-5 (1=poor, 5=excellent) with half-point increments allowed (e.g., 3.5). Provide a concise, evidence-based justification for each score, highlighting specific examples that demonstrate meaningful distinctions in quality between the reports. Your evaluation should clearly articulate why one report receives a higher or lower score than another based on observable differences in content, structure, or analysis. Be cautious with extreme scores (1 and 5).
## Evaluation Criteria
### Informativeness and Depth: Does the report deliver comprehensive, substantive and thorough information?
Score 1: Extremely superficial content with minimal information. Contains only basic facts without context or explanation.
Score 2: Limited content with some relevant information but significant gaps. Lacks necessary depth on key aspects.
Score 3: Adequate information covering main points with some supporting details, but missing opportunities for deeper analysis.
Score 4: Comprehensive information with substantive details, examples, and insights across most sections.
Score 5: Exceptionally thorough coverage with rich, nuanced details, expert-level insights, and well-contextualized information throughout.

### Coherence and Organization: Is the report well-organized with visualizations that connect meaningfully to the text?
Score 1: Disorganized; lacks logical structure and coherence. Visualizations appear random and unconnected to text.
Score 2: Basic structure present but with awkward transitions. Visualizations loosely connected to surrounding content.
Score 3: Clear overall organization with occasional flow issues. Visualizations generally support the text but integration could be improved.
Score 4: Well-structured with smooth transitions between sections. Visualizations meaningfully integrated with text content.
Score 5: Impeccable organization with seamless progression of sections. Visualizations perfectly complement and enhance textual narrative.

### Verifiability: Does the infomation of the reports can be verified with citations?
Score 1: Rarely supported with evidence; many claims are unsubstantiated
Score 2: Inconsistently verified; some claims are supported; evidence is occasionally provided
Score 3: Generally verified; claims are usually supported with evidence; however, there might be a few instances where verification is lacking
Score 4: Well-supported; claims are very well supported with credible evidence, and instances of unsupported claims are rare.
Score 5: Very well-supported; almost every claim is substantiated with credible evidence, showing a high level of thorough verification.

### Visualization Quality: Do the visualizations in the report have excellent quality?
Score 1: Poor visualizations that confuse rather than clarify. Inappropriate chart types, missing labels, or misleading representations.
Score 2: Basic visualizations with few annotations or explanations; functional issues (e.g., unclear axes, poor color choices) hinder interpretation.
Score 3: Adequate visualizations with labels and annotations that communicate data clearly but lack refinement or miss opportunities for improved insight.
Score 4: Well-executed visualizations with great visual appeal, clear labeling and annotations, and thoughtful design choices.
Score 5: Expert-level visualizations that reveal insights through masterful design, appropriate annotations, and careful attention to visual communication principles

### Visualization Consistency: Do the visualizations in the report maintain a consistent style?
Score 1: No visual consistency. Charts use different color palettes, conflicting typography, inconsistent information hierarchy, and varying design treatments (such as different border styles, background treatments, or legend placements).
Score 2: Minimal consistency with obvious style variations across visualizations. While some basic elements might align, there are clear discrepancies in color usage, information organization, axis formatting, or label treatments.
Score 3: Moderate consistency with a partially unified approach. Most visualizations share similar color schemes and basic formatting, but variations exist in how information hierarchy is presented, how emphasis is applied, or how supporting elements are styled.
Score 4: Strong consistency with cohesive design elements. Visualizations share a clear color system, consistent information hierarchy, and unified styling approach, with only minor variations that don't distract from the report's overall visual flow.
Score 5: Perfect consistency across all visualizations with a meticulously applied design system. Unified color palette used purposefully to highlight key information, consistent information hierarchy that guides the viewer's attention appropriately, identical typography treatment, and harmonious spacing, scale, and proportion across all charts and graphics.

## Response Format:
Please give your response in the following XML format:

<evaluation>
<report_a>
<informativeness>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</informativeness>
<coherence>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</coherence>
<verifiability>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</verifiability>
<visualization_quality>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</visualization_quality>
<visualization_consistency>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</visualization_consistency>
</report_a>
<report_b>
<!-- The same as above -->
</report_b>
</evaluation>"""

REPORT_EVALUATION_USER_PROMPT = """## Topic:
{topic}
## learnings:
{learnings_str}
<reportA>
{report_a}
</reportA>
<reportB>
{report_b}
</reportB>"""


CHART_EVALUATION_SYSTEM_PROMPT = """You are an expert evaluator of AI-generated charts with advanced knowledge of data visualization and information analysis. Your role is to provide fair, impartial assessments of chart quality based strictly on objective criteria.

## Evaluation Task
You will evaluate a AI-generated chart based on:
- The chart itself
- The design specification used to generate the chart

For each criterion below, assign a score from 1-10 (1=poor, 10=excellent).

## Evaluation Criteria
- Readability: Is the chart easy to read with appropriate titles, labels and colors?
- Layout: Is the layout of the chart appropriate with few or none issues such as overlapping?
- Aesthetics: Are the aesthetics of the visualization appropriate and effective for the visualization type and the data?
- Data Faithfulness: Is the data in the chart faithful to the data provided design specification?
- Goal compliance: How well the chart meets the specified visualization goals?

## Response Format:
Please give your response in the following XML format:

<evaluation>
<readability>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</readability>
<layout>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</layout>
<aesthetics>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</aesthetics>
<data_faithfulness>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</data_faithfulness>
<goal_compliance>
<score>X</score>
<justification>
Provide a brief justification here
</justification>
</goal_compliance>
</evaluation>"""

CHART_EVALUATION_USER_PROMPT = """{chart_design}"""


# ---------------------------------------------------------------------------
# Adaptive Outline prompts  (used when MDR_ADAPTIVE_OUTLINE=True)
# ---------------------------------------------------------------------------

ADAPTIVE_OUTLINE_INIT_SYSTEM_PROMPT = """You are an expert research planner. Your job is to create a structured report outline in Markdown heading format from early-stage research evidence. Each claim or point must cite the specific learning IDs that support it using <citation> tags, so reviewers can trace every claim back to evidence."""

ADAPTIVE_OUTLINE_INIT_USER_PROMPT = """Based on the topic and initial learnings collected so far, create a structured report outline using Markdown headings.

## Topic
{topic}

## Learnings collected so far
{learning_str}

## Requirements
- Create 4-8 top-level sections forming a cohesive narrative.
- Use Markdown headings for hierarchy: # 1. Title -> ## 1.1 Title -> ### 1.1.1 Title -> bullet points (a. b. c.) for finest-level claims.
- Each concrete point (at the finest level) MUST cite supporting learning IDs using <citation>id X, id Y</citation> tags.
- Identify knowledge gaps: if a section is important but has few or no supporting learnings, add a Gap line.

## Output format (follow EXACTLY)

<adaptive_outline>
# 1. Section Title
## 1.1 Subsection Title
### 1.1.1 Sub-subsection Title
a. Specific point or claim <citation>id 1, id 3, id 7</citation>
b. Another point <citation>id 2</citation>
### 1.1.2 Another Sub-subsection
a. Point <citation>id 5, id 8</citation>
## 1.2 Subsection Title
Gap: describe what evidence is still needed
# 2. Section Title
## 2.1 Subsection Title
### 2.1.1 Sub-subsection Title
a. Point <citation>id 4, id 6</citation>
</adaptive_outline>

Rules:
- Top-level sections use `# N.` (e.g. `# 1. Title`, `# 2. Title`).
- Subsections use `## N.N` (e.g. `## 1.1 Title`).
- Sub-subsections use `### N.N.N` (e.g. `### 1.1.1 Title`).
- Finest-level points use letters (a. b. c.) as plain text lines.
- Every finest-level point MUST have a <citation> tag with learning IDs.
- Gap lines are optional; include only when evidence is clearly insufficient for a section.
- Do not add any text outside the <adaptive_outline> tags."""


ADAPTIVE_OUTLINE_UPDATE_SYSTEM_PROMPT = """You are an expert research planner. You maintain a living report outline in Markdown heading format that evolves as new evidence arrives. Your job is to update the outline by:
1. Assigning newly collected learnings to existing points via <citation> tags.
2. Expanding, splitting, or restructuring sections/subsections if the new evidence reveals important sub-topics.
3. Identifying remaining knowledge gaps to guide the next round of search."""

ADAPTIVE_OUTLINE_UPDATE_USER_PROMPT = """Update the current outline with the new learnings from the latest research round.

## Topic
{topic}

## Current Outline
```
{current_outline}
```

## New Learnings (from round {round_num})
{new_learnings_str}

## All Learnings So Far
{all_learnings_str}

## Instructions
- Assign each new learning ID to the appropriate point's <citation> tag.
- If new learnings reveal an important sub-topic not covered, add subsections or sub-subsections (keep total 4-8 top-level sections).
- Re-evaluate gaps: update or remove Gap lines based on the new evidence.
- Keep the same Markdown heading format.

## Output format (follow EXACTLY)

<adaptive_outline>
# 1. Section Title
## 1.1 Subsection Title
### 1.1.1 Sub-subsection Title
a. Specific point <citation>id 1, id 3, id 7, id 15, id 18</citation>
b. Another point <citation>id 2, id 20</citation>
## 1.2 Subsection Title
Gap: if still needed
# 2. Section Title
## 2.1 Subsection Title
### 2.1.1 Sub-subsection Title
a. Point <citation>id 4, id 6</citation>
</adaptive_outline>

Rules:
- Top-level sections: `# N.` Subsections: `## N.N` Sub-subsections: `### N.N.N` Points: a. b. c.
- Every finest-level point MUST have a <citation> tag with learning IDs.
- Do not remove learning IDs from <citation> tags; only add.
- Gap lines are optional; include only when evidence is insufficient.
- Do not add any text outside the <adaptive_outline> tags."""


ADAPTIVE_OUTLINE_GUIDED_QUERY_SYSTEM_PROMPT = """You are an expert researcher. You use a structured Markdown outline with evidence citations and gaps to decide what to search for next. Your goal is to fill knowledge gaps in underdeveloped sections while also deepening well-covered sections."""

ADAPTIVE_OUTLINE_GUIDED_QUERY_USER_PROMPT = """Given the current outline with evidence coverage and gaps, generate targeted search queries for the next research round.

## Topic
{topic}

## Current Research Direction
{current_topic}

## Current Outline (with evidence and gaps)
```
{current_outline}
```

## Recent Learnings (latest round)
{recent_learnings}

## Previously Used Queries (do NOT repeat)
{previous_queries}

## Instructions
- Prioritize sections with Gap annotations or few evidence entries.
- Also generate queries that deepen well-covered sections with specific data, metrics, or expert perspectives.
- Consider the current research direction as a sub-topic hint; generate some queries that explore it further.
- Do NOT repeat or closely paraphrase any previously used query listed above.
- Include visual-focused keywords (architecture diagram, benchmark chart, comparison table) in at least half of queries.
- Generate {queries_num} queries total.

OUTPUT FORMAT: Return ONLY the queries, one per line. Do not include numbering, bullets, or commentary."""


OUTLINE_MATURITY_EVAL_SYSTEM_PROMPT = """You are an expert evaluator of research report outlines. Your job is to assess whether an outline has reached sufficient maturity to proceed to report drafting, or whether more research rounds are needed. Evaluate strictly and objectively."""

OUTLINE_MATURITY_EVAL_USER_PROMPT = """Evaluate the maturity of the following research outline.

## Topic
{topic}

## Current Outline
```
{outline}
```

## Evidence Base
Total learnings collected: {num_learnings}

## Evaluation Criteria

Score each dimension from 1-5 (half-point increments allowed, e.g. 3.5):

### Breadth & Coverage
- 1: Major aspects of the topic are missing; outline covers only a narrow slice.
- 2: Several important aspects missing; significant gaps remain.
- 3: Most major aspects covered, but 1-2 notable omissions; a few Gap lines remain.
- 4: Comprehensive coverage of the topic; at most 1 minor gap.
- 5: Thorough, exhaustive coverage; no remaining gaps; all important angles addressed.

### Depth & Evidence Density
- 1: Most sections have no or very few citations; evidence is superficial.
- 2: Some sections have citations but many points lack evidence; uneven depth.
- 3: Most sections have reasonable citation coverage; some points could be deeper.
- 4: Strong evidence density across sections; most points well-supported with multiple citations.
- 5: Every point has rich, multi-source evidence; deep sub-structure throughout.

### Coherence & Structure
- 1: Sections are disorganized, overlapping, or lack logical flow.
- 2: Some logical structure but with redundancies or awkward ordering.
- 3: Generally well-organized; minor overlaps or ordering issues.
- 4: Clear logical progression; well-structured hierarchy with minimal redundancy.
- 5: Excellent narrative flow; each section builds on the previous; no redundancy.

## Response Format
Return valid XML using exactly this structure:
<outline_evaluation>
  <breadth_and_coverage><score>X</score><justification>...</justification></breadth_and_coverage>
  <depth_and_evidence_density><score>X</score><justification>...</justification></depth_and_evidence_density>
  <coherence_and_structure><score>X</score><justification>...</justification></coherence_and_structure>
</outline_evaluation>"""
