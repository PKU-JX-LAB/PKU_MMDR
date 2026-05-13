#!/usr/bin/env python
from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from markdown_it import MarkdownIt


HTML_RENDERER_RE = re.compile(r'<HTMLRenderer\s+htmlFile="([^"]+)"\s*/?>', flags=re.IGNORECASE)
IMAGE_ONLY_RE = re.compile(r'^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
ORDERED_RE = re.compile(r'^\d+\.\s+(.*)$')
UNORDERED_RE = re.compile(r'^[-*+]\s+(.*)$')
TABLE_SEP_RE = re.compile(r'^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$')
INLINE_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
INLINE_LINK_RE = re.compile(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)')
INLINE_CODE_RE = re.compile(r'`([^`]+)`')
INLINE_BOLD_RE = re.compile(r'\*\*([^*]+)\*\*')
INLINE_ITALIC_RE = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)')
FOOTNOTE_REF_RE = re.compile(r'\[\^([A-Za-z0-9_-]+)\]')
FOOTNOTE_DEF_RE = re.compile(r'^\[\^([A-Za-z0-9_-]+)\]:\s*(.*)$')
BARE_URL_RE = re.compile(r'(?<!["=])(https?://[^\s<]+)')
SRC_ATTR_RE = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")', flags=re.IGNORECASE)


DEFAULT_BROWSER_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def find_browser(explicit: str | None) -> Path:
    if explicit:
        browser = Path(explicit)
        if browser.exists():
            return browser
        raise FileNotFoundError(f"Browser not found: {browser}")
    for candidate in DEFAULT_BROWSER_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No supported browser found. Please pass --browser.")


def resolve_src(src: str, report_dir: Path) -> str:
    src = src.strip()
    parsed = urlparse(src)
    if parsed.scheme in {"http", "https", "data", "file"}:
        return src
    local_path = (report_dir / src).resolve()
    return local_path.as_uri()


def chart_screenshot_uri(html_file: str, report_dir: Path) -> str:
    html_path = (report_dir / html_file).resolve()
    screenshot = html_path.with_name(f"{html_path.stem}_screenshot.png")
    if screenshot.exists():
        return screenshot.as_uri()
    return ""


def footnote_html_id(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-").lower()
    return f"fn-{safe or 'ref'}"


def linkify_plain_urls(text: str) -> str:
    return BARE_URL_RE.sub(
        lambda match: f'<a href="{html.escape(match.group(1), quote=True)}">{html.escape(match.group(1))}</a>',
        text,
    )


def build_footnote_ref_html(label: str, number: int) -> str:
    target = html.escape(footnote_html_id(label), quote=True)
    return f'<sup class="footnote-ref"><a href="#{target}">[{number}]</a></sup>'


def build_chart_html(html_file: str, report_dir: Path) -> str:
    uri = chart_screenshot_uri(html_file, report_dir)
    if not uri:
        missing = html.escape(html_file)
        return f'<div class="missing-chart">Missing chart screenshot for {missing}</div>'
    caption = html.escape(Path(html_file).stem)
    return (
        '<figure class="generated-chart">'
        f'<img src="{html.escape(uri, quote=True)}" alt="{caption}">'
        '</figure>'
    )


def preprocess_markdown(markdown_text: str, report_dir: Path) -> tuple[str, list[tuple[int, str, str]]]:
    footnote_defs: dict[str, str] = {}
    content_lines: list[str] = []

    for line in markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = FOOTNOTE_DEF_RE.match(line.strip())
        if match:
            footnote_defs[match.group(1)] = match.group(2).strip()
            continue
        content_lines.append(line)

    content_text = "\n".join(content_lines)
    content_text = HTML_RENDERER_RE.sub(
        lambda match: build_chart_html(match.group(1), report_dir),
        content_text,
    )
    footnote_order: list[str] = []

    def replace_ref(match: re.Match[str]) -> str:
        label = match.group(1)
        if label not in footnote_order:
            footnote_order.append(label)
        return build_footnote_ref_html(label, footnote_order.index(label) + 1)

    content_text = FOOTNOTE_REF_RE.sub(
        replace_ref,
        content_text,
    )
    ordered_footnotes: list[tuple[int, str, str]] = []
    for number, label in enumerate(footnote_order, start=1):
        if label in footnote_defs:
            ordered_footnotes.append((number, label, footnote_defs[label]))
    return content_text, ordered_footnotes


def render_footnotes_html(footnotes: list[tuple[int, str, str]]) -> str:
    if not footnotes:
        return ""

    items = []
    for number, label, raw_content in footnotes:
        content = linkify_plain_urls(html.escape(raw_content))
        footnote_id = html.escape(footnote_html_id(label), quote=True)
        items.append(
            f'<p id="{footnote_id}" class="footnote-def">'
            f'<sup class="footnote-label">[{number}]</sup> {content}'
            "</p>"
        )

    return '<hr class="footnotes-sep">\n<div class="footnotes">\n' + "\n".join(items) + "\n</div>"


def resolve_img_srcs(rendered_html: str, report_dir: Path) -> str:
    def repl(match: re.Match[str]) -> str:
        raw_src = html.unescape(match.group(2))
        resolved = html.escape(resolve_src(raw_src, report_dir), quote=True)
        return f"{match.group(1)}{resolved}{match.group(3)}"

    return SRC_ATTR_RE.sub(repl, rendered_html)


def split_blocks(text: str) -> list[list[str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[list[str]] = []
    current: list[str] = []
    in_fenced_code = False

    def flush_current() -> None:
        nonlocal current
        if current:
            blocks.append(current)
            current = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if not in_fenced_code:
                flush_current()
            current.append(line)
            in_fenced_code = not in_fenced_code
            if not in_fenced_code:
                flush_current()
            continue

        if in_fenced_code:
            current.append(line)
            continue

        if stripped == "":
            flush_current()
            continue

        if HEADING_RE.match(line):
            flush_current()
            blocks.append([line])
            continue

        current.append(line)

    flush_current()
    return blocks


def render_inline(text: str, report_dir: Path) -> str:
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"@@PLACEHOLDER_{len(placeholders)-1}@@"

    def image_repl(match: re.Match[str]) -> str:
        alt = html.escape(match.group(1))
        src = html.escape(resolve_src(match.group(2), report_dir), quote=True)
        return stash(f'<img class="inline-image" src="{src}" alt="{alt}">')

    def link_repl(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        href = html.escape(match.group(2), quote=True)
        return stash(f'<a href="{href}">{label}</a>')

    def code_repl(match: re.Match[str]) -> str:
        return stash(f"<code>{html.escape(match.group(1))}</code>")

    def footnote_ref_repl(match: re.Match[str]) -> str:
        label = match.group(1)
        safe_label = html.escape(label)
        target = html.escape(footnote_html_id(label), quote=True)
        return stash(f'<sup class="footnote-ref"><a href="#{target}">[{safe_label}]</a></sup>')

    text = INLINE_IMAGE_RE.sub(image_repl, text)
    text = INLINE_LINK_RE.sub(link_repl, text)
    text = INLINE_CODE_RE.sub(code_repl, text)
    text = FOOTNOTE_REF_RE.sub(footnote_ref_repl, text)
    text = html.escape(text)
    text = INLINE_BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = INLINE_ITALIC_RE.sub(r"<em>\1</em>", text)
    text = BARE_URL_RE.sub(r'<a href="\1">\1</a>', text)

    for idx, value in enumerate(placeholders):
        text = text.replace(f"@@PLACEHOLDER_{idx}@@", value)
    return text


def render_image_block(lines: list[str], report_dir: Path) -> str | None:
    if len(lines) != 1:
        return None
    match = IMAGE_ONLY_RE.match(lines[0])
    if not match:
        return None
    alt = match.group(1).strip()
    src = resolve_src(match.group(2), report_dir)
    caption = f"<figcaption>{html.escape(alt)}</figcaption>" if alt else ""
    return (
        '<figure class="report-image">'
        f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt)}">'
        f"{caption}</figure>"
    )


def render_htmlrenderer_block(lines: list[str], report_dir: Path) -> str | None:
    if len(lines) != 1:
        return None
    match = HTML_RENDERER_RE.match(lines[0].strip())
    if not match:
        return None
    uri = chart_screenshot_uri(match.group(1), report_dir)
    if not uri:
        missing = html.escape(match.group(1))
        return f'<div class="missing-chart">Missing chart screenshot for {missing}</div>'
    caption = html.escape(Path(match.group(1)).stem)
    return (
        '<figure class="generated-chart">'
        f'<img src="{html.escape(uri, quote=True)}" alt="{caption}">'
        '</figure>'
    )


def render_heading_block(lines: list[str], report_dir: Path) -> str | None:
    if len(lines) != 1:
        return None
    match = HEADING_RE.match(lines[0])
    if not match:
        return None
    level = len(match.group(1))
    content = render_inline(match.group(2).strip(), report_dir)
    return f"<h{level}>{content}</h{level}>"


def render_rule_block(lines: list[str]) -> str | None:
    if len(lines) == 1 and lines[0].strip() in {"---", "***"}:
        return "<hr>"
    return None


def render_list_block(lines: list[str], report_dir: Path) -> str | None:
    ordered = all(ORDERED_RE.match(line) for line in lines)
    unordered = all(UNORDERED_RE.match(line) for line in lines)
    if not ordered and not unordered:
        return None
    tag = "ol" if ordered else "ul"
    items = []
    for line in lines:
        content = ORDERED_RE.match(line).group(1) if ordered else UNORDERED_RE.match(line).group(1)
        items.append(f"<li>{render_inline(content.strip(), report_dir)}</li>")
    return f"<{tag}>\n" + "\n".join(items) + f"\n</{tag}>"


def parse_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def render_table_block(lines: list[str], report_dir: Path) -> str | None:
    if len(lines) < 2:
        return None
    if "|" not in lines[0] or not TABLE_SEP_RE.match(lines[1]):
        return None
    headers = parse_table_row(lines[0])
    body_rows = [parse_table_row(line) for line in lines[2:]]
    thead = "<thead><tr>" + "".join(f"<th>{render_inline(cell, report_dir)}</th>" for cell in headers) + "</tr></thead>"
    tbody_rows = []
    for row in body_rows:
        tbody_rows.append("<tr>" + "".join(f"<td>{render_inline(cell, report_dir)}</td>" for cell in row) + "</tr>")
    tbody = "<tbody>" + "".join(tbody_rows) + "</tbody>"
    return f'<div class="table-wrap"><table>{thead}{tbody}</table></div>'


def render_blockquote_block(lines: list[str], report_dir: Path) -> str | None:
    if not all(line.lstrip().startswith(">") for line in lines):
        return None
    content = " ".join(line.lstrip()[1:].strip() for line in lines)
    return f"<blockquote>{render_inline(content, report_dir)}</blockquote>"


def render_code_block(lines: list[str]) -> str | None:
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
        code = "\n".join(lines[1:-1])
        return f"<pre><code>{html.escape(code)}</code></pre>"
    return None


def render_footnote_def_block(lines: list[str], report_dir: Path) -> str | None:
    matches = [FOOTNOTE_DEF_RE.match(line.strip()) for line in lines]
    if not matches or any(match is None for match in matches):
        return None

    items = []
    for match in matches:
        label = match.group(1)
        content = render_inline(match.group(2).strip(), report_dir)
        footnote_id = html.escape(footnote_html_id(label), quote=True)
        safe_label = html.escape(label)
        items.append(
            f'<p id="{footnote_id}" class="footnote-def">'
            f'<sup class="footnote-label">[{safe_label}]</sup> {content}'
            "</p>"
        )
    return '<div class="footnotes">\n' + "\n".join(items) + "\n</div>"


def render_paragraph_block(lines: list[str], report_dir: Path) -> str:
    content = " ".join(line.strip() for line in lines)
    return f"<p>{render_inline(content, report_dir)}</p>"


def markdown_to_html(markdown_text: str, report_dir: Path) -> str:
    prepared_markdown, footnotes = preprocess_markdown(markdown_text, report_dir)
    md = MarkdownIt("default", {"html": True, "breaks": False})
    body_html = md.render(prepared_markdown)
    body_html = resolve_img_srcs(body_html, report_dir)
    return body_html + ("\n" + render_footnotes_html(footnotes) if footnotes else "")


def build_full_html(title: str, body_html: str) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    @page {{
      size: A4;
      margin: 18mm 14mm 18mm 14mm;
    }}
    body {{
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
      color: #1f2328;
      line-height: 1.72;
      font-size: 14px;
      margin: 0;
      background: #ffffff;
    }}
    main {{
      max-width: 820px;
      margin: 0 auto;
    }}
    h1, h2, h3, h4, h5, h6 {{
      line-height: 1.3;
      margin: 1.2em 0 0.55em;
      color: #111827;
    }}
    h1 {{ font-size: 28px; }}
    h2 {{
      font-size: 22px;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 0.25em;
    }}
    h3 {{ font-size: 18px; }}
    p, ul, ol, blockquote, table, pre {{
      margin: 0.75em 0;
    }}
    ul, ol {{
      padding-left: 1.5em;
    }}
    code {{
      background: #f3f4f6;
      border-radius: 4px;
      padding: 0.1em 0.35em;
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.92em;
    }}
    pre {{
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 12px 14px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    pre code {{
      background: transparent;
      padding: 0;
    }}
    blockquote {{
      border-left: 4px solid #d1d5db;
      padding: 0.1em 0 0.1em 1em;
      color: #4b5563;
      background: #fafafa;
    }}
    hr {{
      border: 0;
      border-top: 1px solid #e5e7eb;
      margin: 1.6em 0;
    }}
    figure {{
      margin: 1.2em 0 1.5em;
      page-break-inside: avoid;
      break-inside: avoid;
    }}
    img {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }}
    figure img {{
      display: block;
      width: 100%;
      max-width: 100%;
      height: auto;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #fff;
    }}
    figcaption {{
      text-align: center;
      color: #6b7280;
      font-size: 12px;
      margin-top: 0.5em;
    }}
    .generated-chart img {{
      border-radius: 12px;
      box-shadow: 0 8px 20px rgba(0,0,0,0.06);
    }}
    .inline-image {{
      max-width: 100%;
      vertical-align: middle;
    }}
    .missing-chart {{
      border: 1px dashed #ef4444;
      color: #b91c1c;
      background: #fef2f2;
      padding: 12px;
      border-radius: 8px;
      margin: 1em 0;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 1em 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 8px 10px;
      vertical-align: top;
    }}
    th {{
      background: #f9fafb;
      text-align: left;
    }}
    .footnote-ref {{
      font-size: 0.82em;
      vertical-align: super;
      line-height: 0;
      margin-left: 0.08em;
    }}
    .footnotes {{
      margin-top: 1em;
      padding-top: 0.5em;
    }}
    .footnote-def {{
      font-size: 13px;
      color: #374151;
      margin: 0.55em 0;
    }}
    .footnote-label {{
      font-size: 0.92em;
      margin-right: 0.25em;
    }}
    a {{
      color: #0f62fe;
      text-decoration: none;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <main>
{body_html}
  </main>
</body>
</html>
"""


def render_pdf(markdown_path: Path, output_pdf: Path, browser_path: Path, keep_html: bool, wait_ms: int) -> Path:
    report_dir = markdown_path.parent
    markdown_text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    body_html = markdown_to_html(markdown_text, report_dir)
    title = markdown_path.stem
    full_html = build_full_html(title, body_html)

    if keep_html:
        html_path = output_pdf.with_suffix(".html")
        html_path.write_text(full_html, encoding="utf-8")
    else:
        tmp_dir = Path(tempfile.mkdtemp(prefix="report_pdf_"))
        html_path = tmp_dir / f"{markdown_path.stem}.html"
        html_path.write_text(full_html, encoding="utf-8")

    cmd = [
        str(browser_path),
        "--headless",
        "--disable-gpu",
        "--allow-file-access-from-files",
        f"--virtual-time-budget={wait_ms}",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={str(output_pdf)}",
        html_path.resolve().as_uri(),
    ]
    subprocess.run(cmd, check=True)
    return output_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a generated markdown report to PDF with charts and images.")
    parser.add_argument("markdown_path", help="Path to final_report.md")
    parser.add_argument("--output", help="Output PDF path. Defaults to same name with .pdf suffix.")
    parser.add_argument("--browser", help="Path to Edge/Chrome executable.")
    parser.add_argument("--keep-html", action="store_true", help="Keep the intermediate rendered HTML next to the PDF.")
    parser.add_argument("--wait-ms", type=int, default=15000, help="Browser virtual time budget in milliseconds.")
    args = parser.parse_args()

    markdown_path = Path(args.markdown_path).resolve()
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    output_pdf = Path(args.output).resolve() if args.output else markdown_path.with_suffix(".pdf")
    browser = find_browser(args.browser)
    render_pdf(markdown_path, output_pdf, browser, args.keep_html, args.wait_ms)
    print(f"PDF saved to {output_pdf}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"Browser PDF render failed with exit code {exc.returncode}", file=sys.stderr)
        raise
