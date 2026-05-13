import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).parent / ".env")

def _get_bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_optional_int_env(name, default=None):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    parsed = int(value)
    if parsed <= 0:
        return default
    return parsed


def _get_cli_arg_value(flag):
    argv = sys.argv[1:]
    prefix = f"{flag}="
    for idx, arg in enumerate(argv):
        if arg == flag and idx + 1 < len(argv):
            return argv[idx + 1]
        if arg.startswith(prefix):
            return arg[len(prefix):]
    return None


def _get_api_key_list_env(list_name, single_name, defaults):
    raw = os.environ.get(list_name)
    if raw and raw.strip():
        normalized = raw.replace("\r", ",").replace("\n", ",").replace(";", ",")
        parsed = [item.strip() for item in normalized.split(",") if item.strip()]
        if parsed:
            return parsed

    single = os.environ.get(single_name)
    if single and single.strip():
        return [single.strip()]

    return list(defaults)


def _normalize_ablation_mode(value):
    normalized = (value or "none").strip().lower().replace("-", "_")
    aliases = {
        "none": "none",
        "off": "none",
        "default": "none",
        "section": "section_generation",
        "section_generation": "section_generation",
        "storm": "section_generation",
        "storm_like": "section_generation",
        "image": "image_enrichment",
        "image_enrichment": "image_enrichment",
        "contextual_image": "image_enrichment",
        "contextual_image_enrichment": "image_enrichment",
        "weak_metadata": "weak_metadata",
        "image_weak_metadata": "weak_metadata",
        "weak_image_metadata": "weak_metadata",
        "adaptive_outline": "adaptive_outline",
        "outline": "adaptive_outline",
    }
    if normalized not in aliases:
        raise ValueError(
            "Unsupported ablation mode: "
            f"{value}. Expected one of: none, section_generation, image_enrichment, weak_metadata, adaptive_outline."
        )
    return aliases[normalized]


ABLATION_MODE = _normalize_ablation_mode(
    _get_cli_arg_value("--ablation") or os.environ.get("MDR_ABLATION_MODE")
)
os.environ["MDR_ABLATION_MODE"] = ABLATION_MODE

ABLATION_LABELS = {
    "none": "default",
    "section_generation": "ablate_section_generation",
    "image_enrichment": "ablate_image_enrichment",
    "weak_metadata": "ablate_weak_metadata_image_selection",
    "adaptive_outline": "adaptive_outline",
}
ACTIVE_ABLATION_LABEL = ABLATION_LABELS[ABLATION_MODE]
ENABLE_SECTION_BY_SECTION_GENERATION = ABLATION_MODE != "section_generation"

N1N_API_KEY = os.environ.get("MDR_API_KEY", "")
N1N_BASE_URL = os.environ.get("MDR_BASE_URL", "https://api.openai.com/v1")
FIRECRAWL_API_KEYS = _get_api_key_list_env(
    "FIRECRAWL_API_KEYS",
    "FIRECRAWL_API_KEY",
    [],
)
FIRECRAWL_API_KEY = FIRECRAWL_API_KEYS[0] if FIRECRAWL_API_KEYS else ""

DEFAULT_TEXT_MODEL = os.environ.get("MDR_TEXT_MODEL", "gpt-5.2")
DEFAULT_VISION_MODEL = os.environ.get("MDR_VISION_MODEL", "gpt-5.4-mini")

RESEARCH_LLM_MODEL = os.environ.get("MDR_RESEARCH_LLM_MODEL", DEFAULT_TEXT_MODEL)
PLANNING_LLM_MODEL = os.environ.get("MDR_PLANNING_LLM_MODEL", DEFAULT_TEXT_MODEL)
EXEMPLAR_MLLM_MODEL = os.environ.get("MDR_EXEMPLAR_MLLM_MODEL", DEFAULT_VISION_MODEL)
REPORT_LLM_MODEL = os.environ.get("MDR_REPORT_LLM_MODEL", DEFAULT_VISION_MODEL)
GLOBAL_REPORT_LLM_MODEL = os.environ.get("MDR_GLOBAL_REPORT_LLM_MODEL", RESEARCH_LLM_MODEL)
CHART_ACTOR_MODEL = os.environ.get("MDR_CHART_ACTOR_MODEL", DEFAULT_VISION_MODEL)
CHART_CRITIC_MLLM_MODEL = os.environ.get("MDR_CHART_CRITIC_MLLM_MODEL", DEFAULT_VISION_MODEL)
VISION_METADATA_MLLM_MODEL = os.environ.get("MDR_VISION_METADATA_MLLM_MODEL", DEFAULT_VISION_MODEL)
FINAL_REPORT_POLISH_MODEL = os.environ.get("MDR_FINAL_REPORT_POLISH_MODEL", REPORT_LLM_MODEL)

# Research hyperparameters
N_R = int(os.environ.get("MDR_N_R", "5"))
N_K = int(os.environ.get("MDR_N_K", "10"))
N_P = int(os.environ.get("MDR_N_P", "3"))
N_L = int(os.environ.get("MDR_N_L", "3"))
# switched to hyperparameters
# N_R = int(os.environ.get("MDR_N_R", "2"))
# N_K = int(os.environ.get("MDR_N_K", "2"))
# N_P = int(os.environ.get("MDR_N_P", "3"))
# N_L = int(os.environ.get("MDR_N_L", "3"))

MAX_RETRIES = 3
ENABLE_REPORT_PREPROCESS = _get_bool_env("MDR_ENABLE_REPORT_PREPROCESS", True)
ENABLE_FINAL_REPORT_POLISH = _get_bool_env("MDR_ENABLE_FINAL_REPORT_POLISH", True)
FINAL_REPORT_POLISH_MAX_TOKENS = int(os.environ.get("MDR_FINAL_REPORT_POLISH_MAX_TOKENS", "6000"))
MAX_GENERATED_CHARTS = _get_optional_int_env("MDR_MAX_GENERATED_CHARTS", None)


IMAGE_PIPELINE_CONFIG = {
    "enable_image_metadata": _get_bool_env("MDR_ENABLE_IMAGE_METADATA", True),
    "enable_strict_image_prompt": _get_bool_env("MDR_ENABLE_STRICT_IMAGE_PROMPT", True),
    "enable_image_dedup": _get_bool_env("MDR_ENABLE_IMAGE_DEDUP", True),
    "enable_contextual_image_pipeline": _get_bool_env("MDR_ENABLE_CONTEXTUAL_IMAGE_PIPELINE", True),
    "image_selection_mode": os.environ.get("MDR_IMAGE_SELECTION_MODE", "semantic").strip().lower(),
    "enable_global_image_selection": _get_bool_env("MDR_ENABLE_GLOBAL_IMAGE_SELECTION", False),
    "enable_image_reranking": _get_bool_env("MDR_ENABLE_IMAGE_RERANKING", True),
    "section_image_selection_chain": os.environ.get("MDR_SECTION_IMAGE_SELECTION_CHAIN", "rerank").strip().lower(),
    "enable_image_grounding_check": False,
    "context_screening_batch_size": int(os.environ.get("MDR_CONTEXT_SCREENING_BATCH_SIZE", "12")),
    "max_context_screened_images": int(os.environ.get("MDR_MAX_CONTEXT_SCREENED_IMAGES", "100")),
    "max_topic_shortlist_images": int(os.environ.get("MDR_MAX_TOPIC_SHORTLIST_IMAGES", "50")),
    "max_ocr_images": int(os.environ.get("MDR_MAX_OCR_IMAGES", "20")),
    "max_final_selected_images": int(os.environ.get("MDR_MAX_FINAL_SELECTED_IMAGES", "15")),
    "max_global_selected_images": _get_optional_int_env("MDR_MAX_GLOBAL_SELECTED_IMAGES", None),
    "max_legacy_selected_images_per_section": int(os.environ.get("MDR_MAX_LEGACY_SELECTED_IMAGES_PER_SECTION", "1")),
    "max_weak_metadata_selected_images_per_section": int(os.environ.get("MDR_MAX_WEAK_METADATA_SELECTED_IMAGES_PER_SECTION", "1")),
}

if ABLATION_MODE == "image_enrichment":
    IMAGE_PIPELINE_CONFIG.update(
        {
            "enable_image_metadata": False,
            "enable_contextual_image_pipeline": False,
            "enable_image_reranking": False,
            "enable_image_grounding_check": False,
        }
    )
elif ABLATION_MODE == "weak_metadata":
    IMAGE_PIPELINE_CONFIG.update(
        {
            "enable_image_metadata": True,
            "enable_contextual_image_pipeline": False,
            "enable_image_reranking": False,
            "enable_image_grounding_check": False,
            "image_selection_mode": "weak_metadata",
            "section_image_selection_chain": "weak_metadata",
        }
    )

PLANNING_MODE = os.environ.get("MDR_PLANNING_MODE", "text_only")

# Adaptive outline during research
# Enabled by default; can still be forced on via MDR_ADAPTIVE_OUTLINE=True or --ablation adaptive_outline.
ADAPTIVE_OUTLINE = _get_bool_env("MDR_ADAPTIVE_OUTLINE", True) or ABLATION_MODE == "adaptive_outline"

# Early-stop: evaluate outline maturity each round, stop research if score >= threshold
# Activates via --early-stop CLI flag OR MDR_ADAPTIVE_EARLY_STOP=True (only effective when ADAPTIVE_OUTLINE=True)
ADAPTIVE_EARLY_STOP = (
    _get_bool_env("MDR_ADAPTIVE_EARLY_STOP", False)
    or "--early-stop" in sys.argv
) and ADAPTIVE_OUTLINE
ADAPTIVE_EARLY_STOP_THRESHOLD = float(os.environ.get("MDR_ADAPTIVE_EARLY_STOP_THRESHOLD", "3.5"))
ADAPTIVE_EARLY_STOP_MIN_ROUNDS = int(os.environ.get("MDR_ADAPTIVE_EARLY_STOP_MIN_ROUNDS", "1"))
