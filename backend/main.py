"""
TrustLens — FastAPI Application
================================
Endpoints
---------
GET  /                 — service info
GET  /health           — liveness probe
POST /api/analyze      — upload an image, receive analysis + trust score

Pipeline (per request)
----------------------
  bytes → preprocessing.validate_and_prepare()
        → image_analysis.run_all_analyses()
        → scoring.compute_score()
        → JSON response

Error contract
--------------
All non-2xx responses use FastAPI's standard:

    {"detail": {"code": "<machine_code>", "message": "<human_message>"}}

so the frontend can render user-friendly text based on `code` and fall
back to `message` when it doesn't recognise the code.

This module never crashes on bad input; every failure path is caught and
returned as structured JSON.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
import image_analysis
import preprocessing
import scoring


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
)
logger = logging.getLogger("trustlens")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TrustLens API",
    version="2.0.0",
    description=(
        "Explainable, rule-based image analysis. "
        "Provides an estimated Trust Score and per-feature findings."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # prototype: allow any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _err(status: int, code: str, message: str) -> HTTPException:
    """Construct a structured HTTPException the frontend can parse."""
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _persist_upload(image_bytes: bytes, original_name: str) -> str:
    """Save the original bytes for audit. Best-effort; never fatal."""
    try:
        safe_name = os.path.basename(original_name or "upload.bin")[:120]
        fname = f"{uuid.uuid4().hex}_{safe_name}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(image_bytes)
        return fname
    except Exception as exc:  # noqa: BLE001
        logger.warning("Upload persist failed (non-fatal): %s", exc)
        return ""


def _build_response(
    prepared: Dict[str, Any],
    findings: Dict[str, Dict[str, Any]],
    score_result: Dict[str, Any],
    original_filename: str,
    stored_filename: str,
) -> Dict[str, Any]:
    """Assemble the JSON payload the frontend consumes."""

    # File info card in the dashboard
    file_info = {
        "filename": original_filename or "upload",
        "stored_as": stored_filename or None,
        "format": prepared["format"],
        "mode": prepared["mode_original"],
        "original_width": prepared["original_size"][0],
        "original_height": prepared["original_size"][1],
        "analysis_width": prepared["analysis_size"][0],
        "analysis_height": prepared["analysis_size"][1],
        "was_resized": prepared["was_resized"],
    }

    # Support-only findings, keyed for the dashboard
    support_map = {f["key"]: f for f in score_result["support_features"]}
    jpeg_info = support_map.get("jpeg", {
        "value": None, "level": "unavailable",
        "explanation": "JPEG indicator analysis was not available.",
    })
    metadata_info = support_map.get("metadata", {
        "format": prepared["format"],
        "has_exif": False,
        "exif_fields": {},
        "editing_software": None,
        "notes": "Metadata was not available.",
    })

    # Skin-smoothing may be support-only (no skin) or scored — normalise.
    skin_info = None
    for f in score_result["scored_features"]:
        if f["key"] == "skin_smoothing":
            skin_info = f
            break
    if skin_info is None and "skin_smoothing" in support_map:
        skin_info = support_map["skin_smoothing"]

    return {
        "success": True,
        "generated_at": _utc_now_iso(),
        "file_info": file_info,

        # -- Score block ----------------------------------------------------
        "trust_score": score_result["trust_score"],
        "risk": score_result["risk"],
        "verdict": score_result["verdict"],
        "formula": score_result["formula"],

        # -- Per-feature findings ------------------------------------------
        "scored_features": score_result["scored_features"],
        "skin_smoothing": skin_info,

        # -- Support-only sections -----------------------------------------
        "jpeg_info": jpeg_info,
        "metadata_info": metadata_info,

        # -- Diagnostics ----------------------------------------------------
        "warnings": score_result["warnings"],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "TrustLens",
        "version": "2.0.0",
        "status": "running",
        "endpoints": ["/health", "/api/analyze"],
        "time": _utc_now_iso(),
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "time": _utc_now_iso()}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> JSONResponse:
    """
    Analyse an uploaded image and return a Trust Score + per-feature findings.

    Happy-path returns 200 with a JSON body. Any failure returns a structured
    error with a stable `code` for the frontend.
    """
    original_name = file.filename or "upload"

    # -- 1. Read bytes ------------------------------------------------------
    try:
        image_bytes = await file.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read upload: %s", exc)
        raise _err(400, "read_failed", "Could not read the uploaded file.")

    if not image_bytes:
        raise _err(400, "empty_upload", "The uploaded file is empty.")

    # Quick size guard before any decoding
    if len(image_bytes) > config.MAX_FILE_SIZE_BYTES:
        limit_mb = config.MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise _err(
            413,
            "file_too_large",
            f"File is too large. Maximum allowed size is {limit_mb} MB.",
        )

    # -- 2. Preprocessing ---------------------------------------------------
    try:
        prepared = preprocessing.validate_and_prepare(image_bytes)
    except preprocessing.PreprocessingError as exc:
        logger.info("Preprocessing rejected upload: %s (%s)", exc.message, exc.code)
        raise _err(400, exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001 — belt and braces
        logger.exception("Unexpected preprocessing failure: %s", exc)
        raise _err(
            500,
            "preprocessing_failed",
            "The image could not be prepared for analysis.",
        )

    # -- 3. Persist (audit trail; non-fatal) -------------------------------
    stored_name = _persist_upload(image_bytes, original_name)

    # -- 4. Feature analysis ------------------------------------------------
    try:
        findings = image_analysis.run_all_analyses(prepared)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis engine failed: %s", exc)
        raise _err(
            500,
            "analysis_failed",
            "The analysis engine encountered an unexpected error.",
        )

    # -- 5. Scoring ---------------------------------------------------------
    try:
        score_result = scoring.compute_score(findings)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scoring failed: %s", exc)
        raise _err(
            500,
            "scoring_failed",
            "The Trust Score could not be computed for this image.",
        )

    # -- 6. Respond ---------------------------------------------------------
    payload = _build_response(
        prepared=prepared,
        findings=findings,
        score_result=score_result,
        original_filename=original_name,
        stored_filename=stored_name,
    )
    logger.info(
        "Analysed '%s' → score=%.2f verdict='%s' warnings=%d",
        original_name,
        score_result["trust_score"],
        score_result["verdict"],
        len(score_result["warnings"]),
    )
    return JSONResponse(status_code=200, content=payload)


# ---------------------------------------------------------------------------
# Global exception handler — ensures no raw traceback ever hits the client
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "internal_error",
                "message": "An unexpected error occurred. Please try again.",
            }
        },
    )