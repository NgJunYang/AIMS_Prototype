from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SEEDS_DIR = BASE_DIR / "app" / "seeds"
STATIC_DIR = BASE_DIR / "static"
FIXTURES_DIR = BASE_DIR / "fixtures"
LLM_CACHE_DIR = FIXTURES_DIR / "llm_cache"
IMAGES_DIR = FIXTURES_DIR / "images"
SUBMISSIONS_DIR = BASE_DIR / "data" / "submissions"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# "live"    -> call the API, write every response to the cache
# "offline" -> serve only from the cache, never touch the network
DEMO_MODE = os.getenv("DEMO_MODE", "live")

VISION_MODEL = "claude-sonnet-5"
MARKING_MODEL = "claude-opus-5"

for directory in (LLM_CACHE_DIR, IMAGES_DIR, SUBMISSIONS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
