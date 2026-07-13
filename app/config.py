"""Static configuration for ClinicalxCRAFT v2.

Two things differ from v1: the data plane is a local file (no CRAFT/OAuth), and the only
credential needed is the LLM key. Everything is read-only.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "kirc.json"
WEB_DIR = BASE_DIR / "web"

# Load a local .env if python-dotenv is installed (optional convenience; env vars set in the
# shell still win). Keeps NEBIUS_API_KEY out of the code and out of git (see .gitignore).
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# --- LLM (Nebius Token Factory — OpenAI-compatible endpoint, auth via NEBIUS_API_KEY) ---
NEBIUS_BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
# NVIDIA Nemotron 3 Super — tuned for tool-calling / long-horizon agentic work. Note: it
# emits reasoning tokens that count against max_tokens before the visible answer, so keep
# max_tokens generous (see agent.MAX_TOKENS).
NEBIUS_MODEL = os.environ.get("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b")

# --- Cohort ---
COHORT_LABEL = "KIRC (kidney renal clear cell carcinoma)"
COHORT_N = 518

# Row cap returned to the model from a single SQL call (keeps tool payloads small).
MAX_SQL_ROWS = 200
