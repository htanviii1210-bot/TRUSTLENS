"""
TrustLens — Preprocessing Module
=================================
Responsibilities (spec §3):
  - Validate uploaded bytes (size, magic bytes, decode, dimensions).
  - Decode with Pillow safely (verify + reopen).
  - Convert to RGB.
  - Downscale to ANALYSIS_MAX_DIMENSION if needed (preserving aspect).
  - Produce a NumPy BGR array (OpenCV convention) for analysis.

Contract
--------
The public function `validate_and_prepare(image_bytes)` returns a dict:

    {
        "pil_image":   PIL.Image.Image,   # RGB, possibly resized (analysis copy)
        "original_size":  (width, height),   # as uploaded
        "analysis_size":  (width, height),   # after any resize
        "was_resized":    bool,
        "format":         "JPEG" | "PNG" | ...,
        "mode_original":  "RGB" | "RGBA" | "L" | ...,
        "cv_image":       np.ndarray (BGR, HxWx3, uint8),
    }

Raises PreprocessingError with a human-readable `.message` on any failure.
This module NEVER mutates the original bytes or opens network resources.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

import config


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class PreprocessingError(Exception):
    """Raised when an uploaded image cannot be safely prepared for analysis.

    The `.message` attribute is safe to surface to end users (no stack traces,
    no file paths, no library-internal jargon).
    """

    def __init__(self, message: str, code: str = "invalid_image"):
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _check_size(image_bytes: bytes) -> None:
    if not image_bytes:
        raise PreprocessingError(
            "No image data received. Please upload a file.",
            code="empty_upload",
        )
    if len(image_bytes) > config.MAX_FILE_SIZE_BYTES:
        limit_mb = config.MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise PreprocessingError(
            f"File is too large. Maximum allowed size is {limit_mb} MB.",
            code="file_too_large",
        )


def _open_and_verify(image_bytes: bytes) -> Image.Image:
    """Open, verify, then *reopen* the stream.

    Pillow's `.verify()` consumes the file object and can leave the image in
    an unusable state, so we always reopen from the original bytes after a
    successful verify. This is the canonical safe pattern recommended by
    Pillow's docs.
    """
    try:
        probe = Image.open(io.BytesIO(image_bytes))
        probe.verify()
    except UnidentifiedImageError:
        raise PreprocessingError(
            "The uploaded file is not a valid image. "
            "Please upload a JPG or PNG file.",
            code="unrecognised_format",
        )
    except Exception as exc:  # noqa: BLE001 — surface *any* verify failure
        logger.warning("verify() failed: %s", exc)
        raise PreprocessingError(
            "The file appears to be corrupted or unreadable.",
            code="corrupt_file",
        )

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()  # force full decode — catches truncated data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Full decode failed: %s", exc)
        raise PreprocessingError(
            "The image is corrupted or incomplete.",
            code="decode_failed",
        )

    return img


def _validate_format(img: Image.Image) -> None:
    fmt = (img.format or "").upper()
    if fmt not in config.ALLOWED_PIL_FORMATS:
        allowed = ", ".join(sorted(config.ALLOWED_PIL_FORMATS))
        raise PreprocessingError(
            f"Unsupported image format '{fmt or 'unknown'}'. "
            f"Allowed formats: {allowed}.",
            code="unsupported_format",
        )


def _validate_dimensions(img: Image.Image) -> None:
    w, h = img.size
    if w < config.MIN_IMAGE_WIDTH or h < config.MIN_IMAGE_HEIGHT:
        raise PreprocessingError(
            f"Image is too small ({w}×{h} px). "
            f"Minimum {config.MIN_IMAGE_WIDTH}×{config.MIN_IMAGE_HEIGHT} required.",
            code="image_too_small",
        )


def _normalise_mode(img: Image.Image) -> Image.Image:
    """Convert to RGB while handling transparency sanely.

    - RGBA / LA / P-with-alpha → flatten over white so no data is lost.
    - L (grayscale) → replicate to RGB (keeps 3-channel analysis consistent).
    - CMYK / YCbCr / etc. → direct RGB conversion.
    - Already RGB → returned as-is.
    """
    mode = img.mode

    if mode == "RGB":
        return img

    if mode in ("RGBA", "LA") or (mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")

    # L, CMYK, YCbCr, P (no alpha), I, F, ...
    try:
        return img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mode conversion failed (%s): %s", mode, exc)
        raise PreprocessingError(
            "This image's colour mode could not be processed.",
            code="colour_mode_unsupported",
        )


def _resize_if_needed(img: Image.Image) -> Tuple[Image.Image, bool]:
    """Downscale so the longest side ≤ ANALYSIS_MAX_DIMENSION.

    Preserves aspect ratio. Uses LANCZOS for quality. Never upscales —
    a small image is analysed at its native size.
    """
    w, h = img.size
    longest = max(w, h)
    if longest <= config.ANALYSIS_MAX_DIMENSION:
        return img, False

    scale = config.ANALYSIS_MAX_DIMENSION / float(longest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    return resized, True


def _to_cv_bgr(pil_rgb: Image.Image) -> np.ndarray:
    """Convert PIL RGB → OpenCV BGR uint8 array.

    `np.asarray` on a PIL image returns a read-only view in some Pillow
    versions; we `.copy()` to guarantee a writable buffer before passing to
    cv2 operations that may modify in place.
    """
    arr = np.asarray(pil_rgb, dtype=np.uint8)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return bgr


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_and_prepare(image_bytes: bytes) -> Dict[str, Any]:
    """Validate and prepare image bytes for TrustLens analysis.

    See module docstring for the returned dict shape.
    """
    _check_size(image_bytes)

    pil = _open_and_verify(image_bytes)
    _validate_format(pil)
    _validate_dimensions(pil)

    original_size = pil.size
    mode_original = pil.mode

    pil = _normalise_mode(pil)

    # Honour EXIF orientation so analysis sees the image as the user sees it.
    # (ImageOps.exif_transpose is a no-op if there's no orientation tag.)
    try:
        pil = ImageOps.exif_transpose(pil)
    except Exception as exc:  # noqa: BLE001
        logger.warning("exif_transpose failed (continuing): %s", exc)

    pil, was_resized = _resize_if_needed(pil)

    if pil.mode != "RGB":
        pil = pil.convert("RGB")

    cv_image = _to_cv_bgr(pil)

    return {
        "pil_image": pil,
        "original_size": original_size,
        "analysis_size": pil.size,
        "was_resized": was_resized,
        "format": (pil.format or "UNKNOWN"),
        "mode_original": mode_original,
        "cv_image": cv_image,
    }