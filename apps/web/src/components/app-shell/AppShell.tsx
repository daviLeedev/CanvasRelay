import { Activity, ImageIcon } from "lucide-react";
import Link from "next/link";

import styles from "./AppShell.module.css";

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <Link className={styles.brand} href="/image" aria-label="CanvasRelay image workspace">
          <span className={styles.brandMark} aria-hidden="true">
            CR
          </span>
          <span>CanvasRelay</span>
        </Link>

        <span className={styles.releaseLabel}>Foundation</span>
      </header>

      <aside className={styles.sidebar}>
        <nav aria-label="Primary navigation">
          <Link className={styles.navItem} href="/image" aria-current="page">
            <ImageIcon aria-hidden="true" size={18} />
            <span>Image</span>
          </Link>
        </nav>

        <div className={styles.sidebarStatus}>
          <Activity aria-hidden="true" size={16} />
          <span>Studio foundation</span>
        </div>
      </aside>

      <main className={styles.main}>{children}</main>
    </div>
  );
}
