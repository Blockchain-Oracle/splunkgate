# Aegis

> Runtime safety net for AI agents deployed in Splunk + Cisco enterprise environments. Built for the Splunk Agentic Ops Hackathon (Devpost, deadline Jun 15 2026).

## Status

**Spec phase.** No code yet. All specifications live in `docs/`. Reference architecture in `../research/splunk-agentic-ops-2026/13-architecture-recommendation-v2.md`. Full verified domain knowledge in `../context/`.

## What is it

Aegis is a four-surface AI agent safety net that any agent in a Splunk-customer environment can consult (or be intercepted by) before taking risky actions. It answers three questions in real time, with auditable record-keeping:

1. Is this user input a prompt-injection attempt?
2. Does this agent output contain PII / PHI / PCI / credentials / source code?
3. Is this tool-call's argument set safe to execute?

Verdicts emit as OpenTelemetry GenAI evaluation events, land in Splunk via HEC (using the same `cisco_ai_defense:*` sourcetype family that Cisco Security Cloud Splunkbase app 7404 already populates in 55,544+ customer instances), surface in three Splunk Dashboard Studio v2 dashboards, and integrate with Enterprise Security risk-based alerting.

## The four surfaces

| # | Surface | Consumer | Status |
|---|---|---|---|
| S1 | `aegis-mw` — Python middleware library for `splunklib.ai` agents | Agent developer | spec |
| S2 | `aegis-mcp` — own MCP server (parallel to Splunk's, not into it) | Any MCP client (Claude Desktop / Cursor / LangGraph / custom) | spec |
| S3 | DefenseClaw integration (config delta + upstream PR) | HTTP-intercept layer for non-`splunklib.ai` agents | spec |
| S4 | `aegis-app` — Splunk app with SPL/MLTK + Dashboard Studio v2 | CISO / SOC analyst / compliance / regulator | spec |

## Judgment layer

Multi-model, each model doing what it was actually built for:

- **Cisco AI Defense Inspection API** — binary classifier; 11 named rules (Prompt Injection, PII, PHI, PCI, Code Detection, Harassment, Hate Speech, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats); 10M queries/AI-app/year quota verified in Cisco's Offer Description PDF
- **Foundation-Sec-1.1-8B-Instruct via `| ai` SPL** — explanations only (used as Cisco markets it: a security copilot/generator, not a classifier); 64k context, RLHF-tuned
- **Luna-2 (Galileo, Cisco-owned since May 22 2026)** — future hosted judge; no announced Splunk integration date; designed for plug-in once Cisco publishes an SDK or HTTP integration

## License

[Apache-2.0](LICENSE). Auto-detectable by GitHub per Splunk Agentic Ops Hackathon submission requirements.

## Repo layout

```
aegis/
├── README.md           ← you are here
├── LICENSE             ← Apache-2.0
├── .gitignore
├── docs/
│   ├── PRD.md
│   ├── architecture.md
│   ├── cicd-spec.md
│   ├── eval-spec.md
│   ├── ux-spec.md
│   ├── epics.md
│   ├── stories/
│   │   ├── story-cicd-01-*.md
│   │   ├── story-mw-01-*.md
│   │   └── ...
│   └── plans/
│       └── 2026-06-02-aegis-spec-set-design.md
└── (code arrives after specs land + epics get GitHub-issue'd)
```

### Local development setup

```bash
uv sync --all-packages --frozen
uv run pre-commit install
```

After this, `git commit` runs ruff + mypy --strict + 400-LOC cap + gitleaks + no-print locally before the commit lands. See `docs/ops/pre-commit-install.md` for hook details and bypass policy.

## Source-of-truth links

- Architecture: `../research/splunk-agentic-ops-2026/13-architecture-recommendation-v2.md`
- Domain knowledge: `../context/` (12 numbered folders, ~150K words, 12+ primary-source PDFs, every claim flagged ✅/🟡/❓/❌)
- Hallucination audit: `../context/HALLUCINATION-AUDIT.md`
- Brainstorm output: `docs/plans/2026-06-02-aegis-spec-set-design.md`
