import styles from "./ui.module.css";

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: Readonly<{ label: string; htmlFor: string; hint?: string; children: React.ReactNode }>) {
  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel} htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint ? <p className={styles.fieldHint}>{hint}</p> : null}
    </div>
  );
}
