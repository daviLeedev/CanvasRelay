import { ImageIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell/AppShell";
import { HealthPanel } from "@/components/health/HealthPanel";

import styles from "./page.module.css";

export default function ImageWorkspacePage() {
  return (
    <AppShell>
      <div className={styles.workspace}>
        <section className={styles.stage} aria-labelledby="workspace-title">
          <header className={styles.stageHeader}>
            <div>
              <p className={styles.eyebrow}>Workspace</p>
              <h1 id="workspace-title">Image</h1>
            </div>
          </header>

          <div className={styles.emptyState} role="status">
            <ImageIcon aria-hidden="true" size={28} strokeWidth={1.5} />
            <span>No active generation</span>
          </div>
        </section>

        <aside className={styles.inspector} aria-label="System inspector">
          <HealthPanel />
        </aside>
      </div>
    </AppShell>
  );
}
