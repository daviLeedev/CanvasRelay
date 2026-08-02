import { Activity } from "lucide-react";
import Link from "next/link";

import { StudioNavigation } from "./StudioNavigation";
import styles from "./AppShell.module.css";

function Brand() {
  return (
    <Link className={styles.brand} href="/image" aria-label="CanvasRelay image workspace">
      <span className={styles.brandMark} aria-hidden="true">
        CR
      </span>
      <span className={styles.brandName}>CanvasRelay</span>
    </Link>
  );
}

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Studio navigation">
        <div>
          <Brand />
          <StudioNavigation />
        </div>

        <div className={styles.sidebarStatus}>
          <Activity aria-hidden="true" size={16} />
          <span>Provider relay</span>
        </div>
      </aside>

      <header className={styles.mobileBar}>
        <Brand />
        <StudioNavigation mobile />
      </header>

      <main className={styles.main}>{children}</main>
    </div>
  );
}

export function WorkspaceLoading({ label }: Readonly<{ label: string }>) {
  return <div className={styles.workspaceLoading} role="status">{label}</div>;
}
