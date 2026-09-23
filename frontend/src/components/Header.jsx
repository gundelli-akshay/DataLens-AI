import { useState, useRef, useEffect } from "react";
import ApiStatus from "./ApiStatus";
import "./Header.css";

export default function Header({
  apiStatus,
  user,
  onNavigate,
  onOpenAuth,
  onOpenUserMenu,
  onSignOut,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  const displayName = user?.full_name || user?.email || "User";
  const initial = displayName.charAt(0).toUpperCase();

  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    }

    function handleKeyDown(e) {
      if (e.key === "Escape") {
        setMenuOpen(false);
      }
    }

    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  function handleMenuSelect(tab) {
    setMenuOpen(false);
    onOpenUserMenu?.(tab);
  }

  function handleSignOutClick() {
    setMenuOpen(false);
    onSignOut?.();
  }

  return (
    <header className="header">
      <div className="header__inner">
        <div className="header__brand">
          <a
            href="/"
            className="header__brand-link"
            onClick={(e) => {
              e.preventDefault();
              onNavigate?.("/");
            }}
            aria-label="DataLens AI Home"
          >
            <div className="header__logo">
              <svg
                width="28"
                height="28"
                viewBox="0 0 28 28"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
              >
                <rect width="28" height="28" rx="6" fill="#0284c7" />
                <path
                  d="M7 14L12 9L17 14L22 9"
                  stroke="white"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M7 19L12 14L17 19L22 14"
                  stroke="#bae6fd"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="header__name">DataLens AI</span>
          </a>
        </div>

        <div className="header__actions">
          <ApiStatus status={apiStatus} />

          {user ? (
            <div className="header__user-wrapper" ref={menuRef}>
              <button
                type="button"
                className={`header__user-btn ${menuOpen ? "header__user-btn--active" : ""}`}
                onClick={() => setMenuOpen(!menuOpen)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                aria-label={`User menu for ${displayName}`}
              >
                <div className="header__avatar" title={user.email}>
                  {initial}
                </div>
                <span className="header__user-name" title={user.email}>
                  {displayName}
                </span>
                <svg
                  className={`header__chevron ${menuOpen ? "header__chevron--open" : ""}`}
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              {menuOpen && (
                <div className="header__dropdown-menu" role="menu">
                  <div className="header__dropdown-header">
                    <span className="header__dropdown-email" title={user.email}>
                      {user.email}
                    </span>
                  </div>

                  <button
                    type="button"
                    className="header__dropdown-item"
                    role="menuitem"
                    onClick={() => handleMenuSelect("profile")}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                    Account
                  </button>

                  <button
                    type="button"
                    className="header__dropdown-item"
                    role="menuitem"
                    onClick={() => handleMenuSelect("history")}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                    History &amp; Files
                  </button>

                  <div className="header__dropdown-divider" />

                  <button
                    type="button"
                    className="header__dropdown-item header__dropdown-item--signout"
                    role="menuitem"
                    onClick={handleSignOutClick}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                      <polyline points="16 17 21 12 16 7" />
                      <line x1="21" y1="12" x2="9" y2="12" />
                    </svg>
                    Sign Out
                  </button>
                </div>
              )}
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
