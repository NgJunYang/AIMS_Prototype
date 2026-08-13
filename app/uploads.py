"""Turn an arbitrary upload into safe, normalized PNG bytes.

No disk I/O, no network, no LLM calls. Every upload — image or PDF — leaves
this module as validated PNG bytes, so the caller never has to trust a
client-supplied Content-Type or handle two different image formats downstream.
"""

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

import fitz  # PyMuPDF
from PIL import Image, ImageOps

SourceType = Literal["image", "pdf"]

# Anthropic's documented sweet spot for vision input: legible for handwritten
# maths, and quality plateaus above this while both request size and token
# cost keep climbing. See the matching comment in render_page().
_MAX_DIMENSION = 1568


class UnsupportedUpload(ValueError):
    """Raised when bytes are neither a decodable image nor a PDF."""


class PageOutOfRange(ValueError):
    """Raised when the requested page is outside 1..page_count for this upload."""


@dataclass(frozen=True)
class UploadInfo:
    source_type: SourceType
    page_count: int


def _is_pdf(raw: bytes) -> bool:
    return raw[:5] == b"%PDF-"


def inspect(raw: bytes) -> UploadInfo:
    """Report what an upload is, without rasterizing anything expensive."""
    if _is_pdf(raw):
        try:
            with fitz.open(stream=raw, filetype="pdf") as document:
                page_count = document.page_count
        except Exception as exc:
            raise UnsupportedUpload("Could not open this file as a PDF.") from exc
        if page_count < 1:
            raise UnsupportedUpload("This PDF has no pages.")
        return UploadInfo(source_type="pdf", page_count=page_count)

    try:
        with Image.open(BytesIO(raw)) as image:
            image.verify()
    except Exception as exc:
        # Pillow's decoders raise format-specific exceptions on corruption -
        # e.g. a bad chunk CRC in a PNG surfaces as a bare SyntaxError, not
        # UnidentifiedImageError/OSError. Catching broadly here is the only
        # way to guarantee a malformed-but-plausible-looking upload degrades
        # to a clean error instead of an unhandled 500.
        raise UnsupportedUpload(
            "Could not read this file as an image or a PDF."
        ) from exc
    return UploadInfo(source_type="image", page_count=1)


def render_page(raw: bytes, page: int = 1, dpi: int = 200) -> bytes:
    """Render the requested page as normalized PNG bytes.

    Images are corrected for EXIF orientation before being re-encoded — a
    photo taken in portrait often carries a rotation tag rather than being
    physically rotated, and an uncorrected image is a wrong page shown to
    the model, not just a cosmetic issue.

    Always opens a fresh handle on the bytes rather than reusing one that
    `inspect()` already called `.verify()` on: Pillow raises `AssertionError`
    on further use of a handle after `.verify()`, so the two must stay
    independent even though they're reading the same bytes.
    """
    info = inspect(raw)
    if page < 1 or page > info.page_count:
        raise PageOutOfRange(
            f"Page {page} is outside the valid range 1..{info.page_count}."
        )

    if info.source_type == "pdf":
        with fitz.open(stream=raw, filetype="pdf") as document:
            pixmap = document.load_page(page - 1).get_pixmap(
                matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False
            )
            source_bytes = pixmap.tobytes("png")
    else:
        source_bytes = raw

    try:
        with Image.open(BytesIO(source_bytes)) as image:
            # exif_transpose can return None when no rotation is needed on
            # some Pillow versions; fall back to the original image rather
            # than crashing on .convert(None).
            corrected = ImageOps.exif_transpose(image) or image
            corrected = corrected.convert("RGB")
            # A phone photo can be 3000-4000px on the long edge - Claude's
            # vision input caps at 10 MB, and cost scales with pixel count
            # regardless. 1568px is Anthropic's own documented sweet spot:
            # comfortably legible for handwriting, quality plateaus above
            # it. thumbnail() only ever shrinks, never enlarges, so smaller
            # images (test fixtures, most PDF pages) pass through untouched.
            corrected.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.LANCZOS)
            buffer = BytesIO()
            corrected.save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception as exc:
        # See the matching comment in inspect(): Pillow's exceptions here are
        # not limited to UnidentifiedImageError/OSError.
        raise UnsupportedUpload("Could not read this file as an image.") from exc
