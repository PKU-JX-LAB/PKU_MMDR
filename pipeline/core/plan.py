from .config import PLANNING_LLM_MODEL
from .llm_utils import chat_with_model
from .prompts import OUTLINE_SYSTEM_PROMPT, OUTLINE_USER_PROMPT
from .exemplar import DEFAULT_STYLE_GUIDE
import re


def _normalize_outline_format(outline):
    text = (outline or "").strip()
    if not text:
        return text

    text = re.sub(
        r"(?im)^\*\*Section\s+(\d+)\s+Title:\*\*\s*(.+?)\s*$",
        r"## Section \1\nTitle: \2",
        text,
    )
    text = re.sub(
        r"(?im)^\*\*Section\s+(\d+):\s*(.+?)\*\*\s*$",
        r"## Section \1\nTitle: \2",
        text,
    )
    text = re.sub(
        r"(?im)^\*\*Section\s+(\d+)\*\*\s*$\n^\*\*Title:\*\*\s*(.+?)\s*$",
        r"## Section \1\nTitle: \2",
        text,
    )
    text = re.sub(
        r"(?im)^\*\*Summary:\*\*\s*",
        "Summary: ",
        text,
    )
    text = re.sub(
        r"(?im)^Section\s+(\d+):\s*(.+?)\s*$",
        r"## Section \1\nTitle: \2",
        text,
    )
    text = re.sub(
        r"(?im)^Section\s+(\d+)\s+Title:\s*(.+?)\s*$",
        r"## Section \1\nTitle: \2",
        text,
    )
    text = re.sub(
        r"(?im)^##\s*Section\s+(\d+)\s+Title:\s*(.+?)\s*$",
        r"## Section \1\nTitle: \2",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def generate_plan(topic, learnings_str, exemplar_reports="", figure_plan_text=""):
    print("=== Generating Plan (Outline & Style Guide) ===")
    
    if not exemplar_reports:
        exemplar_reports = "No specific exemplars provided. Follow standard professional report style."
        
    system_prompt = OUTLINE_SYSTEM_PROMPT.format(list_of_example_reports=exemplar_reports)
    user_prompt = OUTLINE_USER_PROMPT.format(
        topic=topic,
        learning_str=learnings_str
    )
    if figure_plan_text:
        user_prompt += (
            "\n\n## Candidate Figure Evidence\n"
            "Use these figure candidates as optional planning evidence. "
            "If useful, align sections with them and indicate where visual evidence is most needed.\n"
            f"{figure_plan_text}"
        )
    
    response = chat_with_model(PLANNING_LLM_MODEL, system_prompt, user_prompt)
    

    style_guide = ""
    outline = ""
    
    if "<style_guide>" in response and "</style_guide>" in response:
        style_guide = response.split("<style_guide>")[1].split("</style_guide>")[0].strip()
    else:
        style_guide = DEFAULT_STYLE_GUIDE
        
    if "<outline>" in response and "</outline>" in response:
        outline = response.split("<outline>")[1].split("</outline>")[0].strip()
    else:
        outline = response

    outline = _normalize_outline_format(outline)
        
    return outline, style_guide
