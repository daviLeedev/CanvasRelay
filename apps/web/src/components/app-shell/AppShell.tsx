import { Activity, ImageIcon, PanelsTopLeft } from "lucide-react";
import Link from "next/link";

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
          <nav className={styles.navigation} aria-label="Primary navigation">
            <Link className={styles.navItem} href="/image" aria-current="page">
              <ImageIcon aria-hidden="true" size={19} />
              <span>Image studio</span>
            </Link>
          </nav>
        </div>

        <div className={styles.sidebarStatus}>
          <Activity aria-hidden="true" size={16} />
          <span>Demo workspace</span>
        </div>
      </aside>

      <header className={styles.mobileBar}>
        <Brand />
        <nav aria-label="Mobile navigation">
          <Link className={styles.mobileNavItem} href="/image" aria-current="page">
            <PanelsTopLeft aria-hidden="true" size={19} />
            <span className={styles.visuallyHidden}>Image studio</span>
          </Link>
        </nav>
      </header>

      <main className={styles.main}>{children}</main>
    </div>
  );
}
