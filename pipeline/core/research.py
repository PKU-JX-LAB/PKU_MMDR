import requests
import json
import re
from urllib.parse import urlparse
from .config import (
    FIRECRAWL_API_KEY,
    FIRECRAWL_API_KEYS,
    N_R,
    N_K,
    N_P,
    N_L,
    RESEARCH_LLM_MODEL,
    ADAPTIVE_OUTLINE,
    ADAPTIVE_EARLY_STOP,
    ADAPTIVE_EARLY_STOP_THRESHOLD,
    ADAPTIVE_EARLY_STOP_MIN_ROUNDS,
)
from .artifact_utils import save_json
from .llm_utils import chat_with_model
from .prompts import (
    SERP_QUERY_SYSTEM_PROMPT, SERP_QUERY_USER_PROMPT,
    LEARNING_GENERATION_SYSTEM_PROMPT, LEARNING_GENERATION_USER_PROMPT,
    ADAPTIVE_OUTLINE_INIT_SYSTEM_PROMPT, ADAPTIVE_OUTLINE_INIT_USER_PROMPT,
    ADAPTIVE_OUTLINE_UPDATE_SYSTEM_PROMPT, ADAPTIVE_OUTLINE_UPDATE_USER_PROMPT,
    ADAPTIVE_OUTLINE_GUIDED_QUERY_SYSTEM_PROMPT, ADAPTIVE_OUTLINE_GUIDED_QUERY_USER_PROMPT,
    OUTLINE_MATURITY_EVAL_SYSTEM_PROMPT, OUTLINE_MATURITY_EVAL_USER_PROMPT,
)


def _extract_text_window(text, start, end, window=140):
    before = text[max(0, start - window):start].replace("\n", " ").strip()
    after = text[end:min(len(text), end + window)].replace("\n", " ").strip()
    around = text[max(0, start - window):min(len(text), end + window)].replace("\n", " ").strip()
    return before, after, around


def _build_image_reference(*, img_id, url, alt_text, raw_text, start, end, page_url, page_title, query, iteration, source_kind):
    before, after, around = _extract_text_window(raw_text, start, end)
    parsed = urlparse(url)
    return {
        "image_id": img_id,
        "url": url,
        "alt_text": alt_text,
        "page_url": page_url or "",
        "page_title": page_title or "",
        "query": query,
        "iteration": iteration,
        "source_kind": source_kind,
        "source_domain": parsed.netloc.lower(),
        "context_before": before,
        "context_after": after,
        "surrounding_text": around,
    }


def _mask_api_key(api_key):
    if not api_key:
        return "unknown"
    if len(api_key) <= 8:
        return api_key
    return f"{api_key[:5]}...{api_key[-4:]}"


def search_web(query):
    import time
    print(f"--- Searching web for: {query} ---")
    url = "https://api.firecrawl.dev/v1/search"
    data = {"query": query, "limit": N_P, "scrapeOptions": {"formats": ["markdown"]}}

    # Optional proxies if needed, otherwise rely on env vars
    proxies = {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }

    search_keys = FIRECRAWL_API_KEYS or [FIRECRAWL_API_KEY]

    for key_index, api_key in enumerate(search_keys, start=1):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        key_label = _mask_api_key(api_key)

        for attempt in range(1, 4):
            try:
                # Using proxies explicitely if there is a proxy issue
                try:
                    response = requests.post(
                        url,
                        headers=headers,
                        json=data,
                        verify=False,
                        timeout=(10, 30),
                        proxies=proxies,
                    )
                except Exception:
                    # Fallback without explicit proxies
                    response = requests.post(
                        url,
                        headers=headers,
                        json=data,
                        verify=False,
                        timeout=(10, 30),
                    )

                response.raise_for_status()
                res = response.json()
                items = res.get("data", [])
                if items:
                    if key_index > 1:
                        print(f"Search succeeded with fallback Firecrawl key {key_index}/{len(search_keys)} ({key_label}).")
                    return items
                return []
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None
                print(f"Search failed (key {key_index}/{len(search_keys)} {key_label}, attempt {attempt}): {e}")
                # Switch keys immediately when a key is unauthorized, out of quota, or rate-limited.
                if status_code in {401, 402, 429}:
                    break
                if attempt < 3:
                    time.sleep(2 * attempt)
            except Exception as e:
                print(f"Search failed (key {key_index}/{len(search_keys)} {key_label}, attempt {attempt}): {e}")
                if attempt < 3:
                    time.sleep(2 * attempt)
    return []

def extract_learnings(contents, query):
    prompt = LEARNING_GENERATION_USER_PROMPT.format(
        query=query,
        learning_num=N_L,
        question_num=2,
        contents=contents
    )
    res = chat_with_model(RESEARCH_LLM_MODEL, LEARNING_GENERATION_SYSTEM_PROMPT, prompt)
    return res

def _format_learnings_with_ids(learnings, start_id=1):
    """Format learnings with L-prefixed IDs for adaptive outline referencing."""
    lines = []
    for idx, l in enumerate(learnings, start=start_id):
        lines.append(f"[L{idx}] {l}")
    return "\n".join(lines)


def _init_adaptive_outline(topic, learnings):
    """Generate the first adaptive outline from initial learnings."""
    print("--- Adaptive Outline: Initializing ---")
    learning_str = _format_learnings_with_ids(learnings)
    response = chat_with_model(
        RESEARCH_LLM_MODEL,
        ADAPTIVE_OUTLINE_INIT_SYSTEM_PROMPT,
        ADAPTIVE_OUTLINE_INIT_USER_PROMPT.format(
            topic=topic,
            learning_str=learning_str,
        ),
    )
    if "<adaptive_outline>" in response and "</adaptive_outline>" in response:
        return response.split("<adaptive_outline>")[1].split("</adaptive_outline>")[0].strip()
    return response.strip()


def _update_adaptive_outline(topic, current_outline, new_learnings, all_learnings, round_num):
    """Update the adaptive outline with new learnings from the latest round."""
    print(f"--- Adaptive Outline: Updating (round {round_num}) ---")
    all_str = _format_learnings_with_ids(all_learnings)
    # Build new learnings string with correct global IDs
    new_start = len(all_learnings) - len(new_learnings) + 1
    new_str = _format_learnings_with_ids(new_learnings, start_id=new_start)
    response = chat_with_model(
        RESEARCH_LLM_MODEL,
        ADAPTIVE_OUTLINE_UPDATE_SYSTEM_PROMPT,
        ADAPTIVE_OUTLINE_UPDATE_USER_PROMPT.format(
            topic=topic,
            current_outline=current_outline,
            new_learnings_str=new_str,
            all_learnings_str=all_str,
            round_num=round_num,
        ),
    )
    if "<adaptive_outline>" in response and "</adaptive_outline>" in response:
        return response.split("<adaptive_outline>")[1].split("</adaptive_outline>")[0].strip()
    return response.strip()


def _generate_outline_guided_queries(
    topic,
    current_outline,
    recent_learnings,
    n_queries,
    current_topic=None,
    previous_queries=None,
):
    """Generate search queries guided by outline gaps."""
    print("--- Adaptive Outline: Generating outline-guided queries ---")
    recent_str = "\n".join(f"- {l}" for l in recent_learnings) if recent_learnings else "None"
    prev_queries_str = "\n".join(f"- {q}" for q in previous_queries) if previous_queries else "None"
    response = chat_with_model(
        RESEARCH_LLM_MODEL,
        ADAPTIVE_OUTLINE_GUIDED_QUERY_SYSTEM_PROMPT,
        ADAPTIVE_OUTLINE_GUIDED_QUERY_USER_PROMPT.format(
            topic=topic,
            current_topic=current_topic or topic,
            current_outline=current_outline,
            recent_learnings=recent_str,
            previous_queries=prev_queries_str,
            queries_num=n_queries,
        ),
    )
    return response


def _evaluate_outline_maturity(topic, outline, all_learning_items):
    """Evaluate outline maturity for early-stop decision. Returns (avg_score, scores_dict)."""
    print("--- Outline Maturity: Evaluating ---")
    response = chat_with_model(
        RESEARCH_LLM_MODEL,
        OUTLINE_MATURITY_EVAL_SYSTEM_PROMPT,
        OUTLINE_MATURITY_EVAL_USER_PROMPT.format(
            topic=topic,
            outline=outline,
            num_learnings=len(all_learning_items),
        ),
    )
    dimensions = ["breadth_and_coverage", "depth_and_evidence_density", "coherence_and_structure"]
    scores = {}
    for dim in dimensions:
        match = re.search(rf"<{dim}>\s*<score>([\d.]+)</score>", response)
        scores[dim] = float(match.group(1)) if match else 0.0
    avg = sum(scores.values()) / len(scores) if scores else 0.0
    return avg, scores


def do_research(topic, output_dir=None):
    print(f"=== Starting Research for topic: {topic} ===")
    learnings = []
    questions = []

    current_topic = topic

    image_mapping = {}
    image_references = []
    image_counter = 1

    # Adaptive outline state (only used when ADAPTIVE_OUTLINE=True)
    adaptive_outline = None
    # Flat list of individual learning strings for ID tracking
    all_learning_items = []
    # Track all used queries for dedup (adaptive mode)
    all_used_queries = []
    # Track most recent round's learnings for query generation
    latest_round_items = []

    for i in range(N_R):
        print(f"--- Iteration {i+1}/{N_R} ---")
        learning_str = "\n".join(learnings) if learnings else "None"

        # --- Query generation: outline-guided vs. default ---
        if ADAPTIVE_OUTLINE and adaptive_outline is not None:
            queries_text = _generate_outline_guided_queries(
                topic,
                adaptive_outline,
                latest_round_items,
                N_K,
                current_topic=current_topic,
                previous_queries=all_used_queries,
            )
        else:
            query_prompt = SERP_QUERY_USER_PROMPT.format(
                queries_num=N_K,
                query=current_topic,
                learning_str=learning_str
            )
            queries_text = chat_with_model(RESEARCH_LLM_MODEL, SERP_QUERY_SYSTEM_PROMPT, query_prompt)


        queries = [q.strip("- *1234567890.\"'""''") for q in queries_text.split('\n') if q.strip()]
        queries = queries[:N_K]
        if ADAPTIVE_OUTLINE:
            all_used_queries.extend(queries)

        iteration_learnings = []
        for q in queries:
            results = search_web(q)
            contents = ""
            for res in results:
                if 'markdown' in res:
                    md_text = res['markdown']
                    page_url = res.get("url", "")
                    page_title = res.get("title", "")
                    
                    def is_valid_image(url, alt_text):
                        lower_url = url.lower()
                        if lower_url.endswith('.svg') or lower_url.endswith('.gif') or lower_url.startswith('data:image'):
                            return False
                        invalid_keywords = ['icon', 'logo', 'avatar', 'profile', 'facebook', 'twitter', 'linkedin', 'instagram', 'social', 'button', 'badge', 'banner', 'thumbnail', 'emoji', 'sticker', 'reaction']
                        for kw in invalid_keywords:
                            if kw in lower_url or kw in alt_text.lower():
                                return False
                                
                        invalid_domains = ['pic1.zhimg.com', 'pic2.zhimg.com', 'pic3.zhimg.com', 'pic4.zhimg.com']
                        for domain in invalid_domains:
                            if domain in lower_url and ('v2-' in lower_url or '50' in lower_url):
                                if 'v2-' in lower_url and len(lower_url.split('/')[-1]) < 20: 
                                    return False
                                    
                        try:
                            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                            r = requests.head(url, headers=headers, timeout=2, verify=False, allow_redirects=True)
                            if r.status_code >= 400:
                                return False
                            content_type = r.headers.get('Content-Type', '')
                            if not content_type.startswith('image/'):
                                return False
                                
                            # Filter small images/icons based on Content-Length (if available)
                            content_length = r.headers.get('Content-Length')
                            if content_length and int(content_length) < 30000: # 30KB
                                return False
                        except Exception:
                            return False
                            
                        return True

                    raw_md_text = md_text

                    page_img_count = 0

                    def repl_md(match):
                        nonlocal image_counter, page_img_count
                        if page_img_count >= 15:
                            return ""
                        alt_text = match.group(1).replace('\n', ' ').strip()
                        url = match.group(2).strip()
                        
                        if not is_valid_image(url, alt_text):
                            return ""
                            
                        page_img_count += 1
                        img_id = f"Image_{image_counter}"
                        image_counter += 1
                        image_mapping[img_id] = url
                        image_references.append(
                            _build_image_reference(
                                img_id=img_id,
                                url=url,
                                alt_text=alt_text,
                                raw_text=raw_md_text,
                                start=match.start(),
                                end=match.end(),
                                page_url=page_url,
                                page_title=page_title,
                                query=q,
                                iteration=i + 1,
                                source_kind="markdown_image",
                            )
                        )
                        return f"[{img_id}: {alt_text}]"
                    md_text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', repl_md, md_text)
                    
                    html_capture_text = md_text

                    def repl_html(match):
                        nonlocal image_counter, page_img_count
                        if page_img_count >= 15:
                            return ""
                        url = match.group(1).strip()
                        
                        if not is_valid_image(url, ""):
                            return ""
                            
                        page_img_count += 1
                        img_id = f"Image_{image_counter}"
                        image_counter += 1
                        image_mapping[img_id] = url
                        image_references.append(
                            _build_image_reference(
                                img_id=img_id,
                                url=url,
                                alt_text="",
                                raw_text=html_capture_text,
                                start=match.start(),
                                end=match.end(),
                                page_url=page_url,
                                page_title=page_title,
                                query=q,
                                iteration=i + 1,
                                source_kind="html_img_tag",
                            )
                        )
                        return f"[{img_id}: image]"
                    md_text = re.sub(r'<img[^>]+src="([^"]+)"[^>]*>', repl_html, md_text)
                    
                    contents += md_text + "\n\n"
                elif 'description' in res:
                    contents += res['description'] + "\n\n"
            
            if contents:

                contents = contents[:8000]
                extracted = extract_learnings(contents, q)
                iteration_learnings.append(extracted)
        
        learnings.extend(iteration_learnings)

        # --- Adaptive outline: extract individual learning items & update outline ---
        if ADAPTIVE_OUTLINE:
            # Parse individual learning bullets from raw extracted text
            round_items = []
            for raw in iteration_learnings:
                # Strip <questions> block if present
                body = raw.split("<questions>")[0] if "<questions>" in raw else raw
                for line in body.split("\n"):
                    line = line.strip().lstrip("- *")
                    if line and len(line) > 20:
                        round_items.append(line)
            all_learning_items.extend(round_items)
            latest_round_items = round_items

            if round_items:
                if adaptive_outline is None:
                    # First time we have learnings: create initial outline
                    adaptive_outline = _init_adaptive_outline(topic, all_learning_items)
                else:
                    # Update existing outline with new evidence
                    adaptive_outline = _update_adaptive_outline(
                        topic, adaptive_outline, round_items, all_learning_items, i + 1
                    )
                # Save intermediate outline
                if output_dir and adaptive_outline:
                    import os
                    outline_path = os.path.join(output_dir, "adaptive_outline.md")
                    with open(outline_path, "w", encoding="utf-8") as f:
                        f.write(adaptive_outline)
                    round_path = os.path.join(output_dir, f"adaptive_outline_round_{i+1}.md")
                    with open(round_path, "w", encoding="utf-8") as f:
                        f.write(adaptive_outline)
                    print(f"--- Adaptive Outline saved to {outline_path} & {round_path} ---")
                if ADAPTIVE_EARLY_STOP and adaptive_outline and (i + 1) >= ADAPTIVE_EARLY_STOP_MIN_ROUNDS:
                    avg_score, eval_scores = _evaluate_outline_maturity(topic, adaptive_outline, all_learning_items)
                    print(f"--- Outline Maturity: {avg_score:.1f}/5.0 (threshold: {ADAPTIVE_EARLY_STOP_THRESHOLD}) ---")
                    for dim, sc in eval_scores.items():
                        print(f"    {dim}: {sc}")
                    if output_dir:
                        save_json(
                            os.path.join(output_dir, f"outline_eval_round_{i+1}.json"),
                            {
                                "round": i + 1,
                                "avg_score": avg_score,
                                "scores": eval_scores,
                            },
                        )
                    if avg_score >= ADAPTIVE_EARLY_STOP_THRESHOLD:
                        print(f"--- Early stop triggered at round {i+1}/{N_R} ---")
                        break
            else:
                print(f"--- Adaptive Outline: No new learnings in round {i+1}, skipping update ---")

        if iteration_learnings:

            last_extracted = iteration_learnings[-1]
            if "<questions>" in last_extracted:
                q_part = last_extracted.split("<questions>")[1].split("</questions>")[0]
                qs = [q.strip("- *") for q in q_part.split('\n') if q.strip()]
                if qs:
                    current_topic = qs[0]
                    
    if output_dir and image_mapping:
        import os
        save_json(os.path.join(output_dir, "images_mapping.json"), image_mapping)
        save_json(os.path.join(output_dir, "image_references.json"), image_references)

    result_learnings = "\n".join(learnings)
    if ADAPTIVE_OUTLINE:
        id_map = {f"L{idx}": text for idx, text in enumerate(all_learning_items, start=1)}
        if output_dir:
            save_json(os.path.join(output_dir, "learning_id_map.json"), id_map)
        return result_learnings, adaptive_outline, id_map
    return result_learnings
