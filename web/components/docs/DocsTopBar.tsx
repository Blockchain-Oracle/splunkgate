"use client";

import Link from "next/link";
import { Shield } from "../shared/Shield";
import { SunIcon, MoonIcon } from "../shared/ThemeIcons";
import { AG_LINKS } from "@/lib/links";
import type { Theme } from "../hooks/useTheme";

interface DocsTopBarProps {
  theme: Theme;
  onToggleTheme: () => void;
  onOpenMenu: () => void;
}

export function DocsTopBar({ theme, onToggleTheme, onOpenMenu }: DocsTopBarProps) {
  return (
    <header className="docs-top">
      <div className="docs-top-in">
        <div className="docs-top-l">
          <button className="docs-menu-btn" onClick={onOpenMenu} aria-label="Open menu">
            ☰ Menu
          </button>
          <Link href="/" className="ag-brand" style={{ textDecoration: "none" }}>
            <Shield size={20} />
            <span className="ag-wordmark">SplunkGate</span>
          </Link>
          <span className="docs-badge">Docs</span>
        </div>
        <div className="docs-top-r">
          <Link href="/" aria-label="Back to site">
            ←<span className="docs-back-label"> Back to site</span>
          </Link>
          <a href={AG_LINKS.github} target="_blank" rel="noreferrer">GitHub</a>
          <button
            className="theme-toggle"
            onClick={onToggleTheme}
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    </header>
  );
}
