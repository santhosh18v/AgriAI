"""Tests for app/image_validation.py (Milestone M7).

All test images are tiny and generated in-memory with Pillow -- no
PlantVillage source images are used.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.image_validation import ImageValidationError, read_upload_bounded, sanitize_filename, validate_upload

DEFAULT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_PIXELS = 24_000_000


def _validate(**overrides):
    kwargs = dict(
        filename="leaf.jpg",
        content_type="image/jpeg",
        raw_bytes=b"",
        max_upload_bytes=DEFAULT_MAX_BYTES,
        allowed_extensions=DEFAULT_EXTENSIONS,
        allowed_mime_types=DEFAULT_MIME_TYPES,
        max_decode_pixels=DEFAULT_MAX_PIXELS,
    )
    kwargs.update(overrides)
    return validate_upload(**kwargs)


def _encode(size=(50, 50), color=(100, 150, 200), fmt="JPEG", mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format=fmt)
    return buf.getvalue()


def test_valid_jpeg_accepted():
    result = _validate(raw_bytes=_encode(fmt="JPEG"), filename="leaf.jpg", content_type="image/jpeg")
    assert result.image.mode == "RGB"
    assert result.original_width == 50
    assert result.original_height == 50


def test_valid_png_accepted():
    result = _validate(raw_bytes=_encode(fmt="PNG"), filename="leaf.png", content_type="image/png")
    assert result.image.mode == "RGB"


def test_valid_webp_accepted():
    try:
        data = _encode(fmt="WEBP")
    except Exception:
        pytest.skip("Pillow build does not support WEBP encoding")
    result = _validate(raw_bytes=data, filename="leaf.webp", content_type="image/webp")
    assert result.image.mode == "RGB"


def test_empty_upload_rejected():
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=b"", filename="leaf.jpg", content_type="image/jpeg")
    assert exc.value.error_code == "invalid_file"


def test_missing_filename_rejected():
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=_encode(), filename="", content_type="image/jpeg")
    assert exc.value.error_code == "invalid_file"


def test_unsupported_extension_rejected():
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=_encode(), filename="leaf.gif", content_type="image/jpeg")
    assert exc.value.error_code == "unsupported_media_type"


def test_unsupported_mime_rejected():
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=_encode(), filename="leaf.jpg", content_type="image/gif")
    assert exc.value.error_code == "unsupported_media_type"


def test_mime_content_mismatch_rejected():
    # Real PNG bytes, but declared (and extension-allowed) as JPEG.
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=_encode(fmt="PNG"), filename="leaf.jpg", content_type="image/jpeg")
    assert exc.value.error_code == "mime_mismatch"


def test_corrupt_image_rejected():
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=b"this is not image data at all, just plain bytes " * 10,
                   filename="leaf.jpg", content_type="image/jpeg")
    assert exc.value.error_code == "malformed_image"


def test_truncated_image_rejected():
    full = _encode(size=(200, 200), fmt="JPEG")
    truncated = full[: len(full) // 2]
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=truncated, filename="leaf.jpg", content_type="image/jpeg")
    assert exc.value.error_code == "malformed_image"


def test_oversized_upload_rejected():
    data = _encode(size=(300, 300))
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=data, filename="leaf.jpg", content_type="image/jpeg", max_upload_bytes=100)
    assert exc.value.error_code == "file_too_large"


def test_excessive_dimensions_rejected():
    # Small byte size, but pixel count deliberately exceeds a tiny configured cap.
    data = _encode(size=(200, 200))  # 40,000 pixels
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=data, filename="leaf.jpg", content_type="image/jpeg", max_decode_pixels=1000)
    assert exc.value.error_code == "image_too_large"


def test_animated_webp_rejected():
    buf = io.BytesIO()
    frames = [Image.new("RGB", (30, 30), c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
    try:
        frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:], duration=100, loop=0)
    except Exception:
        pytest.skip("Pillow build does not support animated WEBP encoding")
    with pytest.raises(ImageValidationError) as exc:
        _validate(raw_bytes=buf.getvalue(), filename="leaf.webp", content_type="image/webp")
    assert exc.value.error_code == "animated_image_not_supported"


def test_exif_orientation_is_applied():
    # Orientation 6 = "rotate 90 CW to display correctly" -> exif_transpose
    # swaps width/height for a landscape source.
    img = Image.new("RGB", (60, 40), (10, 20, 30))
    exif = img.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)

    result = _validate(raw_bytes=buf.getvalue(), filename="leaf.jpg", content_type="image/jpeg")
    assert result.original_width == 60
    assert result.original_height == 40
    assert result.image.size == (40, 60)  # swapped after orientation correction


def test_grayscale_converted_to_rgb():
    data = _encode(mode="L", color=128, fmt="PNG")
    result = _validate(raw_bytes=data, filename="leaf.png", content_type="image/png")
    assert result.image.mode == "RGB"


def test_rgba_converted_to_rgb():
    data = _encode(mode="RGBA", color=(10, 20, 30, 128), fmt="PNG")
    result = _validate(raw_bytes=data, filename="leaf.png", content_type="image/png")
    assert result.image.mode == "RGB"


def test_filename_traversal_not_used_as_path():
    result = _validate(raw_bytes=_encode(), filename="../../etc/passwd.jpg", content_type="image/jpeg")
    assert "/" not in result.filename
    assert ".." not in result.filename
    assert result.filename == "passwd.jpg"


def test_long_control_character_filename_safely_represented():
    dirty = "leaf\x00\x07" + ("x" * 300) + ".jpg"
    safe = sanitize_filename(dirty)
    assert "\x00" not in safe
    assert "\x07" not in safe
    assert len(safe) <= 100


def test_read_upload_bounded_stops_early_past_the_limit():
    data = _encode(size=(300, 300))
    assert len(data) > 100
    with pytest.raises(ImageValidationError) as exc:
        read_upload_bounded(io.BytesIO(data), max_bytes=100)
    assert exc.value.error_code == "file_too_large"


def test_read_upload_bounded_returns_full_bytes_within_limit():
    data = _encode()
    result = read_upload_bounded(io.BytesIO(data), max_bytes=DEFAULT_MAX_BYTES)
    assert result == data


def test_no_file_is_written_to_disk(tmp_path, monkeypatch):
    # Sanity check: validate_upload never touches the filesystem for
    # writing. Patch builtins.open's write mode to fail loudly if invoked.
    import builtins

    original_open = builtins.open

    def _guarded_open(file, mode="r", *args, **kwargs):
        if "w" in mode or "a" in mode or "x" in mode:
            raise AssertionError(f"validate_upload attempted to write to disk: {file!r} mode={mode!r}")
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _guarded_open)
    _validate(raw_bytes=_encode(), filename="leaf.jpg", content_type="image/jpeg")
