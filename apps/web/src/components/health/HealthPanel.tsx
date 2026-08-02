"use client";

import { RefreshCw, Server } from "lucide-react";

import { IconButton } from "@/components/ui/IconButton";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import { useHealthQuery } from "@/lib/api/useHealthQuery";

import styles from "./HealthPanel.module.css";

export function HealthPanel() {
  const healthQuery = useHealthQuery();
  const isChecking = healthQuery.isPending || healthQuery.isFetching;

  return (
    <section className={styles.panel} aria-labelledby="health-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Server aria-hidden="true" size={18} />
          <h2 id="health-title">API details</h2>
        </div>

        <IconButton
          label="Check API connection again"
          onClick={() => void healthQuery.refetch()}
          disabled={isChecking}
        >
          <RefreshCw aria-hidden="true" size={16} />
        </IconButton>
      </header>

      <div className={styles.status} aria-live="polite">
        {isChecking ? (
          <div>
            <StatusIndicator label="Checking connection" tone="warning" />
            <p>Waiting for the local API health response.</p>
          </div>
        ) : null}

        {healthQuery.isSuccess && !isChecking ? (
          <div>
            <StatusIndicator label="Connected" tone="success" />
            <p>
              {healthQuery.data.service} - v{healthQuery.data.version}
            </p>
          </div>
        ) : null}

        {healthQuery.isError && !isChecking ? (
          <div>
            <StatusIndicator label="API unavailable" tone="danger" />
            <p>Start the local API service, then check the connection again.</p>
          </div>
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
