// The canonical example Verdict — shown on the landing page (RealVerdict)
// and on the docs page (Verdict type section). Source of truth.
//
// Pinned to the field set of `packages/splunkgate_core/src/splunkgate_core/verdict.py`:
// the dict below must round-trip through `Verdict.model_validate` (frozen pydantic,
// `extra="forbid"`). The `modifications` field has no default and would reject the
// dict if omitted — ADR-003 / story-mw-04. The string-literal types here mirror
// `RuleHit.source` which is itself a `Literal["ai_defense", "defenseclaw_regex",
// "splunklib_security"]` — Foundation-Sec is structurally excluded from this enum.

export type ExampleVerdict = {
  readonly trace_id: string;
  readonly timestamp: string;
  readonly verdict: "ALLOW" | "BLOCK" | "MODIFY" | "REVIEW";
  readonly severity: "NONE" | "LOW" | "MEDIUM" | "HIGH";
  readonly rules: ReadonlyArray<{
    readonly rule: string;
    readonly confidence: number;
    readonly source: "ai_defense" | "defenseclaw_regex" | "splunklib_security";
  }>;
  readonly explanation: string;
  readonly classifications: ReadonlyArray<string>;
  readonly modifications: Record<string, unknown> | null;
  readonly surface: string;
  readonly latency_ms: number;
  readonly agent_id: string;
};

export const EXAMPLE_VERDICT: ExampleVerdict = {
  trace_id: "9f3c2a17-4e8b-4c1a-9d2e-7b1f0a3c5e6a",
  timestamp: "2026-06-08T14:03:21.118Z",
  verdict: "BLOCK",
  severity: "HIGH",
  rules: [
    { rule: "Prompt Injection", confidence: 1.0, source: "splunklib_security" },
    { rule: "Prompt Injection", confidence: 0.97, source: "ai_defense" },
  ],
  explanation:
    "Multi-step instruction-injection attempting to exfiltrate customer PII via the email tool",
  classifications: ["SECURITY_VIOLATION"],
  modifications: null,
  surface: "mw_model",
  latency_ms: 213.4,
  agent_id: "support-agent-7f3a",
} as const;

export const EXAMPLE_OTEL = {
  "event.name": "gen_ai.evaluation.result",
  "gen_ai.evaluation.name": "splunkgate.safety_verdict",
  "gen_ai.evaluation.score.value": 1.0,
  "gen_ai.evaluation.score.label": "block",
  "gen_ai.evaluation.explanation": "Multi-step instruction-injection…",
  "splunkgate.surface": "mw_model",
  "splunkgate.rules": ["Prompt Injection"],
  "splunkgate.trace_id": "9f3c2a17-4e8b-4c1a-9d2e-7b1f0a3c5e6a",
  "splunkgate.agent_id": "support-agent-7f3a",
} as const;
