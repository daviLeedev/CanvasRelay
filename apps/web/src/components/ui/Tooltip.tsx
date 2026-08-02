import { useId } from "react";

import styles from "./ui.module.css";

export function Tooltip({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  const tooltipId = useId();

  return (
    <span className={styles.tooltipRoot}>
      <span aria-describedby={tooltipId}>{children}</span>
      <span className={styles.tooltip} id={tooltipId} role="tooltip">
        {label}
      </span>
    </span>
  );
}
