import React from 'react';

export default function ScoreGauge({ score }) {
  const radius = 90;
  const stroke = 14;
  const circumference = 2 * Math.PI * radius;
  const dash = (score / 100) * circumference;
  const gap = circumference - dash;

  let color = '#10b981';
  if (score < 80) color = '#84cc16';
  if (score < 60) color = '#f59e0b';
  if (score < 40) color = '#f97316';
  if (score < 20) color = '#ef4444';

  return (
    <div className="gauge-wrap">
      <div className="gauge">
        <svg width="220" height="220">
          <circle
            cx="110" cy="110" r={radius}
            stroke="rgba(255,255,255,0.08)" strokeWidth={stroke}
            fill="transparent"
          />
          <circle
            cx="110" cy="110" r={radius}
            stroke={color} strokeWidth={stroke}
            fill="transparent"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${gap}`}
            style={{ transition: 'stroke-dasharray 1s cubic-bezier(.2,.9,.3,1)' }}
          />
        </svg>
        <div className="score-num">
          <div>
            <div className="value" style={{ color }}>{score}</div>
            <div className="label">Trust Score</div>
          </div>
        </div>
      </div>
    </div>
  );
}