"""
TrustLens Scoring Engine
Aggregates forensic evidence into a 0-100 Trust Score.
"""

# Weight each indicator based on reliability for filter detection
WEIGHTS = {
    'noise': 0.15,
    'saturation': 0.15,
    'contrast': 0.10,
    'color_balance': 0.10,
    'sharpness': 0.10,
    'edges': 0.08,
    'jpeg_artifacts': 0.07,
    'face_smoothing': 0.15,
    'metadata': 0.10,
}


def _metadata_risk(meta):
    if meta.get('editing_software_detected'):
        return 0.9
    if meta.get('has_exif'):
        return 0.05
    # No EXIF at all is a mild signal (could be stripped or screenshot)
    return 0.35


def compute_trust_score(findings):
    """
    Returns (trust_score 0-100, risk_score 0-1, breakdown)
    """
    breakdown = {}
    total_risk = 0.0
    total_weight = 0.0

    for key, weight in WEIGHTS.items():
        if key == 'metadata':
            risk = _metadata_risk(findings.get('metadata', {}))
        else:
            risk = findings.get(key, {}).get('risk', 0.1)
        breakdown[key] = {
            'risk': round(risk, 3),
            'weight': weight,
        }
        total_risk += risk * weight
        total_weight += weight

    if total_weight > 0:
        total_risk /= total_weight

    trust_score = max(0, min(100, round((1 - total_risk) * 100)))

    if trust_score >= 80:
        verdict = "Authentic / Minimal Filtering"
    elif trust_score >= 60:
        verdict = "Mostly Natural with Light Editing"
    elif trust_score >= 40:
        verdict = "Moderately Filtered"
    elif trust_score >= 20:
        verdict = "Heavily Filtered"
    else:
        verdict = "Extremely Edited / Synthetic Look"

    return trust_score, round(total_risk, 3), verdict, breakdown