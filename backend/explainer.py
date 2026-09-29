"""
TrustLens Explainer Module
Converts technical findings into human-readable explanation.
"""


def build_explanation(findings, breakdown, trust_score, verdict):
    bullets = []

    # Noise
    n = findings.get('noise', {})
    if n.get('risk', 0) >= 0.5:
        bullets.append(
            f"⚠️ **Noise / Grain:** {n['level']} (σ={n['noise_std']}). "
            f"Low sensor noise is a hallmark of smoothing or beauty filters."
        )
    else:
        bullets.append(
            f"✅ **Noise / Grain:** {n['level']} (σ={n['noise_std']}) — "
            f"consistent with natural camera capture."
        )

    # Saturation
    s = findings.get('saturation', {})
    if s.get('risk', 0) >= 0.4:
        bullets.append(
            f"⚠️ **Saturation:** {s['level']} — mean {s['mean_saturation']}, "
            f"{round(s['high_sat_ratio']*100,1)}% pixels heavily saturated. "
            f"Typical of vivid Instagram-style filters."
        )
    else:
        bullets.append(
            f"✅ **Saturation:** {s['level']} — mean {s['mean_saturation']}."
        )

    # Contrast
    c = findings.get('contrast', {})
    if c.get('risk', 0) >= 0.35:
        bullets.append(
            f"⚠️ **Contrast:** {c['level']} (σ={c['contrast_std']}, "
            f"clipping={round(c['clipping_ratio']*100,2)}%)."
        )
    else:
        bullets.append(f"✅ **Contrast:** {c['level']} (σ={c['contrast_std']}).")

    # Color balance
    cb = findings.get('color_balance', {})
    if cb.get('risk', 0) >= 0.4:
        bullets.append(
            f"⚠️ **Color Cast:** {cb['level']} — R={cb['r_mean']}, "
            f"G={cb['g_mean']}, B={cb['b_mean']} (deviation {cb['deviation']}). "
            f"Indicates a tinted filter was applied."
        )
    else:
        bullets.append(f"✅ **Color Balance:** {cb['level']}.")

    # Sharpness
    sh = findings.get('sharpness', {})
    if sh.get('risk', 0) >= 0.4:
        bullets.append(
            f"⚠️ **Sharpness:** {sh['level']} (Laplacian var {sh['laplacian_variance']}). "
            f"Possible over-sharpening or over-smoothing."
        )
    else:
        bullets.append(f"✅ **Sharpness:** {sh['level']}.")

    # Edges
    e = findings.get('edges', {})
    if e.get('risk', 0) >= 0.3:
        bullets.append(
            f"⚠️ **Edge Density:** {e['level']} ({round(e['edge_density']*100,2)}%)."
        )

    # JPEG
    j = findings.get('jpeg_artifacts', {})
    if j.get('risk', 0) >= 0.4:
        bullets.append(
            f"⚠️ **Compression Artifacts:** {j['level']} — blockiness {j['blockiness']}, "
            f"suggests re-saving after editing."
        )

    # Face smoothing
    f = findings.get('face_smoothing', {})
    if f.get('risk', 0) >= 0.4:
        bullets.append(
            f"⚠️ **Skin Smoothing:** {f['level']} — skin noise σ="
            f"{f.get('skin_noise_std', 0)}. Common in beauty filters."
        )

    # Metadata
    m = findings.get('metadata', {})
    if m.get('editing_software_detected'):
        bullets.append(
            f"🚨 **Metadata:** Editing software detected → "
            f"\"{m.get('software')}\". Strong indication of post-processing."
        )
    elif m.get('has_exif'):
        bullets.append(
            f"✅ **Metadata:** Original EXIF present "
            f"(camera: {m.get('make') or 'n/a'} {m.get('model') or ''})."
        )
    else:
        bullets.append(
            "⚠️ **Metadata:** No EXIF data found — may have been stripped, "
            "common after social media processing or editing."
        )

    # Compose narrative
    if trust_score >= 80:
        summary = ("This image appears **largely authentic**. Most forensic "
                   "indicators align with an unedited camera capture.")
    elif trust_score >= 60:
        summary = ("This image is **mostly natural**, but a few minor signs "
                   "of light editing or in-camera processing are present.")
    elif trust_score >= 40:
        summary = ("This image shows **moderate filter usage**. Multiple "
                   "indicators suggest deliberate aesthetic processing.")
    else:
        summary = ("This image is **heavily processed**. Strong indicators of "
                   "filters, smoothing, or synthetic enhancement were found.")

    # Top contributing factors
    top = sorted(breakdown.items(), key=lambda kv: kv[1]['risk'], reverse=True)[:3]
    top_str = ", ".join([f"{k} (risk {v['risk']})" for k, v in top])

    summary += f"\n\n**Top contributing factors:** {top_str}."

    return {
        'verdict': verdict,
        'summary': summary,
        'bullets': bullets,
    }