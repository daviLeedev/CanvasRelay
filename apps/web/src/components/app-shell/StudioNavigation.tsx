"use client";

import { ImagePlus, Images, PanelsTopLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./AppShell.module.css";

const destinations = [
  { href: "/image", label: "Image studio", icon: PanelsTopLeft },
  { href: "/edit", label: "Image edit", icon: ImagePlus },
  { href: "/library", label: "Library", icon: Images },
] as const;

export function StudioNavigation({ mobile = false }: Readonly<{ mobile?: boolean }>) {
  const pathname = usePathname();
  return (
    <nav className={mobile ? styles.mobileNavigation : styles.navigation} aria-label="Primary navigation">
      {destinations.map((destination) => {
        const Icon = destination.icon;
        return (
          <Link
            className={mobile ? styles.mobileNavItem : styles.navItem}
            href={destination.href}
            aria-current={pathname === destination.href ? "page" : undefined}
            key={destination.href}
          >
            <Icon aria-hidden="true" size={19} />
            <span className={mobile ? styles.visuallyHidden : undefined}>{destination.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
