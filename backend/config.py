"""
TrustLens — Configuration Module
=================================
All tunable thresholds, weights, and constants live here.
No logic. No imports from other project modules.

NOTE ON THRESHOLDS
------------------
The numeric thresholds below are *heuristic starting values* chosen from
general image-forensics principles and common color-statistics ranges.
They are NOT scientifically validated filter-detection limits. Real-world
photos (low-light, DSLR RAW exports, HDR, B&W, etc.) can and will fall
outside these ranges. Treat every risk value as an *indicator*, not proof.
"""

# ---------------------------------------------------------------------------
# UPLOAD / FILE VALIDATION
# ---------------------------------------------------------------------------

# Max upload size in bytes (15 MB).
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024

# MIME types we accept from the browser.
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
}

# Pillow image formats we accept after decoding.
# This is the *real* validation — MIME headers can lie.
ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "MPO"}  # MPO = multi-picture JPEG (iPhone)

# Longest side (px) to which images are downscaled before feature analysis.
# Keeps analysis fast and deterministic across huge images.
ANALYSIS_MAX_DIMENSION = 1024

# Minimum dimensions for a meaningful analysis.
MIN_IMAGE_WIDTH = 32
MIN_IMAGE_HEIGHT = 32


# ---------------------------------------------------------------------------
# FEATURE WEIGHTS  (used in R = Σ(wᵢ·rᵢ) / Σwᵢ)
# ---------------------------------------------------------------------------
# Only features listed here participate in the Trust Score.
# JPEG compression + metadata are DISPLAY-ONLY support sections (spec §6).
#
# Rationale for each weight:
#   noise        — strongly smoothed images are a hallmark of beauty/vivid filters
#   saturation   — the most common signal of Instagram / VSCO style grading
#   contrast     — in-camera HDR and "clarity" filters push this
#   color_balance— tinted overlays leave per-channel casts
#   sharpness    — over-sharpening vs. over-smoothing both edit signals
#   texture      — skin/foliage smoothing drops local variance
#   edges        — Canny density falls on heavily-smoothed images
#
# Sum of weights = 1.00 (so R is already normalized).
# If a feature fails to compute, scoring.py renormalizes over remaining ones.

FEATURE_WEIGHTS = {
    "noise":         0.16,
    "saturation":    0.16,
    "contrast":      0.12,
    "color_balance": 0.12,
    "sharpness":     0.12,
    "texture":       0.10,
    "edges":         0.10,
    # Note: sum = 0.88 intentionally left below 1.0.
    # We add "skin_smoothing" only if skin is detected (below) — see scoring.py.
    # The scoring module renormalizes to sum(w)=1 automatically.
}

# Skin-tone smoothing is only counted when enough skin pixels exist.
# Its weight is applied conditionally in scoring.py.
SKIN_SMOOTHING_WEIGHT = 0.12


# ---------------------------------------------------------------------------
# INDIVIDUAL FEATURE THRESHOLDS
# ---------------------------------------------------------------------------
# Each block defines the breakpoints for a piecewise risk curve.
# risk ∈ [0, 1]. Lower = more natural; higher = more filter-like.

# --- A. NOISE --------------------------------------------------------------
# Gaussian residual std (σ) after a (5,5) blur, computed on grayscale.
# Natural photographs typically show σ in the 3–10 range at native scale.
# Anything below ~2.5 usually indicates smoothing or heavy denoising.
NOISE_THRESHOLDS = {
    "very_low": 2.5,     # ≤ → risk 0.85
    "low":      4.0,     # ≤ → risk 0.55
    "moderate": 7.0,     # ≤ → risk 0.20
    # above "moderate" → risk 0.05 (natural grain)
}

# --- B. SATURATION ---------------------------------------------------------
# HSV S-channel mean and the fraction of pixels with S > 200.
SATURATION_THRESHOLDS = {
    "mean_very_high": 140,      # ≥ → strong oversaturation
    "mean_high":      120,      # ≥ → elevated
    "mean_very_low":  40,       # ≤ → near-grayscale / desaturated style
    "frac_high_pixels": 0.35,   # ≥ 35% of pixels S>200 → strong
    "frac_mild_pixels": 0.20,   # ≥ 20% → elevated
}

# --- C. CONTRAST -----------------------------------------------------------
# Grayscale std and histogram clipping fraction (both ends combined).
CONTRAST_THRESHOLDS = {
    "std_high":        80.0,   # ≥ → strong contrast
    "std_elevated":    65.0,   # ≥ → elevated
    "clipping_high":   0.08,   # ≥ 8% of pixels near 0 or 255
    "clipping_mild":   0.04,
}

# --- D. COLOR BALANCE ------------------------------------------------------
# Max per-channel deviation from the RGB mean, normalized by the mean.
# 0 = perfectly balanced; >0.15 suggests a tint.
COLOR_BALANCE_THRESHOLDS = {
    "deviation_strong": 0.15,
    "deviation_mild":   0.08,
}

# --- E. SHARPNESS (Laplacian variance) -------------------------------------
SHARPNESS_THRESHOLDS = {
    "very_low":   30.0,     # ≤ → over-smoothed
    "low":        70.0,     # ≤ → soft
    "very_high": 1500.0,    # ≥ → over-sharpened
}

# --- F. TEXTURE (local variance, 8x8 blocks) -------------------------------
# Mean of per-block grayscale std. Natural textures (skin, fabric, foliage)
# usually sit in the 5–25 range; very smooth skin can drop below 3.
TEXTURE_THRESHOLDS = {
    "very_low":  3.0,
    "low":       6.0,
    "very_high": 40.0,      # ≥ → unusually busy (may hint at synthetic)
}

# --- G. EDGE DENSITY (Canny) -----------------------------------------------
# Fraction of pixels flagged as edges by Canny(100, 200).
EDGE_THRESHOLDS = {
    "very_sparse": 0.02,    # ≤ → heavy smoothing
    "reduced":     0.05,    # ≤ → soft
}

# --- H. JPEG COMPRESSION (blockiness) — SUPPORTING ONLY --------------------
# Not part of the score. Displayed in the dashboard as context.
JPEG_THRESHOLDS = {
    "blockiness_high":     12.0,
    "blockiness_moderate":  6.0,
}

# --- I. SKIN SMOOTHING (face/beauty filter) --------------------------------
# Only applied when skin_ratio ≥ min_skin_ratio.
SKIN_THRESHOLDS = {
    "min_skin_ratio": 0.05,   # ≥5% skin pixels required to score this feature
    "noise_very_low": 3.0,    # ≤ → beauty filter likely
    "noise_low":      5.0,    # ≤ → smoothed
}

# ---------------------------------------------------------------------------
# SCORE VERDICT BUCKETS
# ---------------------------------------------------------------------------
# Mapping from Trust Score (0–100) to a human-readable category.
# Evaluated top-down; first match wins.

VERDICT_BUCKETS = [
    (80, "Authentic / Minimal Filtering"),
    (60, "Mostly Natural with Light Editing"),
    (40, "Moderately Filtered"),
    (20, "Heavily Filtered"),
    (0,  "Extremely Edited / Synthetic Look"),
]

# ---------------------------------------------------------------------------
# EXPLANATION TONE
# ---------------------------------------------------------------------------
# Each feature returns a short sentence in scoring.py.
# This dict centralizes the leading emoji so the dashboard stays consistent.

STATUS_ICONS = {
    "ok":    "✅",
    "warn":  "⚠️",
    "alert": "🚨",
    "info":  "ℹ️",
}