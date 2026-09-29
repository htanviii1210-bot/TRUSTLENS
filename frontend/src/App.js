import React, { useState } from 'react';
import axios from 'axios';
import Uploader from './components/Uploader';
import Results from './components/Results';

const API = process.env.REACT_APP_API || 'http://localhost:8000';

function Logo() {
  return (
    <div className="logo">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M12 2L4 6v6c0 5 3.5 9 8 10 4.5-1 8-5 8-10V6l-8-4z"
              stroke="white" strokeWidth="2" strokeLinejoin="round" />
        <path d="M9 12l2 2 4-4" stroke="white" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleFile = (f) => {
    setFile(f);
    setResult(null);
    setError(null);
    setPreview(URL.createObjectURL(f));
  };

  const analyze = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append('file', file);

    try {
      const res = await axios.post(`${API}/api/analyze`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      });
      setResult(res.data);
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      setError(`Analysis failed: ${detail}`);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="app">
      <div className="nav">
        <div className="brand">
          <Logo />
          TrustLens
        </div>
        <div className="nav-tag">v1.0 · Prototype</div>
      </div>

      <div className="hero">
        <h1>Detect filters. Reveal authenticity.</h1>
        <p>
          Upload any image and TrustLens will analyze forensic indicators,
          filter signatures, and metadata to compute a transparent trust score.
        </p>
        <div className="badge-row">
          <span className="badge">Noise Analysis</span>
          <span className="badge">Color Forensics</span>
          <span className="badge">Skin Smoothing</span>
          <span className="badge">EXIF Inspection</span>
          <span className="badge">Explainable AI</span>
        </div>
      </div>

      <div className="panel">
        {!result && (
          <>
            <Uploader
              onFile={handleFile}
              onAnalyze={analyze}
              loading={loading}
              hasFile={!!file}
            />

            {preview && !loading && (
              <div style={{ marginTop: 24 }}>
                <img src={preview} alt="preview" className="preview-img" />
                <div className="row">
                  <button className="btn btn-ghost" onClick={reset}>
                    Clear
                  </button>
                </div>
              </div>
            )}

            {loading && (
              <div className="loader">
                <div className="spinner" />
                <div style={{ color: 'var(--muted)', fontSize: 14 }}>
                  Running forensic analysis…
                </div>
              </div>
            )}

            {error && <div className="error">{error}</div>}
          </>
        )}

        {result && (
          <>
            <Results data={result} previewUrl={preview} />
            <div className="row" style={{ marginTop: 32 }}>
              <button className="btn btn-ghost" onClick={reset}>
                ← Analyze another image
              </button>
            </div>
          </>
        )}
      </div>

      <div className="footer">
        TrustLens is a prototype. Scores are heuristic and should not be used
        as sole evidence for forensic decisions.
      </div>
    </div>
  );
}