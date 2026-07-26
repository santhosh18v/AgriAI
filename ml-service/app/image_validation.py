"""Upload / image validation for the disease-prediction endpoint (M7).

Everything here operates on in-memory bytes only -- no uploaded file is
ever written to disk. MIME type and filename extension are treated only as
untrusted hints; the actual image bytes are what gets decoded, verified,
and cross-checked. All failures raise ImageValidationError with a stable
`error_code` (mapped to an HTTP status in routes/predict.py) and a
`message` that is safe to return to the client verbatim -- never a Pillow
exception string, a path, or other internal detail.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import BinaryIO, Set

from PIL import Image, ImageOps

MAX_DISPLAY_FILENAME_LENGTH = 100

# Declared Content-Type must correspond to Pillow's own detected format --
# this is the "don't trust MIME/extension alone" cross-check.
_MIME_TO_PILLOW_FORMATS = {
    "image/jpeg": {"JPEG"},
    "image/png": {"PNG"},
    "image/webp": {"WEBP"},
}


class ImageValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass(frozen=True)
class ValidatedImage:
    image: Image.Image  # decoded, EXIF-corrected, RGB
    filename: str  # sanitized, display-only -- never used as a filesystem path
    content_type: str
    byte_size: int
    original_width: int
    original_height: int


def sanitize_filename(filename: str | None) -> str:
    """Display-only sanitization: strips any path component (a client could
    send one even though it's never used as one here), strips control
    characters, and caps length. Never used to construct a filesystem path."""
    if not filename:
        return "upload"
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = name.strip() or "upload"
    return name[:MAX_DISPLAY_FILENAME_LENGTH]


def _extension_of(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def read_upload_bounded(file_obj: BinaryIO, max_bytes: int) -> bytes:
    """Reads `file_obj` in chunks, aborting as soon as `max_bytes` is
    exceeded, so an oversized (or unbounded/streamed) upload cannot force
    the whole body into memory before the size limit is enforced."""
    chunks = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ImageValidationError("file_too_large", "the uploaded file exceeds the maximum allowed size")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    raw_bytes: bytes,
    max_upload_bytes: int,
    allowed_extensions: Set[str],
    allowed_mime_types: Set[str],
    max_decode_pixels: int,
) -> ValidatedImage:
    safe_filename = sanitize_filename(filename)

    if not filename or not filename.strip():
        raise ImageValidationError("invalid_file", "no filename was provided")

    if not raw_bytes:
        raise ImageValidationError("invalid_file", "the uploaded file is empty")

    if len(raw_bytes) > max_upload_bytes:
        raise ImageValidationError("file_too_large", "the uploaded file exceeds the maximum allowed size")

    extension = _extension_of(safe_filename)
    if extension not in allowed_extensions:
        raise ImageValidationError("unsupported_media_type", "the file extension is not supported")

    if content_type not in allowed_mime_types:
        raise ImageValidationError("unsupported_media_type", "the declared content type is not supported")

    # Cheap structural check first (does not decode pixel data).
    try:
        with Image.open(io.BytesIO(raw_bytes)) as probe:
            probe.verify()
    except Exception as e:
        raise ImageValidationError("malformed_image", "the file could not be decoded as a valid image") from e

    # verify() leaves the file object unusable -- reopen fresh for the real
    # decode. Pillow's own MAX_IMAGE_PIXELS guard also applies during load().
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except Image.DecompressionBombError as e:
        raise ImageValidationError("image_too_large", "the image dimensions exceed the maximum allowed size") from e
    except Exception as e:
        raise ImageValidationError("malformed_image", "the file could not be decoded as a valid image") from e

    actual_format = image.format
    if actual_format not in _MIME_TO_PILLOW_FORMATS.get(content_type, set()):
        raise ImageValidationError(
            "mime_mismatch", "the declared content type does not match the actual image content"
        )

    if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
        raise ImageValidationError("animated_image_not_supported", "animated or multi-frame images are not supported")

    width, height = image.size
    if width <= 0 or height <= 0:
        raise ImageValidationError("malformed_image", "the image has invalid dimensions")
    if width * height > max_decode_pixels:
        raise ImageValidationError("image_too_large", "the image dimensions exceed the maximum allowed size")

    # EXIF orientation must be applied before any further processing (and
    # before the RGB conversion, since exif_transpose reads Exif tags that
    # a mode conversion could otherwise interfere with).
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")

    return ValidatedImage(
        image=image,
        filename=safe_filename,
        content_type=content_type,
        byte_size=len(raw_bytes),
        original_width=width,
        original_height=height,
    )
