import React from 'react';
import ScoreGauge from './ScoreGauge';

function riskColor(pct) {
  if (pct < 20) return '#10b981';
  if (pct < 40) return '#84cc16';
  if (pct < 60) return '#f59e0b';
  if (pct < 80) return '#f97316';
  return '#ef4444';
}

function renderBold(text) {
  // Very small markdown: **bold**
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={i}>{p.slice(2, -2)}</strong>;
    }
    return <span key={i}>{p}</span>;
  });
}

export default function Results({ data, previewUrl }) {
  const { trust_score, verdict, indicators, explanation } = data;

  return (
    <div className="preview-wrap two-col fade-in">
      <div>
        <img src={previewUrl} alt="upload preview" className="preview-img" />
        <div style={{ marginTop: 20 }}>
          <ScoreGauge score={trust_score} />
          <div style={{ textAlign: 'center' }}>
            <div className="verdict">{verdict}</div>
          </div>
        </div>
      </div>

      <div>
        <h3 style={{ marginBottom: 6 }}>Forensic Indicators</h3>
        <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 8 }}>
          Higher % = stronger evidence of filtering or editing.
        </p>
        <div className="indicators">
          {indicators.map((ind) => (
            <div key={ind.key} className="indicator">
              <div className="indicator-head">
                <span>{ind.label}</span>
                <span className="pct">{ind.risk_percent}% risk</span>
              </div>
              <div className="bar">
                <div
                  className="bar-fill"
                  style={{
                    width: `${ind.risk_percent}%`,
                    background: `linear-gradient(90deg, ${riskColor(ind.risk_percent)}aa, ${riskColor(ind.risk_percent)})`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        <h3 style={{ marginTop: 32, marginBottom: 12 }}>Explanation</h3>
        <div className="explanation">
          <div className="summary">{renderBold(explanation.summary)}</div>
          <div className="bullets">
            {explanation.bullets.map((b, i) => (
              <div className="bullet" key={i}>{renderBold(b)}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
