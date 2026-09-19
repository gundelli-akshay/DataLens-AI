import "./ApiStatus.css";

const STATUS_CONFIG = {
  checking: { label: "Connecting…", className: "api-status--checking" },
  online:   { label: "API Online",  className: "api-status--online"   },
  offline:  { label: "API Offline", className: "api-status--offline"  },
};

export default function ApiStatus({ status }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.checking;

  return (
    <div className={`api-status ${config.className}`} role="status" aria-live="polite">
      <span className="api-status__dot" aria-hidden="true" />
      <span className="api-status__label">{config.label}</span>
    </div>
  );
}
