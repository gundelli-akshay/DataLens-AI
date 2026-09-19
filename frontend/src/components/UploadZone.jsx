import "./UploadZone.css";

const SUPPORTED_FORMATS = [
  { ext: "CSV",  description: "Spreadsheet data",   color: "#34d399" },
  { ext: "XLSX", description: "Excel workbook",      color: "#60a5fa" },
  { ext: "PDF",  description: "PDF document",        color: "#f87171" },
  { ext: "DOCX", description: "Word document",       color: "#a78bfa" },
];

export default function UploadZone() {
  return (
    <section className="upload-zone" aria-label="File upload area">
      <div className="upload-zone__droparea">
        <div className="upload-zone__icon" aria-hidden="true">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="24" fill="rgba(99,102,241,0.12)" />
            <path
              d="M24 32V20M24 20L19 25M24 20L29 25"
              stroke="#818cf8"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M16 33h16"
              stroke="#818cf8"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.5"
            />
          </svg>
        </div>

        <div className="upload-zone__text">
          <p className="upload-zone__primary">Drop your file here</p>
          <p className="upload-zone__secondary">
            or{" "}
            <span className="upload-zone__browse" role="button" tabIndex={0}>
              browse to upload
            </span>
          </p>
        </div>

        <div className="upload-zone__coming-soon">
          File upload — coming in the next step
        </div>
      </div>

      <div className="upload-zone__formats" role="list" aria-label="Supported file formats">
        {SUPPORTED_FORMATS.map(({ ext, description, color }) => (
          <div
            key={ext}
            className="format-badge"
            role="listitem"
            style={{ "--badge-color": color }}
            title={description}
          >
            <span className="format-badge__dot" aria-hidden="true" />
            <span className="format-badge__ext">{ext}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
