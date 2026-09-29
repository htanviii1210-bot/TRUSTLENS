from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import uuid
from datetime import datetime

from analyzer import run_analysis
from scoring import compute_trust_score
from explainer import build_explanation

app = FastAPI(title="TrustLens API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


@app.get("/")
def root():
    return {"service": "TrustLens", "status": "running",
            "endpoints": ["/api/analyze", "/health"]}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported file type: {file.content_type}")

    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")

    # Persist for audit
    fname = f"{uuid.uuid4().hex}_{file.filename}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    try:
        with open(fpath, "wb") as f:
            f.write(data)

        findings = run_analysis(data)
        trust_score, risk_score, verdict, breakdown = compute_trust_score(findings)
        explanation = build_explanation(findings, breakdown, trust_score, verdict)

        # Indicator percent contribution for UI bars
        indicators = []
        labels = {
            'noise': 'Noise / Grain',
            'saturation': 'Saturation',
            'contrast': 'Contrast',
            'color_balance': 'Color Balance',
            'sharpness': 'Sharpness',
            'edges': 'Edge Density',
            'jpeg_artifacts': 'Compression',
            'face_smoothing': 'Skin Smoothing',
            'metadata': 'Metadata',
        }
        for k, v in breakdown.items():
            indicators.append({
                'key': k,
                'label': labels.get(k, k.title()),
                'risk_percent': round(v['risk'] * 100, 1),
                'weight_percent': round(v['weight'] * 100, 1),
            })
        indicators.sort(key=lambda x: x['risk_percent'], reverse=True)

        return JSONResponse({
            'success': True,
            'trust_score': trust_score,
            'risk_score': risk_score,
            'verdict': verdict,
            'indicators': indicators,
            'explanation': explanation,
            'raw_findings': findings,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")