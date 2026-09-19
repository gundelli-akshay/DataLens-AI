import ApiStatus from "./ApiStatus";
import "./Header.css";

export default function Header({ apiStatus }) {
  return (
    <header className="header">
      <div className="header__inner">
        <div className="header__brand">
          <div className="header__logo" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
              <rect width="28" height="28" rx="8" fill="url(#logoGrad)" />
              <path d="M7 14 L14 7 L21 14 L14 21 Z" fill="white" opacity="0.9" />
              <circle cx="14" cy="14" r="3" fill="white" />
              <defs>
                <linearGradient id="logoGrad" x1="0" y1="0" x2="28" y2="28">
                  <stop offset="0%" stopColor="#6366f1" />
                  <stop offset="100%" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <span className="header__name">DataLens AI</span>
        </div>
        <ApiStatus status={apiStatus} />
      </div>
    </header>
  );
}
