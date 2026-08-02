import styles from "./ui.module.css";

type StatusTone = "success" | "warning" | "danger" | "neutral";

export function StatusIndicator({ label, tone = "neutral" }: Readonly<{ label: string; tone?: StatusTone }>) {
  return (
    <span className={`${styles.statusIndicator} ${styles[tone]}`} role="status">
      <span className={styles.statusDot} aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
