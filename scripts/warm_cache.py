"""Populate fixtures/llm_cache/ from real handwritten images.

The demo runs entirely offline (DEMO_MODE=offline) by serving cached model
responses -- see app/llm.py. Those responses have to come from somewhere: this
script walks fixtures/images/ for real photographs, sends each one through
app.transcriber.transcribe with a live API key, and lets app/llm.py's normal
content-addressed cache write the response to fixtures/llm_cache/ as a side
effect. Nothing here talks to the cache directly.

This does NOT call the marking or feedback stages -- those prompts depend on
the *confirmed* transcription (which a lecturer edits in the UI), so their
cache entries cannot be pre-warmed from a raw image the way transcription's
can. scripts/seed_demo_cache.py covers that half for the flagship q2 script.

Requires DEMO_MODE=live and a real ANTHROPIC_API_KEY. Deliberately exits early
and cleanly if either is missing, rather than letting app.llm raise partway
through a run.

Run:  .venv/Scripts/python.exe scripts/warm_cache.py
"""

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ANTHROPIC_API_KEY, DEMO_MODE, IMAGES_DIR, LLM_CACHE_DIR  # noqa: E402
from app import uploads  # noqa: E402
from app.transcriber import transcribe, transcribe_model_solution  # noqa: E402

# Only a filename filter. The media type sent to the model is always
# "image/png", because every server path normalises through
# uploads.render_page() first - see the comment in main() for why that matters.
_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})


def _find_images(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
    )


def _count_cache_entries() -> int:
    if not LLM_CACHE_DIR.exists():
        return 0
    return len(list(LLM_CACHE_DIR.glob("*.json")))


def main() -> int:
    if not ANTHROPIC_API_KEY:
        print(
            "No ANTHROPIC_API_KEY set (checked the environment and .env). "
            "warm_cache.py needs a real key to call the vision model, so "
            "there is nothing it can do -- exiting without touching the cache.\n"
            "Set ANTHROPIC_API_KEY (see .env.example) and re-run, or use "
            "scripts/seed_demo_cache.py for the API-key-free offline demo path."
        )
        return 1

    if DEMO_MODE != "live":
        print(
            f"DEMO_MODE is {DEMO_MODE!r}, not 'live'. app.llm will not attempt a "
            "network call in this mode (see app/llm.py's OfflineCacheMiss), so "
            "warming the cache from real images is not possible right now.\n"
            "Re-run with DEMO_MODE=live."
        )
        return 1

    images = _find_images(IMAGES_DIR)
    before = _count_cache_entries()

    if not images:
        print(
            f"No images found in {IMAGES_DIR} (looked for *.jpg, *.jpeg, *.png). "
            "Nothing to warm."
        )
        print(f"Cache entries in {LLM_CACHE_DIR}: {before} (unchanged).")
        return 0

    print(f"Found {len(images)} image(s) in {IMAGES_DIR}:")

    successes = 0
    failures = 0
    for path in images:
        print(f"  {path.name} ... ", end="", flush=True)
        try:
            # Warm exactly what the API will later look up. llm.cache_key hashes
            # the image bytes, and every server path base64s
            # uploads.render_page() output with media_type="image/png" - not the
            # raw file. Sending the raw bytes here (as this script used to) put
            # the warmed entries in a disjoint key space from the ones the
            # server asks for, so the offline photo demo could never hit the
            # cache no matter how much was warmed.
            png = uploads.render_page(path.read_bytes())
            image_b64 = base64.b64encode(png).decode()

            # Both framings, because both are real server paths: a student's
            # scan and a lecturer's photographed model solution.
            student = transcribe(image_b64=image_b64, media_type="image/png")
            transcribe_model_solution(image_b64=image_b64, media_type="image/png")
        except Exception as error:  # noqa: BLE001 - report and keep going
            print(f"FAILED ({type(error).__name__}: {error})")
            failures += 1
            continue
        print(f"ok, {len(student.steps)} step(s) transcribed (both framings)")
        successes += 1

    after = _count_cache_entries()
    print()
    print("Summary:")
    print(f"  images processed:      {len(images)}")
    print(f"  transcriptions ok:     {successes}")
    print(f"  transcriptions failed: {failures}")
    print(f"  cache entries before:  {before}")
    print(f"  cache entries after:   {after}")
    print(f"  cache entries written: {after - before}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
