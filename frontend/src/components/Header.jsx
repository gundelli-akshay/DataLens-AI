import ApiStatus from "./ApiStatus";
import "./Header.css";

export default function Header({ apiStatus, user, onOpenAuth, onSignOut }) {
  const displayName = user?.full_name || user?.email?.split("@")[0] || "User";
  const initial = displayName.charAt(0).toUpperCase();

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

        <div className="header__actions">
          <ApiStatus status={apiStatus} />

          {user ? (
            <div className="header__user">
              <div className="header__avatar" title={user.email}>
                {initial}
              </div>
              <span className="header__user-name" title={user.email}>
                {displayName}
              </span>
              <button
                type="button"
                className="header__btn header__btn--signout"
                onClick={onSignOut}
                aria-label="Sign Out"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="header__btn header__btn--signin"
              onClick={onOpenAuth}
              aria-label="Sign In or Register"
            >
              Sign In
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
