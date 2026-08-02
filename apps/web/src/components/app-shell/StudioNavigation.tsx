"use client";

import { ImagePlus, Images, ListChecks, PanelsTopLeft, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./AppShell.module.css";

const destinations = [
  { href: "/image", label: "Image studio", icon: PanelsTopLeft },
  { href: "/edit", label: "Image edit", icon: ImagePlus },
  { href: "/gpt-image", label: "GPT image", icon: Sparkles },
  { href: "/jobs", label: "Job center", icon: ListChecks },
  { href: "/library", label: "Library", icon: Images },
  { href: "/settings", label: "Settings", icon: Settings },
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
