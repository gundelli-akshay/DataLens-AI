import { useState, useEffect, useRef } from "react";
import { login, signup, loginWithGoogle } from "../services/api";
import "./AuthModal.css";

export default function AuthModal({ isOpen, onClose, onSuccess }) {
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const googleBtnRef = useRef(null);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setErrorMsg("");
      setEmail("");
      setPassword("");
      setFullName("");
    }
  }, [isOpen, mode]);

  // Google Identity Services integration
  useEffect(() => {
    if (!isOpen) return;

    if (window.google?.accounts?.id && googleBtnRef.current) {
      try {
        window.google.accounts.id.initialize({
          client_id: "mock-google-client-id.apps.googleusercontent.com",
          callback: async (response) => {
            if (response?.credential) {
              setLoading(true);
              setErrorMsg("");
              try {
                const res = await loginWithGoogle(response.credential);
                onSuccess(res.user);
                onClose();
              } catch (err) {
                setErrorMsg(err.message || "Google Sign-In failed.");
              } finally {
                setLoading(false);
              }
            }
          },
        });

        window.google.accounts.id.renderButton(googleBtnRef.current, {
          theme: "outline",
          size: "large",
          width: "100%",
          text: "continue_with",
          shape: "rectangular",
        });
      } catch (err) {
        console.warn("GSI initialization skipped/unavailable:", err);
      }
    }
  }, [isOpen, mode]);

  if (!isOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) {
      setErrorMsg("Please enter both email and password.");
      return;
    }
    if (mode === "signup" && password.length < 6) {
      setErrorMsg("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);
    setErrorMsg("");
    try {
      let res;
      if (mode === "login") {
        res = await login({ email, password });
      } else {
        res = await signup({ email, password, fullName });
      }
      onSuccess(res.user);
      onClose();
    } catch (err) {
      setErrorMsg(err.message || "Authentication failed. Please check your details.");
    } finally {
      setLoading(false);
    }
  }

  // Fallback Google login click handler
  async function handleCustomGoogleClick() {
    if (window.google?.accounts?.id) {
      window.google.accounts.id.prompt();
    } else {
      setErrorMsg("Google Sign-In is initializing. Please try again or use Email/Password.");
    }
  }

  return (
    <div className="auth-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="auth-card" onClick={(e) => e.stopPropagation()}>
        {/* Close Button */}
        <button className="auth-close" onClick={onClose} aria-label="Close modal">
          &times;
        </button>

        {/* Header */}
        <div className="auth-header">
          <div className="auth-logo-badge">
            <span className="auth-badge-dot"></span>
            DataLens AI
          </div>
          <h2 className="auth-title">
            {mode === "login" ? "Welcome back" : "Create an account"}
          </h2>
          <p className="auth-subtitle">
            {mode === "login"
              ? "Sign in to access your documents and chat history"
              : "Sign up to start analyzing files and chatting with AI"}
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            className={`auth-tab ${mode === "login" ? "active" : ""}`}
            onClick={() => setMode("login")}
            role="tab"
            aria-selected={mode === "login"}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab ${mode === "signup" ? "active" : ""}`}
            onClick={() => setMode("signup")}
            role="tab"
            aria-selected={mode === "signup"}
          >
            Sign Up
          </button>
        </div>

        {/* Error Notice */}
        {errorMsg && (
          <div className="auth-error-notice" role="alert">
            <span className="auth-error-icon">!</span>
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Email/Password Form */}
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "signup" && (
            <div className="auth-field">
              <label htmlFor="auth-name">Full Name</label>
              <input
                id="auth-name"
                type="text"
                placeholder="Jane Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
              />
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="auth-email">Email Address</label>
            <input
              id="auth-email"
              type="email"
              required
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              required
              placeholder="At least 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </div>

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <span className="auth-spinner"></span>
            ) : mode === "login" ? (
              "Sign In"
            ) : (
              "Create Account"
            )}
          </button>
        </form>

        {/* Divider */}
        <div className="auth-divider">
          <span>OR</span>
        </div>

        {/* Google Sign-In Container */}
        <div className="auth-google-container">
          <div ref={googleBtnRef} className="auth-gsi-wrapper"></div>
          {/* Custom fallback Google button */}
          <button
            type="button"
            className="auth-google-fallback-btn"
            onClick={handleCustomGoogleClick}
            disabled={loading}
          >
            <svg className="google-icon" viewBox="0 0 24 24" width="18" height="18">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
              />
            </svg>
            Continue with Google
          </button>
        </div>
      </div>
    </div>
  );
}
