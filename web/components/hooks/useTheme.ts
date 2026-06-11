"use client";

import { useEffect, useState } from "react";

export type Theme = "dark" | "paper";

const STORAGE_KEY = "sg-theme";

// Theme state with localStorage persistence under `sg-theme`. Default = dark
// (per designer's prototype). The page root reads this and applies
// `.theme-dark` / `.theme-paper` to drive the CSS token swap.
//
// localStorage is wrapped in try/catch because Safari Private (older versions),
// iOS Lockdown Mode, MDM policies, and quota-exceeded all throw on access.
// Without a guard, the useEffect callback throws synchronously and React 19
// renders the page blank — a marketing-site silent failure that beats the
// purpose of having a fallback theme at all. We degrade to "session-only"
// theming (toggle works in-page, doesn't persist across reload) and warn.
//
// The `mounted` flag skips the first persist write so a returning paper-theme
// user doesn't get their preference clobbered by the dark default during the
// initial render → first effect tick.
export function useTheme() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "dark" || stored === "paper") setTheme(stored);
    } catch {
      console.warn(
        `[useTheme] localStorage read failed — using default 'dark'. ` +
          `Theme will not persist this session (Safari Private / Lockdown / quota).`
      );
    }
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      console.warn("[useTheme] localStorage write failed — theme will not persist.");
    }
  }, [theme, mounted]);

  const toggle = () => setTheme((t) => (t === "dark" ? "paper" : "dark"));
  return { theme, toggle };
}
