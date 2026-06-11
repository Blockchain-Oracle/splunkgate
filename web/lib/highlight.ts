// JSON syntax-highlighter — emits <span class="tok-*"> spans the designer's CSS
// targets. The result is injected via `dangerouslySetInnerHTML` in `<CodeBlock>`.
//
// XSS safety contract (do NOT regress when adding new token types):
//   1. ESCAPE() runs FIRST on the JSON string, escaping `&`, `<`, `>`.
//   2. The token regex matches only on the escaped output and wraps matches in
//      `<span class="tok-*">…</span>`. No attribute interpolation, no href, no
//      style attribute — the only sink is the span class name, which is a
//      compile-time constant from this file.
// As long as both invariants hold, this function is XSS-safe for any input.
//
// The `TrustedHtml` brand is the contract the rest of the app reads from. Any
// HTML accepted by `CodeBlock.html` must either come out of this function or
// be a hand-written literal in TSX. New producers MUST escape their input the
// same way ESCAPE() does before assembling token spans.

// Brand the return type so consumers cannot pass arbitrary strings into
// `dangerouslySetInnerHTML` without an explicit cast. Casting is the audit
// trail — each call site that needs it spells out "this string is trusted".
export type TrustedHtml = string & { readonly __trustedHtml: unique symbol };

// The ONLY sanctioned way to brand a plain string as TrustedHtml. Use
// only at const declaration sites where the HTML is a compile-time literal
// authored by us (no template substitutions of runtime data). If you find
// yourself reaching for `trust()` in component code, escape the data first.
export const trust = (literal: string): TrustedHtml => literal as TrustedHtml;

const ESCAPE = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const TOKEN_RE =
  /("(?:\\.|[^\\"])*"(\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?)/g;

// Defensive serialization: `JSON.stringify` throws on circular refs and on
// BigInt; returns `undefined` for top-level functions / symbols. Either path
// crashes the React tree without an error boundary above DocsContent — and
// the consumers today (EXAMPLE_VERDICT, EXAMPLE_OTEL) are static, but the
// signature is `unknown`, so a future caller can hand us anything.
export function jsonHighlight(obj: unknown): TrustedHtml {
  let raw: string | undefined;
  try {
    raw = JSON.stringify(obj, null, 2);
  } catch (err) {
    console.error("[jsonHighlight] JSON.stringify failed:", err);
    const msg = err instanceof Error ? err.message : "unknown";
    return `<span class="tok-com">[unrenderable: ${ESCAPE(msg)}]</span>` as TrustedHtml;
  }
  if (raw === undefined) {
    return `<span class="tok-com">[no JSON output — top-level value not serializable]</span>` as TrustedHtml;
  }
  const json = ESCAPE(raw);
  const out = json.replace(TOKEN_RE, (m) => {
    let cls = "tok-num";
    if (/^"/.test(m)) cls = /:\s*$/.test(m) ? "tok-blue" : "tok-str";
    else if (/true|false|null/.test(m)) cls = "tok-kw";
    return `<span class="${cls}">${m}</span>`;
  });
  return out as TrustedHtml;
}
