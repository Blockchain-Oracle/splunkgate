"use client";

import Link from "next/link";
import { Brand } from "../shared/Brand";
import { SunIcon, MoonIcon } from "../shared/ThemeIcons";
import { AG_LINKS } from "@/lib/links";
import type { Theme } from "../hooks/useTheme";

interface TopNavProps {
  theme: Theme;
  onToggleTheme: () => void;
}

export function TopNav({ theme, onToggleTheme }: TopNavProps) {
  return (
    <nav className="topnav">
      <div className="topnav-in">
        <Brand />
        <div className="topnav-right">
          <div className="topnav-links">
            <a className="nav-hide" href="#how">How it works</a>
            <a className="nav-hide" href="#surfaces">Surfaces</a>
            <a className="nav-hide" href="#evidence">Evidence</a>
            <Link href="/docs">Docs</Link>
            <a href={AG_LINKS.github} target="_blank" rel="noreferrer">GitHub</a>
          </div>
          <button
            className="theme-toggle"
            onClick={onToggleTheme}
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          </button>
          <a className="ag-btn ag-btn-sm" href="#start">Install</a>
        </div>
      </div>
    </nav>
  );
}
