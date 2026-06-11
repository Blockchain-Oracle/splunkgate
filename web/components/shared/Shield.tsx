"use client";

import { useId } from "react";

// Brand glyph — a ">" chevron meeting a gate post. Splunk-flavoured signal:
// gradient stroke (orange→magenta) unless a solid `fill` is provided.
//
// Gradient id comes from `useId()` so multiple Shields in the same SSR tree
// don't share a `<linearGradient id>` — React 19 guarantees the id is
// stable across server and client renders, so no hydration mismatch.

interface ShieldProps {
  size?: number;
  fill?: string;
}

export function Shield({ size = 22, fill }: ShieldProps) {
  const gid = `sgGrad-${useId()}`;
  const stroke = fill ?? `url(#${gid})`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      style={{ display: "block", flex: "0 0 auto" }}
    >
      {!fill && (
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#F99D1C" />
            <stop offset="1" stopColor="#ED0080" />
          </linearGradient>
        </defs>
      )}
      <path
        d="M13 11 L25.5 24 L13 37"
        stroke={stroke}
        strokeWidth="5.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M34 10 L34 38" stroke={stroke} strokeWidth="5.4" strokeLinecap="round" />
    </svg>
  );
}
