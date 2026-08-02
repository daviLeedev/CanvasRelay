import type { ButtonHTMLAttributes } from "react";

import { Tooltip } from "./Tooltip";
import styles from "./ui.module.css";

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
  label: string;
};

export function IconButton({ label, type = "button", ...props }: IconButtonProps) {
  return (
    <Tooltip label={label}>
      <button className={styles.iconButton} type={type} aria-label={label} {...props} />
    </Tooltip>
  );
}
