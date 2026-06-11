"use client";

import { useState } from "react";
import Link from "next/link";
import { Brand } from "../shared/Brand";
import { SunIcon, MoonIcon } from "../shared/ThemeIcons";
import { AG_LINKS } from "@/lib/links";
import type { Theme } from "../hooks/useTheme";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";

interface TopNavProps {
  theme: Theme;
  onToggleTheme: () => void;
}

// Drawer items in order; reused on mobile so the user can still reach
// every section the inline nav hides at ≤720 px.
const DRAWER_LINKS: Array<{ href: string; label: string; external?: boolean }> = [
  { href: "#how", label: "How it works" },
  { href: "#surfaces", label: "Surfaces" },
  { href: "#path", label: "Verdict path" },
  { href: "#evidence", label: "Evidence" },
  { href: "#start", label: "Get started" },
];

export function TopNav({ theme, onToggleTheme }: TopNavProps) {
  const [menu, setMenu] = useState(false);
  const close = () => setMenu(false);
  useBodyScrollLock(menu);

  return (
    <>
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
            <button
              className="topnav-menu-btn"
              onClick={() => setMenu(true)}
              aria-label="Open menu"
              aria-expanded={menu}
            >
              ☰
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile drawer — always rendered so the slide-in transition runs.
          Hidden on ≥720 px by the CSS (display: none on .topnav-menu-btn). */}
      <div
        className={"topnav-drawer-scrim" + (menu ? " open" : "")}
        onClick={close}
        aria-hidden="true"
      />
      <aside className={"topnav-drawer" + (menu ? " open" : "")} aria-hidden={!menu}>
        <div className="topnav-drawer-head">
          <Brand size={20} />
          <button className="topnav-drawer-x" onClick={close} aria-label="Close menu">
            ✕
          </button>
        </div>
        {DRAWER_LINKS.map((l) => (
          <a key={l.href} href={l.href} onClick={close}>
            {l.label}
          </a>
        ))}
        <Link href="/docs" onClick={close}>Docs</Link>
        <a href={AG_LINKS.github} target="_blank" rel="noreferrer" onClick={close}>
          GitHub ↗
        </a>
        <a className="ag-btn" href="#start" onClick={close}>
          Install the Splunk app
        </a>
      </aside>
    </>
  );
}
