// frontend/src/components/Results.js
import React from 'react';
import ScoreGauge from './ScoreGauge';

// ---------- helpers ----------

function riskColor(pct) {
  if (pct < 20) return '#10b981';   // green
  if (pct < 40) return '#84cc16';   // lime
  if (pct < 60) return '#f59e0b';   // amber
  if (pct < 80) return '#f97316';   // orange
  return '#ef4444';                 // red
}

function renderBold(text) {
  if (!text) return null;
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={i}>{p.slice(2, -2)}</strong>;
    }
    return <span key={i}>{p}</span>;
  });
}

function pickIcon(level) {
  const s = String(level || '').toLowerCase();
  if (s.includes('very') || s.includes('strong') || s.includes('heavily')) return '🚨';
  if (s.includes('elevated') || s.includes('mild') || s.includes('low') || s.includes('soft')) return '⚠️';
  if (s.includes('natural') || s.includes('balanced') || s.includes('typical') || s.includes('lossless')) return '✅';
  return 'ℹ️';
}

// ---------- sub-components ----------

function FileInfoCard({ info }) {
  if (!info) return null;
  return (
    <div className="card">
      <h3>Image Information</h3>
      <div className="kv-grid">
        <div className="kv"><span>Filename</span><b>{info.filename}</b></div>
        <div className="kv"><span>Format</span><b>{info.format}</b></div>
        <div className="kv"><span>Mode</span><b>{info.mode}</b></div>
        <div className="kv">
          <span>Original size</span>
          <b>{info.original_width} × {info.original_height} px</b>
        </div>
        <div className="kv">
          <span>Analysed at</span>
          <b>{info.analysis_width} × {info.analysis_height} px</b>
        </div>
        <div className="kv">
          <span>Resized</span>
          <b>{info.was_resized ? 'Yes (downscaled for analysis)' : 'No'}</b>
        </div>
      </div>
    </div>
  );
}

function Indicator({ feature }) {
  const pct = feature.risk * 100;
  const color = riskColor(pct);
  return (
    <div className="indicator">
      <div className="indicator-head">
        <span>{pickIcon(feature.level)} {labelFor(feature.key)}</span>
        <span className="pct">{pct.toFixed(1)}% risk</span>
      </div>
      <div className="bar">
        <div
          className="bar-fill"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}aa, ${color})`,
          }}
        />
      </div>
      <div className="indicator-detail">
        {feature.explanation}
      </div>
    </div>
  );
}

function labelFor(key) {
  const map = {
    noise: 'Noise / Grain',
    saturation: 'Saturation',
    contrast: 'Contrast',
    color_balance: 'Colour Balance',
    sharpness: 'Sharpness',
    texture: 'Texture',
    edges: 'Edge Density',
    skin_smoothing: 'Skin Smoothing',
  };
  return map[key] || key;
}

function SkinCard({ skin }) {
  if (!skin) return null;
  const isScored = skin.scored !== false;
  return (
    <div className="card">
      <h3>Skin Smoothing {isScored ? '' : '(not scored)'}</h3>
      <p className="card-sub">{skin.explanation}</p>
      {isScored && typeof skin.risk === 'number' && (
        <>
          <div className="bar" style={{ marginTop: 10 }}>
            <div
              className="bar-fill"
              style={{
                width: `${(skin.risk * 100).toFixed(1)}%`,
                background: `linear-gradient(90deg, ${riskColor(skin.risk * 100)}aa, ${riskColor(skin.risk * 100)})`,
              }}
            />
          </div>
          <div className="indicator-detail">
            Risk {(skin.risk * 100).toFixed(1)}% · Weight{' '}
            {(skin.weight * 100).toFixed(1)}%
          </div>
        </>
      )}
    </div>
  );
}

function CompressionCard({ jpeg }) {
  if (!jpeg) return null;
  return (
    <div className="card">
      <h3>Supporting · Compression</h3>
      <div className="kv-grid">
        <div className="kv"><span>Blockiness</span><b>{jpeg.value ?? 'n/a'}</b></div>
        <div className="kv"><span>Level</span><b>{jpeg.level}</b></div>
        <div className="kv">
          <span>Included in score</span>
          <b>{jpeg.scored ? 'Yes' : 'No (supporting only)'}</b>
        </div>
      </div>
      <p className="card-sub">{jpeg.explanation}</p>
    </div>
  );
}

function MetadataCard({ meta }) {
  if (!meta) return null;
  const fields = meta.exif_fields || {};
  const entries = Object.entries(fields).slice(0, 12); // cap display
  return (
    <div className="card">
      <h3>Supporting · Metadata</h3>
      <div className="kv-grid">
        <div className="kv"><span>Format</span><b>{meta.format || 'n/a'}</b></div>
        <div className="kv"><span>Has EXIF</span><b>{meta.has_exif ? 'Yes' : 'No'}</b></div>
        <div className="kv">
          <span>Editing software</span>
          <b>{meta.editing_software || 'Not detected'}</b>
        </div>
        <div className="kv">
          <span>Included in score</span>
          <b>No (supporting only)</b>
        </div>
      </div>
      {meta.notes && <p className="card-sub">{meta.notes}</p>}
      {entries.length > 0 && (
        <details className="exif-details">
          <summary>EXIF fields ({entries.length})</summary>
          <div className="kv-grid" style={{ marginTop: 10 }}>
            {entries.map(([k, v]) => (
              <div className="kv" key={k}>
                <span>{k}</span>
                <b>{String(v)}</b>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

// ---------- main component ----------

export default function Results({ data, previewUrl }) {
  const {
    trust_score,
    risk,
    verdict,
    formula,
    file_info,
    scored_features = [],
    skin_smoothing,
    jpeg_info,
    metadata_info,
    warnings = [],
  } = data || {};

  return (
    <div className="results fade-in">
      {/* -------- top row: preview + score -------- */}
      <div className="results-top">
        <div className="results-image">
          <img src={previewUrl} alt="uploaded" className="preview-img" />
        </div>

        <div className="results-score">
          <ScoreGauge score={trust_score} />
          <div className="verdict">{verdict}</div>
          <div className="formula">R = {risk?.toFixed(4)}</div>
          {formula && <div className="formula-line">{formula}</div>}
        </div>
      </div>

      {/* -------- warnings -------- */}
      {warnings.length > 0 && (
        <div className="warn-box">
          <b>Notes during analysis:</b>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* -------- file info -------- */}
      <FileInfoCard info={file_info} />

      {/* -------- scored features -------- */}
      <div className="card">
        <h3>Feature Analysis</h3>
        <p className="card-sub">
          The following features contributed to the Trust Score. Higher risk
          indicates stronger evidence of filtering or editing.
        </p>
        <div className="indicators">
          {scored_features.length === 0 && (
            <p className="empty">No scored features were returned.</p>
          )}
          {scored_features.map((f) => (
            <Indicator key={f.key} feature={f} />
          ))}
        </div>
      </div>

      {/* -------- skin smoothing (may be support or scored) -------- */}
      <SkinCard skin={skin_smoothing} />

      {/* -------- supporting sections -------- */}
      <CompressionCard jpeg={jpeg_info} />
      <MetadataCard meta={metadata_info} />

      {/* -------- disclaimer -------- */}
      <div className="disclaimer">
        <strong>Disclaimer:</strong>{' '}
        TrustLens provides an estimated analysis based on selected image
        characteristics. Its results do not guarantee whether an image is
        original or edited. Lighting, camera quality, compression, resizing
        and natural image variations may influence the results.
      </div>

      {/* -------- hidden details for auditors -------- */}
      <details className="audit-details">
        <summary>Show technical breakdown</summary>
        <div className="kv-grid" style={{ marginTop: 10 }}>
          <div className="kv">
            <span>Weighted risk (R)</span>
            <b>{risk?.toFixed(4)}</b>
          </div>
          <div className="kv">
            <span>Trust Score (T)</span>
            <b>{trust_score?.toFixed(2)}</b>
          </div>
          <div className="kv">
            <span>Formula</span>
            <b>{formula}</b>
          </div>
          <div className="kv">
            <span>Scored features</span>
            <b>{scored_features.length}</b>
          </div>
        </div>
      </details>
    </div>
  );
}