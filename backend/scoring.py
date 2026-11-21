"""
TrustLens — Scoring Module
===========================
Implements spec §6:

    R = Σ(wᵢ · rᵢ) / Σ(wᵢ)       (weighted average of feature risks)
    T = (1 − R) × 100            (Trust Score, 0–100)

Design guarantees:
  - All risk values clamped to [0, 1].
  - Weights are non-negative (asserted from config).
  - Features that failed to compute are excluded and remaining weights
    automatically renormalize (the divisor becomes the sum of *computed*
    weights only).
  - JPEG and metadata never contribute to R (they carry `scored=False`
    from image_analysis.py, so this module filters them out at intake).
  - Every scored feature's explanation is collected verbatim for the
    dashboard, so users can trace exactly which feature moved the score.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import config


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _verdict_for(score: float) -> str:
    """Map Trust Score → verdict label. VERDICT_BUCKETS is ordered high→low."""
    for threshold, label in config.VERDICT_BUCKETS:
        if score >= threshold:
            return label
    return config.VERDICT_BUCKETS[-1][1]


def _weight_for(feature: str, findings: Dict[str, Any]) -> float:
    """Return the effective weight for a feature, or 0.0 if it shouldn't count.

    Rules:
      - `skin_smoothing` participates only when the analyzer marked it scored
        (i.e. enough skin was present), using SKIN_SMOOTHING_WEIGHT.
      - All other scored features use FEATURE_WEIGHTS.
    """
    if feature == "skin_smoothing":
        return config.SKIN_SMOOTHING_WEIGHT
    return float(config.FEATURE_WEIGHTS.get(feature, 0.0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_score(findings: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the Trust Score from per-feature findings.

    Parameters
    ----------
    findings : dict
        Output of `image_analysis.run_all_analyses(...)`.

    Returns
    -------
    dict with keys:
        trust_score      : float  (0–100, rounded to 2 dp)
        risk             : float  (0–1,  weighted, rounded to 4 dp)
        verdict          : str
        scored_features  : list of feature dicts that entered the score
        support_features : list of feature dicts shown as context (jpeg, metadata)
        breakdown        : per-feature {risk, weight, contribution}
        warnings         : list of str (any anomalies, e.g. no features computed)
        formula          : human-readable string of the computation
    """
    warnings: List[str] = []

    # -- 1. Partition features -------------------------------------------------
    scored_pairs: List[Tuple[str, Dict[str, Any], float]] = []
    support_features: List[Dict[str, Any]] = []

    for name, data in findings.items():
        if not isinstance(data, dict):
            warnings.append(f"Ignored malformed finding for '{name}'.")
            continue

        # Errors and support-only features are excluded from the score.
        is_error = "error" in data
        is_scored = bool(data.get("scored", False)) and not is_error
        weight = _weight_for(name, findings)

        if is_error:
            warnings.append(
                f"Feature '{name}' could not be computed: {data['error']}."
            )
            continue

        if not is_scored or weight <= 0.0:
            support_features.append({"key": name, **data})
            continue

        scored_pairs.append((name, data, weight))

    # -- 2. Compute weighted risk ---------------------------------------------
    if not scored_pairs:
        warnings.append(
            "No scored features could be evaluated. Returning neutral score."
        )
        return {
            "trust_score": 50.0,
            "risk": 0.5,
            "verdict": "Insufficient data for a confident verdict",
            "scored_features": [],
            "support_features": support_features,
            "breakdown": {},
            "warnings": warnings,
            "formula": "No features scored; neutral fallback applied.",
        }

    total_weight = 0.0
    weighted_sum = 0.0
    breakdown: Dict[str, Dict[str, float]] = {}
    scored_features_out: List[Dict[str, Any]] = []

    for name, data, weight in scored_pairs:
        risk = _clamp(data.get("risk", 0.0))
        contribution = weight * risk
        weighted_sum += contribution
        total_weight += weight

        breakdown[name] = {
            "risk": round(risk, 4),
            "weight": round(weight, 4),
            "contribution": round(contribution, 4),
        }

        scored_features_out.append({
            "key": name,
            "value": data.get("value"),
            "unit": data.get("unit"),
            "level": data.get("level"),
            "risk": round(risk, 4),
            "weight": round(weight, 4),
            "contribution": round(contribution, 4),
            "explanation": data.get("explanation", ""),
        })

    # -- 3. Guard against zero total weight (config bug) ----------------------
    if total_weight <= 1e-9:
        warnings.append(
            "Total of evaluated weights is zero. Check FEATURE_WEIGHTS in config."
        )
        return {
            "trust_score": 50.0,
            "risk": 0.5,
            "verdict": "Insufficient data for a confident verdict",
            "scored_features": scored_features_out,
            "support_features": support_features,
            "breakdown": breakdown,
            "warnings": warnings,
            "formula": "Weight sum was zero; neutral fallback applied.",
        }

    # -- 4. Final risk & trust -------------------------------------------------
    R = weighted_sum / total_weight
    R = _clamp(R)
    T = round((1.0 - R) * 100.0, 2)
    verdict = _verdict_for(T)

    formula = (
        f"R = Σ(wᵢ·rᵢ) / Σwᵢ = {weighted_sum:.4f} / {total_weight:.4f} = {R:.4f}; "
        f"T = (1 − R) × 100 = {T:.2f}"
    )

    # -- 5. Sort scored features for display (highest contribution first) -----
    scored_features_out.sort(key=lambda f: f["contribution"], reverse=True)

    return {
        "trust_score": T,
        "risk": round(R, 4),
        "verdict": verdict,
        "scored_features": scored_features_out,
        "support_features": support_features,
        "breakdown": breakdown,
        "warnings": warnings,
        "formula": formula,
    }


# ---------------------------------------------------------------------------
# Convenience: one-shot audit print (development only)
# ---------------------------------------------------------------------------

def debug_print(result: Dict[str, Any]) -> None:
    """Prints a compact audit of the scoring result. Handy during dev."""
    print(f"Trust Score: {result['trust_score']}  →  {result['verdict']}")
    print(f"Risk R: {result['risk']}  |  {result['formula']}")
    print("\nScored features (descending contribution):")
    for f in result["scored_features"]:
        print(
            f"  - {f['key']:15s} risk={f['risk']:.3f} "
            f"weight={f['weight']:.3f} contrib={f['contribution']:.3f}  "
            f"[{f['level']}]"
        )
    if result["support_features"]:
        print("\nSupport-only features (not scored):")
        for f in result["support_features"]:
            print(f"  - {f['key']}: {f.get('level', 'n/a')}")
    if result["warnings"]:
        print("\nWarnings:")
        for w in result["warnings"]:
            print(f"  ! {w}")