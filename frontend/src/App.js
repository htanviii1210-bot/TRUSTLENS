// frontend/src/App.js
import React, { useState } from 'react';
import axios from 'axios';
import Uploader from './components/Uploader';
import Results from './components/Results';

const API = process.env.REACT_APP_API || 'http://localhost:8000';

// Client-side validation mirrors the backend, for instant feedback
const ALLOWED_TYPES = ['image/jpeg', 'image/jpg', 'image/png'];
const MAX_BYTES = 15 * 1024 * 1024;

function Logo() {
  return (
    <div className="logo">
      <svg viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2L4 6v6c0 5 3.5 9 8 10 4.5-1 8-5 8-10V6l-8-4z"
          stroke="white" strokeWidth="2" strokeLinejoin="round"
        />
        <path
          d="M9 12l2 2 4-4" stroke="white" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round"
        />
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
    setError(null);
    setResult(null);

    if (!ALLOWED_TYPES.includes(f.type)) {
      setError('Unsupported file type. Please upload a JPG or PNG image.');
      return;
    }
    if (f.size > MAX_BYTES) {
      setError('File is too large. Maximum allowed size is 15 MB.');
      return;
    }

    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const analyze = async () => {
    if (!file || loading) return;
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
      const detail = e?.response?.data?.detail;
      const msg =
        (detail && (detail.message || detail)) ||
        e.message ||
        'Analysis failed.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    if (preview) URL.revokeObjectURL(preview);
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
        <div className="nav-tag">v2.0 · Rule-based Analysis</div>
      </div>

      <div className="hero">
        <h1>Detect filters. Reveal authenticity.</h1>
        <p>
          Upload an image and TrustLens will analyse its noise, colour,
          texture, edges, and metadata to produce an explainable Trust Score.
        </p>
        <div className="badge-row">
          <span className="badge">Noise</span>
          <span className="badge">Saturation</span>
          <span className="badge">Contrast</span>
          <span className="badge">Colour Balance</span>
          <span className="badge">Sharpness</span>
          <span className="badge">Texture</span>
          <span className="badge">Edge Density</span>
          <span className="badge">Skin Smoothing</span>
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
              <div className="preview-single">
                <img src={preview} alt="upload preview" className="preview-img" />
                <div className="file-chip">
                  <strong>{file?.name}</strong>
                  <span> · {(file.size / 1024).toFixed(0)} KB</span>
                </div>
                <div className="row">
                  <button className="btn btn-ghost" onClick={reset}>
                    Remove image
                  </button>
                  <button className="btn btn-ghost" onClick={() => document.getElementById('tl-replace')?.click()}>
                    Replace image
                  </button>
                  <input
                    id="tl-replace"
                    type="file"
                    accept="image/jpeg,image/png"
                    style={{ display: 'none' }}
                    onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                  />
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
                ← Analyse another image
              </button>
            </div>
          </>
        )}
      </div>

      <div className="footer">
        TrustLens provides an estimated analysis based on selected image
        characteristics. Its results do not guarantee whether an image is
        original or edited.
      </div>
    </div>
  );
}