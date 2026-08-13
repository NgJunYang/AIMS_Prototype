import io

import pytest
from PIL import Image

from app.uploads import PageOutOfRange, UnsupportedUpload, inspect, render_page


def _png_bytes(size=(4, 4), color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes(page_count: int = 1) -> bytes:
    import fitz

    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    return doc.tobytes()


def test_garbage_bytes_are_rejected():
    with pytest.raises(UnsupportedUpload):
        inspect(b"this is not an image or a pdf")


def test_empty_bytes_are_rejected():
    with pytest.raises(UnsupportedUpload):
        inspect(b"")


def test_a_valid_png_is_recognised_as_a_single_page_image():
    info = inspect(_png_bytes())
    assert info.source_type == "image"
    assert info.page_count == 1


def test_a_valid_pdf_reports_its_page_count():
    info = inspect(_pdf_bytes(page_count=3))
    assert info.source_type == "pdf"
    assert info.page_count == 3


def test_requesting_a_page_beyond_a_single_image_is_out_of_range():
    with pytest.raises(PageOutOfRange):
        render_page(_png_bytes(), page=2)


def test_requesting_a_page_beyond_a_pdfs_page_count_is_out_of_range():
    with pytest.raises(PageOutOfRange):
        render_page(_pdf_bytes(page_count=2), page=5)


def test_render_page_of_a_plain_image_round_trips_as_png():
    raw = _png_bytes(size=(10, 6))
    rendered = render_page(raw)
    out = Image.open(io.BytesIO(rendered))
    assert out.format == "PNG"
    assert out.size == (10, 6)


def test_render_page_downscales_a_phone_sized_photo():
    """A modern phone photo (e.g. 4000x3000, ~12MP) must not pass through at
    full resolution: Claude's vision input hard-caps at 10 MB, and cost
    scales with pixel count regardless of whether the cap is hit."""
    raw = _png_bytes(size=(4000, 3000), color=(120, 60, 200))
    rendered = render_page(raw)
    out = Image.open(io.BytesIO(rendered))
    assert out.width <= 1568 and out.height <= 1568
    # Aspect ratio preserved (4000x3000 is 4:3).
    assert out.width / out.height == pytest.approx(4000 / 3000, rel=0.01)
    assert len(rendered) < 10 * 1024 * 1024


def test_render_page_of_a_pdf_page_produces_a_reasonably_sized_image():
    raw = _pdf_bytes(page_count=1)
    rendered = render_page(raw, page=1)
    out = Image.open(io.BytesIO(rendered))
    assert out.format == "PNG"
    assert out.width > 100 and out.height > 100


def test_a_structurally_plausible_but_corrupt_png_is_rejected_not_crashed():
    """A bad chunk checksum makes Pillow raise SyntaxError, not
    UnidentifiedImageError/OSError - this pins that inspect() still degrades
    to UnsupportedUpload rather than letting an unhandled exception through.
    """
    raw = bytearray(_png_bytes())
    idat = raw.find(b"IDAT")
    raw[idat + 5] ^= 0xFF  # flip a bit inside the IDAT chunk's data
    with pytest.raises(UnsupportedUpload):
        inspect(bytes(raw))


def test_exif_rotation_is_corrected():
    """A 90-degree EXIF orientation tag must actually swap the reported
    dimensions once rendered — not just be silently ignored."""
    img = Image.new("RGB", (40, 20), color=(0, 128, 255))  # landscape, asymmetric
    buf = io.BytesIO()
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW for correct display
    img.save(buf, format="JPEG", exif=exif)

    rendered = render_page(buf.getvalue())
    out = Image.open(io.BytesIO(rendered))
    assert out.size == (20, 40)
