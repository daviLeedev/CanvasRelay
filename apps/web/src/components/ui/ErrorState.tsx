import { TriangleAlert } from "lucide-react";

import { Button } from "./Button";
import styles from "./ui.module.css";

export function ErrorState({
  title,
  message,
  retryLabel = "Try again",
  onRetry,
}: Readonly<{ title: string; message: string; retryLabel?: string; onRetry: () => void }>) {
  return (
    <section className={styles.errorState} role="alert">
      <div className={styles.errorContent}>
        <TriangleAlert className={styles.errorIcon} aria-hidden="true" size={28} />
        <h2>{title}</h2>
        <p>{message}</p>
        <Button variant="primary" onClick={onRetry}>
          {retryLabel}
        </Button>
      </div>
    </section>
  );
}
