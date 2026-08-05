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
# Lecturer-authored questions, layered over the read-only seeded bank so the
# seed file stays pristine and a fresh clone still starts with six questions.
QUESTIONS_FILE = BASE_DIR / "data" / "questions.json"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# "live"    -> call the API, write every response to the cache
# "offline" -> serve only from the cache, never touch the network
DEMO_MODE = os.getenv("DEMO_MODE", "live")

# Comma-separated list of origins allowed to call this API cross-origin, e.g.
# "https://t-zinlin.github.io" when the frontend is deployed separately on
# GitHub Pages. Defaults to "*" (any origin) because this demo carries no
# auth/cookies to protect - see the CORSMiddleware setup in main.py.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

VISION_MODEL = "claude-sonnet-5"
MARKING_MODEL = "claude-opus-5"

for directory in (LLM_CACHE_DIR, IMAGES_DIR, SUBMISSIONS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
