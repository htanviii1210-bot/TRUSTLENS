"""
TrustLens Analysis Engine
Combines forensic indicators, filter indicators, and metadata analysis.
"""
import cv2
import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS
import io
import math


def _to_cv(image_bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _pil_from_bytes(image_bytes):
    return Image.open(io.BytesIO(image_bytes))


# ---------- 1. Metadata Analysis ----------
def analyze_metadata(image_bytes):
    findings = {}
    try:
        pil = _pil_from_bytes(image_bytes)
        exif = pil.getexif()
        info = {}
        if exif:
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                info[str(tag)] = str(value)

        findings['has_exif'] = len(info) > 0
        findings['software'] = info.get('Software', None)
        findings['make'] = info.get('Make', None)
        findings['model'] = info.get('Model', None)
        findings['datetime'] = info.get('DateTime', None)

        # Heuristic: editing software in EXIF suggests post-processing
        suspicious_software = ['photoshop', 'lightroom', 'snapseed',
                               'vsco', 'gimp', 'picsart', 'facetune',
                               'meitu', 'beautyplus', 'airbrush']
        software_lower = (findings['software'] or '').lower()
        findings['editing_software_detected'] = any(s in software_lower
                                                    for s in suspicious_software)
    except Exception as e:
        findings['error'] = str(e)
        findings['has_exif'] = False
        findings['editing_software_detected'] = False
    return findings


# ---------- 2. Preprocessing ----------
def preprocess(image_bytes):
    img = _to_cv(image_bytes)
    if img is None:
        raise ValueError("Could not decode image")
    # Resize for consistency
    h, w = img.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return img


# ---------- 3. Analysis Module ----------
def analyze_noise(img):
    """Estimate high-frequency noise residual; filters tend to smooth it."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    residual = gray - blur
    noise_std = float(np.std(residual))
    # Natural photos usually > 3-6 std at this scale
    if noise_std < 2.5:
        level = "very low (heavily smoothed)"
        risk = 0.85
    elif noise_std < 4:
        level = "low (possibly smoothed)"
        risk = 0.55
    elif noise_std < 7:
        level = "moderate (typical)"
        risk = 0.2
    else:
        level = "high (natural grain)"
        risk = 0.05
    return {
        'noise_std': round(noise_std, 3),
        'level': level,
        'risk': risk,
    }


def analyze_saturation(img):
    """Over-saturated colors indicate heavy filter use."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    mean_sat = float(np.mean(sat))
    high_sat_ratio = float(np.mean(sat > 200))
    # Typical natural mean saturation ~ 60-110
    if mean_sat > 140 or high_sat_ratio > 0.35:
        level = "very high (oversaturated)"
        risk = 0.8
    elif mean_sat > 120 or high_sat_ratio > 0.20:
        level = "high"
        risk = 0.5
    elif mean_sat < 40:
        level = "very low (desaturated / B&W style)"
        risk = 0.35
    else:
        level = "natural range"
        risk = 0.1
    return {
        'mean_saturation': round(mean_sat, 2),
        'high_sat_ratio': round(high_sat_ratio, 3),
        'level': level,
        'risk': risk,
    }


def analyze_contrast(img):
    """Excessive contrast/clipping => filter signature."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    std = float(np.std(gray))
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    total = hist.sum()
    clipped_high = float(hist[250:].sum() / total)
    clipped_low = float(hist[:5].sum() / total)
    clipping = clipped_high + clipped_low
    if std > 80 or clipping > 0.08:
        level = "high (strong contrast / clipping)"
        risk = 0.6
    elif std > 65 or clipping > 0.04:
        level = "elevated"
        risk = 0.35
    else:
        level = "natural"
        risk = 0.1
    return {
        'contrast_std': round(std, 2),
        'clipping_ratio': round(clipping, 4),
        'level': level,
        'risk': risk,
    }


def analyze_color_balance(img):
    """Cast detection via per-channel means."""
    b, g, r = cv2.split(img.astype(np.float32))
    mean_b, mean_g, mean_r = float(b.mean()), float(g.mean()), float(r.mean())
    overall = (mean_b + mean_g + mean_r) / 3 + 1e-6
    dev = max(abs(mean_b - overall), abs(mean_g - overall), abs(mean_r - overall)) / overall
    if dev > 0.15:
        level = "strong color cast (filter applied)"
        risk = 0.7
    elif dev > 0.08:
        level = "mild color cast"
        risk = 0.4
    else:
        level = "balanced / natural"
        risk = 0.1
    return {
        'r_mean': round(mean_r, 2),
        'g_mean': round(mean_g, 2),
        'b_mean': round(mean_b, 2),
        'deviation': round(dev, 3),
        'level': level,
        'risk': risk,
    }


def analyze_sharpness(img):
    """Laplacian variance — very low or very high may indicate editing."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if lap_var < 30:
        level = "very low (over-smoothed / beauty filter)"
        risk = 0.75
    elif lap_var < 70:
        level = "low"
        risk = 0.4
    elif lap_var > 1500:
        level = "very high (over-sharpened)"
        risk = 0.55
    else:
        level = "natural"
        risk = 0.1
    return {
        'laplacian_variance': round(lap_var, 2),
        'level': level,
        'risk': risk,
    }


def analyze_edges(img):
    """Canny edge density — smoothing reduces edge density."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    density = float(edges.mean() / 255.0)
    if density < 0.02:
        level = "very sparse (heavy smoothing)"
        risk = 0.65
    elif density < 0.05:
        level = "reduced"
        risk = 0.3
    else:
        level = "typical"
        risk = 0.1
    return {
        'edge_density': round(density, 4),
        'level': level,
        'risk': risk,
    }


def analyze_jpeg_artifacts(img):
    """
    Approximate blockiness (JPEG quantization). Strong blockiness can suggest
    re-saves after editing.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    if h < 16 or w < 16:
        return {'blockiness': 0.0, 'level': 'unknown', 'risk': 0.1}

    dh = np.abs(np.diff(gray, axis=1))
    dv = np.abs(np.diff(gray, axis=0))
    # Differences at multiples of 8
    block_h = dh[:, 7::8].mean() if dh.shape[1] > 8 else 0
    block_v = dv[7::8, :].mean() if dv.shape[0] > 8 else 0
    blockiness = float((block_h + block_v) / 2)
    if blockiness > 12:
        level = "high (recompressed / edited)"
        risk = 0.55
    elif blockiness > 6:
        level = "moderate"
        risk = 0.3
    else:
        level = "low"
        risk = 0.1
    return {
        'blockiness': round(blockiness, 3),
        'level': level,
        'risk': risk,
    }


def run_analysis(image_bytes):
    """Runs all analysis modules on a preprocessed image."""
    img = preprocess(image_bytes)

    # Prepare an optional face-region analysis (rough beauty filter signal)
    face_info = analyze_face_smoothing(img)

    findings = {
        'noise': analyze_noise(img),
        'saturation': analyze_saturation(img),
        'contrast': analyze_contrast(img),
        'color_balance': analyze_color_balance(img),
        'sharpness': analyze_sharpness(img),
        'edges': analyze_edges(img),
        'jpeg_artifacts': analyze_jpeg_artifacts(img),
        'metadata': analyze_metadata(image_bytes),
        'face_smoothing': face_info,
    }
    return findings


def analyze_face_smoothing(img):
    """Detect skin-region smoothing using a simple skin-tone mask."""
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    lower = np.array([0, 133, 77], dtype=np.uint8)
    upper = np.array([255, 173, 127], dtype=np.uint8)
    mask = cv2.inRange(ycrcb, lower, upper)
    skin_ratio = float(mask.mean() / 255.0)
    if skin_ratio < 0.05:
        return {'skin_ratio': round(skin_ratio, 3),
                'level': 'no significant skin region',
                'risk': 0.05}

    skin_region = cv2.bitwise_and(img, img, mask=mask)
    gray = cv2.cvtColor(skin_region, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # High-frequency energy in skin region
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    residual = gray - blur
    skin_noise = float(np.std(residual[mask > 0])) if np.any(mask > 0) else 0.0

    if skin_noise < 3.0:
        level = "very smooth (likely beauty filter)"
        risk = 0.85
    elif skin_noise < 5.0:
        level = "smooth"
        risk = 0.5
    else:
        level = "natural skin texture"
        risk = 0.1
    return {
        'skin_ratio': round(skin_ratio, 3),
        'skin_noise_std': round(skin_noise, 3),
        'level': level,
        'risk': risk,
    }