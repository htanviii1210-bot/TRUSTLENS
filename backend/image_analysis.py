"""
TrustLens — Image Analysis Module
==================================
Implements the 9 feature calculators required by spec §4:

    A. Noise          — Gaussian residual std
    B. Saturation     — HSV S-channel statistics
    C. Contrast       — grayscale std + histogram clipping
    D. Color Balance  — per-channel deviation from RGB mean
    E. Sharpness      — Laplacian variance
    F. Texture        — 8×8 block local variance (rule-based)
    G. Edges          — Canny edge density
    H. JPEG           — 8×8 blockiness  (SUPPORTING ONLY, not scored)
    I. Metadata       — EXIF/PNG info   (SUPPORTING ONLY, not scored)

Plus one conditional feature:
    J. Skin Smoothing — only meaningful when enough skin pixels exist.

Every public `analyze_*` function returns a dict with this envelope:

    {
        "value":       <number>,     # actual measured value
        "risk":        <float>,      # 0..1 (only for SCORED features)
        "level":       <str>,        # short qualitative label
        "explanation": <str>,        # one-sentence human description
        "unit":        <str|None>,   # display unit, may be None
        "scored":      <bool>,       # True → counts toward Trust Score
    }

If a feature cannot be computed on this image, the function returns
{"error": "<reason>", "scored": False}. Callers in scoring.py will
renormalize weights over the remaining features (spec §6).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import cv2
import numpy as np
from PIL import Image

import config


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _envelope(*, value, risk, level, explanation, unit=None, scored=True) -> Dict[str, Any]:
    return {
        "value": round(float(value), 4),
        "risk": float(max(0.0, min(1.0, risk))),
        "level": level,
        "explanation": explanation,
        "unit": unit,
        "scored": scored,
    }


def _error(reason: str) -> Dict[str, Any]:
    return {"error": reason, "scored": False}


# ---------------------------------------------------------------------------
# A. Noise
# ---------------------------------------------------------------------------

def analyze_noise(bgr: np.ndarray) -> Dict[str, Any]:
    """Estimate high-frequency residual after Gaussian blur.

    Filters that smooth skin/background also suppress real sensor noise.
    Risk rises as noise drops below the thresholds in config.
    """
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        residual = gray - blur
        sigma = float(np.std(residual))
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_noise failed: %s", exc)
        return _error("noise analysis failed")

    t = config.NOISE_THRESHOLDS
    if sigma <= t["very_low"]:
        risk, level = 0.85, "very low (heavily smoothed)"
    elif sigma <= t["low"]:
        risk, level = 0.55, "low (possibly smoothed)"
    elif sigma <= t["moderate"]:
        risk, level = 0.20, "moderate (typical for photos)"
    else:
        risk, level = 0.05, "natural sensor grain present"

    return _envelope(
        value=sigma,
        risk=risk,
        level=level,
        unit="σ",
        explanation=(
            f"High-frequency noise σ = {sigma:.2f}. {level}. "
            "Unusually low noise often accompanies smoothing filters."
        ),
    )


# ---------------------------------------------------------------------------
# B. Saturation
# ---------------------------------------------------------------------------

def analyze_saturation(bgr: np.ndarray) -> Dict[str, Any]:
    """HSV S-channel statistics — oversaturation is a classic filter signal."""
    try:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        mean_s = float(sat.mean())
        frac_high = float((sat > 200).mean())
        frac_low = float((sat < 20).mean())
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_saturation failed: %s", exc)
        return _error("saturation analysis failed")

    t = config.SATURATION_THRESHOLDS
    if mean_s >= t["mean_very_high"] or frac_high >= t["frac_high_pixels"]:
        risk, level = 0.80, "very high (oversaturated)"
    elif mean_s >= t["mean_high"] or frac_high >= t["frac_mild_pixels"]:
        risk, level = 0.50, "elevated saturation"
    elif mean_s <= t["mean_very_low"] and frac_low > 0.5:
        risk, level = 0.35, "near-grayscale style"
    else:
        risk, level = 0.10, "natural range"

    return _envelope(
        value=mean_s,
        risk=risk,
        level=level,
        unit="HSV-S",
        explanation=(
            f"Mean HSV saturation = {mean_s:.1f}, "
            f"{frac_high * 100:.1f}% of pixels above S=200. {level}."
        ),
    )


# ---------------------------------------------------------------------------
# C. Contrast
# ---------------------------------------------------------------------------

def analyze_contrast(bgr: np.ndarray) -> Dict[str, Any]:
    """Grayscale std plus histogram clipping (both ends combined)."""
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        std = float(gray.std())
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        total = float(hist.sum()) or 1.0
        clipping = float((hist[:5].sum() + hist[250:].sum()) / total)
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_contrast failed: %s", exc)
        return _error("contrast analysis failed")

    t = config.CONTRAST_THRESHOLDS
    if std >= t["std_high"] or clipping >= t["clipping_high"]:
        risk, level = 0.60, "high (strong contrast / clipping)"
    elif std >= t["std_elevated"] or clipping >= t["clipping_mild"]:
        risk, level = 0.35, "elevated"
    else:
        risk, level = 0.10, "natural"

    return _envelope(
        value=std,
        risk=risk,
        level=level,
        unit="gray σ",
        explanation=(
            f"Grayscale contrast σ = {std:.1f}, "
            f"{clipping * 100:.2f}% pixels clipped to extremes. {level}."
        ),
    )


# ---------------------------------------------------------------------------
# D. Color Balance
# ---------------------------------------------------------------------------

def analyze_color_balance(bgr: np.ndarray) -> Dict[str, Any]:
    """Per-channel mean deviation from overall RGB mean."""
    try:
        b, g, r = bgr[:, :, 0].astype(np.float32), \
                  bgr[:, :, 1].astype(np.float32), \
                  bgr[:, :, 2].astype(np.float32)
        mb, mg, mr = float(b.mean()), float(g.mean()), float(r.mean())
        overall = (mb + mg + mr) / 3.0 + 1e-6
        dev = max(abs(mb - overall), abs(mg - overall), abs(mr - overall)) / overall
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_color_balance failed: %s", exc)
        return _error("color balance analysis failed")

    t = config.COLOR_BALANCE_THRESHOLDS
    if dev >= t["deviation_strong"]:
        risk, level = 0.70, "strong colour cast"
    elif dev >= t["deviation_mild"]:
        risk, level = 0.40, "mild colour cast"
    else:
        risk, level = 0.10, "balanced / natural"

    return _envelope(
        value=dev,
        risk=risk,
        level=level,
        unit="deviation",
        explanation=(
            f"Channel means R={mr:.0f}, G={mg:.0f}, B={mb:.0f} "
            f"(max deviation {dev:.3f}). {level}."
        ),
    )


# ---------------------------------------------------------------------------
# E. Sharpness
# ---------------------------------------------------------------------------

def analyze_sharpness(bgr: np.ndarray) -> Dict[str, Any]:
    """Laplacian variance — very low or very high both indicate editing."""
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_sharpness failed: %s", exc)
        return _error("sharpness analysis failed")

    t = config.SHARPNESS_THRESHOLDS
    if lap_var <= t["very_low"]:
        risk, level = 0.75, "very low (over-smoothed)"
    elif lap_var <= t["low"]:
        risk, level = 0.40, "soft"
    elif lap_var >= t["very_high"]:
        risk, level = 0.55, "very high (over-sharpened)"
    else:
        risk, level = 0.10, "natural"

    return _envelope(
        value=lap_var,
        risk=risk,
        level=level,
        unit="Laplacian var",
        explanation=(
            f"Laplacian variance = {lap_var:.1f}. {level}. "
            "Over-sharpening and over-smoothing both raise risk."
        ),
    )


# ---------------------------------------------------------------------------
# F. Texture (local variance, block-wise)
# ---------------------------------------------------------------------------

def analyze_texture(bgr: np.ndarray) -> Dict[str, Any]:
    """Mean per-block grayscale std across 8×8 blocks.

    Real textures (skin pores, fabric, foliage) produce measurable local
    variance. Smoothing filters collapse it. Rule-based; no ML.
    """
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h, w = gray.shape
        # Pad to multiple of 8 so no pixels are dropped.
        pad_h = (-h) % 8
        pad_w = (-w) % 8
        if pad_h or pad_w:
            gray = np.pad(gray, ((0, pad_h), (0, pad_w)), mode="edge")
        h, w = gray.shape
        blocks = gray.reshape(h // 8, 8, w // 8, 8).swapaxes(1, 2)
        block_stds = blocks.reshape(-1, 64).std(axis=1)
        mean_std = float(block_stds.mean())
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_texture failed: %s", exc)
        return _error("texture analysis failed")

    t = config.TEXTURE_THRESHOLDS
    if mean_std <= t["very_low"]:
        risk, level = 0.70, "very smooth (texture lost)"
    elif mean_std <= t["low"]:
        risk, level = 0.45, "smooth"
    elif mean_std >= t["very_high"]:
        risk, level = 0.35, "unusually busy / noisy"
    else:
        risk, level = 0.10, "natural texture"

    return _envelope(
        value=mean_std,
        risk=risk,
        level=level,
        unit="mean block σ",
        explanation=(
            f"Local 8×8 texture σ = {mean_std:.2f}. {level}. "
            "Heavy smoothing flattens local texture."
        ),
    )


# ---------------------------------------------------------------------------
# G. Edges (Canny)
# ---------------------------------------------------------------------------

def analyze_edges(bgr: np.ndarray) -> Dict[str, Any]:
    """Canny edge density — smoothing reduces edge count significantly."""
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        density = float(edges.mean() / 255.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_edges failed: %s", exc)
        return _error("edge analysis failed")

    t = config.EDGE_THRESHOLDS
    if density <= t["very_sparse"]:
        risk, level = 0.65, "very sparse (heavy smoothing)"
    elif density <= t["reduced"]:
        risk, level = 0.30, "reduced"
    else:
        risk, level = 0.10, "typical"

    return _envelope(
        value=density,
        risk=risk,
        level=level,
        unit="edge fraction",
        explanation=(
            f"Canny edge density = {density * 100:.2f}% of pixels. {level}."
        ),
    )


# ---------------------------------------------------------------------------
# H. JPEG compression (SUPPORTING ONLY — not scored)
# ---------------------------------------------------------------------------

def analyze_jpeg(bgr: np.ndarray, pil_image: Image.Image) -> Dict[str, Any]:
    """Approximate JPEG blockiness from 8×8 grid discontinuities.

    PNG uploads are lossless; blockiness will be near-zero, which is
    correct and not an editing signal. Marked `scored=False`.
    """
    fmt = (pil_image.format or "UNKNOWN").upper()
    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h, w = gray.shape
        if h < 16 or w < 16:
            return {
                "value": 0.0,
                "level": "insufficient resolution for blockiness check",
                "explanation": "Image too small for reliable blockiness estimate.",
                "unit": "blockiness",
                "scored": False,
                "format": fmt,
            }
        dh = np.abs(np.diff(gray, axis=1))
        dv = np.abs(np.diff(gray, axis=0))
        block_h = float(dh[:, 7::8].mean()) if dh.shape[1] > 8 else 0.0
        block_v = float(dv[7::8, :].mean()) if dv.shape[0] > 8 else 0.0
        blockiness = (block_h + block_v) / 2.0
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_jpeg failed: %s", exc)
        return {
            "error": "JPEG indicator analysis failed",
            "scored": False,
            "format": fmt,
        }

    t = config.JPEG_THRESHOLDS
    if blockiness >= t["blockiness_high"]:
        level = "high — suggests recompression or editing"
    elif blockiness >= t["blockiness_moderate"]:
        level = "moderate"
    else:
        level = "low / lossless"

    if fmt == "PNG":
        explanation = (
            f"Format is PNG (lossless). Blockiness score = {blockiness:.2f}. "
            "PNG is not expected to show JPEG artifacts — this is normal."
        )
    else:
        explanation = (
            f"JPEG 8×8 blockiness = {blockiness:.2f}. {level}. "
            "Supporting indicator only — not included in the Trust Score."
        )

    return {
        "value": round(blockiness, 3),
        "level": level,
        "explanation": explanation,
        "unit": "blockiness",
        "scored": False,
        "format": fmt,
    }


# ---------------------------------------------------------------------------
# I. Metadata (SUPPORTING ONLY — not scored)
# ---------------------------------------------------------------------------

def analyze_metadata(pil_image: Image.Image) -> Dict[str, Any]:
    """Report available EXIF / PNG text chunks. Never penalised in the score."""
    fmt = (pil_image.format or "UNKNOWN").upper()
    info = {
        "format": fmt,
        "mode": pil_image.mode,
        "size": pil_image.size,
        "has_exif": False,
        "exif_fields": {},
        "editing_software": None,
        "notes": "",
        "scored": False,
    }

    try:
        exif = pil_image.getexif()
        if exif:
            from PIL.ExifTags import TAGS
            for tag_id, value in exif.items():
                name = TAGS.get(tag_id, str(tag_id))
                # Only store compact scalar values, truncate long ones
                try:
                    sval = str(value)
                except Exception:
                    sval = "<unreadable>"
                if len(sval) > 120:
                    sval = sval[:117] + "..."
                info["exif_fields"][name] = sval
            info["has_exif"] = len(info["exif_fields"]) > 0

        software = str(info["exif_fields"].get("Software", "")).strip()
        if software:
            info["editing_software"] = software

        if fmt == "PNG":
            png_text = getattr(pil_image, "text", None) or {}
            if png_text:
                info["notes"] = (
                    f"PNG text chunks present: {', '.join(list(png_text)[:5])}."
                )
            else:
                info["notes"] = (
                    "No EXIF (PNG typically carries only optional text chunks)."
                )
        elif not info["has_exif"]:
            info["notes"] = (
                "No EXIF metadata present — may have been stripped. "
                "This alone does not indicate editing."
            )
        else:
            info["notes"] = "EXIF metadata present."

    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_metadata failed: %s", exc)
        info["notes"] = "Metadata could not be read from this image."

    return info


# ---------------------------------------------------------------------------
# J. Skin Smoothing (conditional; only scored if skin is present)
# ---------------------------------------------------------------------------

def analyze_skin_smoothing(bgr: np.ndarray) -> Dict[str, Any]:
    """Detect smoothing in skin-tone regions via YCrCb mask + residual noise."""
    try:
        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        lower = np.array([0, 133, 77], dtype=np.uint8)
        upper = np.array([255, 173, 127], dtype=np.uint8)
        mask = cv2.inRange(ycrcb, lower, upper)
        skin_ratio = float(mask.mean() / 255.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_skin_smoothing failed: %s", exc)
        return _error("skin smoothing analysis failed")

    t = config.SKIN_THRESHOLDS
    if skin_ratio < t["min_skin_ratio"]:
        return {
            "value": round(skin_ratio, 3),
            "level": "no significant skin region",
            "explanation": (
                f"Skin-tone pixels = {skin_ratio * 100:.1f}% of image "
                "(below the threshold needed for a reliable measurement). "
                "Skin-smoothing score not applied."
            ),
            "unit": "skin fraction",
            "scored": False,
        }

    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        blur = cv2.GaussianBlur(gray, (7, 7), 0)
        residual = gray - blur
        mask_bool = mask > 0
        skin_noise = float(residual[mask_bool].std()) if mask_bool.any() else 0.0
    except Exception as exc:  # noqa: BLE001
        logger.warning("skin smoothing residual failed: %s", exc)
        return _error("skin smoothing residual failed")

    if skin_noise <= t["noise_very_low"]:
        risk, level = 0.85, "very smooth (likely beauty filter)"
    elif skin_noise <= t["noise_low"]:
        risk, level = 0.50, "smooth"
    else:
        risk, level = 0.10, "natural skin texture"

    return _envelope(
        value=skin_noise,
        risk=risk,
        level=level,
        unit="skin σ",
        explanation=(
            f"Skin region covers {skin_ratio * 100:.1f}% of image; "
            f"residual noise σ = {skin_noise:.2f}. {level}."
        ),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_all_analyses(prepared: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Run every calculator on the preprocessed image.

    Returns a dict keyed by feature name. Each value is either the standard
    envelope or an error envelope (`{"error": ..., "scored": False}`).
    """
    bgr = prepared["cv_image"]
    pil = prepared["pil_image"]

    return {
        "noise":          analyze_noise(bgr),
        "saturation":     analyze_saturation(bgr),
        "contrast":       analyze_contrast(bgr),
        "color_balance":  analyze_color_balance(bgr),
        "sharpness":      analyze_sharpness(bgr),
        "texture":        analyze_texture(bgr),
        "edges":          analyze_edges(bgr),
        "skin_smoothing": analyze_skin_smoothing(bgr),
        "jpeg":           analyze_jpeg(bgr, pil),
        "metadata":       analyze_metadata(pil),
    }