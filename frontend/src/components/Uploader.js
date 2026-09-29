import React, { useRef, useState } from 'react';

export default function Uploader({ onFile, onAnalyze, loading, hasFile }) {
  const inputRef = useRef(null);
  const [drag, setDrag] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith('image/')) onFile(f);
  };

  return (
    <>
      <div
        className={`upload-zone ${drag ? 'drag' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={handleDrop}
      >
        <div className="icon">🖼️</div>
        <h3>Drop an image or click to upload</h3>
        <p>JPG · PNG · WEBP · BMP · TIFF — up to 15 MB</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        />
      </div>
      {hasFile && (
        <div className="row">
          <button
            className="btn btn-primary"
            onClick={onAnalyze}
            disabled={loading}
          >
            {loading ? 'Analyzing…' : '⚡ Analyze Trust Score'}
          </button>
        </div>
      )}
    </>
  );
}