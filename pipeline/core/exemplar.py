from .config import EXEMPLAR_MLLM_MODEL
from .llm_utils import chat_with_image
from .prompts import FDV_EXTRACTION_SYSTEM_PROMPT, FDV_EXTRACTION_USER_PROMPT

def extract_fdv_from_image(image_path):
    print(f"=== Extracting FDV from {image_path} ===")
    fdv = chat_with_image(
        EXEMPLAR_MLLM_MODEL,
        FDV_EXTRACTION_SYSTEM_PROMPT,
        FDV_EXTRACTION_USER_PROMPT,
        image_path
    )
    return fdv


DEFAULT_STYLE_GUIDE = """<style_guide>
* **Base Design Elements:** Use a professional and modern color palette. Use deep blue (#1f77b4) for primary data, orange (#ff7f0e) for secondary comparisons, and subtle gray (#7f7f7f) for background elements or less important data.
* **Typography:** Use sans-serif fonts like Arial or Helvetica. Main titles should be bold and 16px-20px. Axis labels and legends should be 12px.
* **Layout:** Ensure adequate margins (e.g., 40px left/bottom, 20px top/right). Avoid overlapping elements.
</style_guide>"""
