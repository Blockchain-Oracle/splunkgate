"use client";

import { useState } from "react";
import type { TrustedHtml } from "@/lib/highlight";

interface CodeBlockProps {
  name: string;
  // Highlighted HTML (tok-* spans). Branded as TrustedHtml — the only producer
  // is `jsonHighlight()` (which escapes its input) or hand-written literals
  // in TSX files. Never accept this prop from runtime/user data without
  // routing through the highlighter.
  html: TrustedHtml;
  // Optional clipboard text; falls back to a stripped-tags version of `html`.
  plain?: string;
}

type CopyState = "idle" | "copied" | "error";

// Code copy is the single most aggravating UX bug on docs sites — if the
// clipboard write silently fails (no HTTPS, blocked permission, doc not
// focused), the user pastes whatever was in their clipboard 10 minutes ago
// and blames us. So we surface every failure both to the developer
// (console.warn) and to the user (visible "copy failed" label).
export function CodeBlock({ name, html, plain }: CodeBlockProps) {
  const [state, setState] = useState<CopyState>("idle");

  const copy = async () => {
    const text = plain ?? html.replace(/<[^>]+>/g, "");
    if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
      console.warn("[CodeBlock] navigator.clipboard unavailable — select text manually");
      setState("error");
      setTimeout(() => setState("idle"), 2400);
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
      setTimeout(() => setState("idle"), 1400);
    } catch (err) {
      console.warn("[CodeBlock] clipboard write failed:", err);
      setState("error");
      setTimeout(() => setState("idle"), 2400);
    }
  };

  const label =
    state === "copied" ? "✓ copied" : state === "error" ? "✗ copy failed" : "copy";
  const className = `code-copy ${state === "copied" ? "copied" : ""} ${state === "error" ? "errored" : ""}`.trim();

  return (
    <div className="code">
      <div className="code-bar">
        <span className="code-name">{name}</span>
        <button className={className} onClick={copy} aria-live="polite">
          {label}
        </button>
      </div>
      <pre>
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}
