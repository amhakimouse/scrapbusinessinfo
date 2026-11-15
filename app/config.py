"""Central place for every setting the project reads from .env.

Nothing else in the codebase should call os.getenv directly — import
from here so there's one source of truth.
"""
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
def _resolve_path(env_var: str, default: str) -> Path:
    raw = os.getenv(env_var, default)
    p = Path(raw)
    return p if p.is_absolute() else ROOT_DIR / p


DEFAULT_FETCH_MODE = os.getenv("DEFAULT_FETCH_MODE", "fast")  # "fast" | "stealthy"
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "2.0"))
LEADS_FILE = _resolve_path("LEADS_FILE", "data/leads.json")
SEEDS_FILE = _resolve_path("SEEDS_FILE", "data/seeds.txt")
SEARCH_RESULTS_PER_KEYWORD = int(os.getenv("SEARCH_RESULTS_PER_KEYWORD", "30"))
# Which DuckDuckGo result page to start from (3 = skip pages 1 & 2, avoiding big-brand results)
SEARCH_START_PAGE = int(os.getenv("SEARCH_START_PAGE", "3"))

# A realistic desktop User-Agent used for the "fast" fetcher's headers
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
