"use client";

import { useEffect, useState } from "react";

interface TickerOpts {
  step?: number;
  every?: number;
  spread?: number;
}

// Slowly-incrementing counter for "live" KPI numbers in the hero + dashboard
// mockups. Pure cosmetic — adds gentle entropy so the numbers feel alive.
//
// CAUTION (SSR safety): `Math.random()` MUST stay inside `useEffect`. With
// `output: "export"` Next.js renders this on the server during static
// generation; if the random call leaks into the render body the server-
// computed value won't match the client's first render and React 19 will
// throw a hydration mismatch. Initial state uses the static `start` so the
// server render and client first render agree.
//
// Also: callers MUST be `"use client"` components. The hook itself uses
// `setInterval` and DOM-only APIs.
export function useTicker(start: number, { step = 1, every = 2400, spread = 2 }: TickerOpts = {}) {
  const [n, setN] = useState(start);
  useEffect(() => {
    const id = setInterval(() => {
      setN((v) => v + step * (1 + Math.floor(Math.random() * spread)));
    }, every);
    return () => clearInterval(id);
  }, [step, every, spread]);
  return n;
}
