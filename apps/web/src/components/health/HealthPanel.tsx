"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, Server, TriangleAlert } from "lucide-react";

import { fetchHealth } from "@/lib/api/health";

import styles from "./HealthPanel.module.css";

export function HealthPanel() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => fetchHealth(signal),
    staleTime: 30_000,
  });

  const isChecking = healthQuery.isPending || healthQuery.isFetching;

  return (
    <section className={styles.panel} aria-labelledby="health-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Server aria-hidden="true" size={18} />
          <h2 id="health-title">API status</h2>
        </div>

        <button
          className={styles.retryButton}
          type="button"
          onClick={() => void healthQuery.refetch()}
          disabled={isChecking}
          aria-label="Check API connection again"
          title="Check again"
        >
          <RefreshCw aria-hidden="true" size={16} />
        </button>
      </header>

      <div className={styles.status} role="status" aria-live="polite">
        {isChecking ? (
          <>
            <span className={`${styles.indicator} ${styles.checking}`} aria-hidden="true" />
            <div>
              <strong>Checking connection</strong>
              <p>Waiting for the API health response.</p>
            </div>
          </>
        ) : null}

        {healthQuery.isSuccess && !isChecking ? (
          <>
            <CheckCircle2 className={styles.connectedIcon} aria-hidden="true" size={18} />
            <div>
              <strong>Connected</strong>
              <p>
                {healthQuery.data.service} - v{healthQuery.data.version}
              </p>
            </div>
          </>
        ) : null}

        {healthQuery.isError && !isChecking ? (
          <>
            <TriangleAlert className={styles.errorIcon} aria-hidden="true" size={18} />
            <div>
              <strong>API unavailable</strong>
              <p>Start the API server, then check the connection again.</p>
            </div>
          </>
        ) : null}
      </div>

      {healthQuery.isSuccess ? (
        <dl className={styles.details}>
          <div>
            <dt>Profile</dt>
            <dd>{healthQuery.data.demoMode ? "Demo" : "Configured"}</dd>
          </div>
          <div>
            <dt>Service</dt>
            <dd>{healthQuery.data.status}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
