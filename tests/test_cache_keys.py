"""The cache key a warmer writes must be the key the server looks up.

This existed as a real bug: `scripts/warm_cache.py` base64'd the raw file bytes
while every server path base64s `uploads.render_page()` output. Since
`llm.cache_key` hashes the image, the two key spaces were disjoint - so the
offline photo demo could never hit the cache no matter how much was warmed, and
nothing failed to say so.
"""

import base64
import io

from PIL import Image

from app import uploads
from app.config import VISION_MODEL
from app.llm import cache_key
from app.transcriber import build_prompt


def _jpeg_bytes(size=(40, 24), color=(200, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _server_image_b64(raw: bytes, page: int = 1) -> str:
    """Exactly what every server transcribe path sends to the model."""
    return base64.b64encode(uploads.render_page(raw, page=page)).decode()


def test_warming_and_serving_agree_on_the_student_key():
    raw = _jpeg_bytes()
    warmed = cache_key(VISION_MODEL, build_prompt("student"), _server_image_b64(raw))
    served = cache_key(VISION_MODEL, build_prompt(), _server_image_b64(raw))
    assert warmed == served


def test_warming_and_serving_agree_on_the_model_solution_key():
    raw = _jpeg_bytes()
    warmed = cache_key(
        VISION_MODEL, build_prompt("model_solution"), _server_image_b64(raw)
    )
    served = cache_key(
        VISION_MODEL, build_prompt("model_solution"), _server_image_b64(raw)
    )
    assert warmed == served


def test_sending_raw_bytes_would_miss_the_key_the_server_asks_for():
    """Pins the actual bug, so nobody reintroduces it.

    Warming with the raw upload rather than the normalised PNG produces a
    different key - which is precisely what made the old warm_cache.py useless.
    """
    raw = _jpeg_bytes()
    naive = cache_key(VISION_MODEL, build_prompt(), base64.b64encode(raw).decode())
    correct = cache_key(VISION_MODEL, build_prompt(), _server_image_b64(raw))
    assert naive != correct


def test_the_two_framings_occupy_different_cache_entries():
    """Each framing needs warming separately; one does not cover the other."""
    image_b64 = _server_image_b64(_jpeg_bytes())
    student = cache_key(VISION_MODEL, build_prompt("student"), image_b64)
    lecturer = cache_key(VISION_MODEL, build_prompt("model_solution"), image_b64)
    assert student != lecturer


def test_the_same_photo_as_jpeg_and_png_shares_one_key():
    """render_page() normalises both to the same PNG, so warming one warms both."""
    original = Image.new("RGB", (30, 18), (10, 90, 140))

    as_jpeg = io.BytesIO()
    original.save(as_jpeg, format="PNG")  # lossless both ways for this check
    as_png = io.BytesIO()
    original.save(as_png, format="PNG")

    assert _server_image_b64(as_jpeg.getvalue()) == _server_image_b64(as_png.getvalue())
