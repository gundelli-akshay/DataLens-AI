/**
 * hooks/useHealthCheck.js
 *
 * Custom hook that polls the backend /health endpoint once on mount
 * and returns the current connection status.
 *
 * Returns: "checking" | "online" | "offline"
 */

import { useState, useEffect } from "react";
import { checkHealth } from "../services/api";

export function useHealthCheck() {
  const [status, setStatus] = useState("checking");

  useEffect(() => {
    let cancelled = false;

    async function ping() {
      try {
        await checkHealth();
        if (!cancelled) setStatus("online");
      } catch {
        if (!cancelled) setStatus("offline");
      }
    }

    ping();

    // Cleanup: don't update state if component unmounts before fetch resolves
    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}
