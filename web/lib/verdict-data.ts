// The canonical example Verdict — shown on the landing page (RealVerdict)
// and on the docs page (Verdict type section). Source of truth.

export const EXAMPLE_VERDICT = {
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
  surface: "mw_model",
  latency_ms: 213.4,
  agent_id: "support-agent-7f3a",
};

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
};
