# SplunkGate — Release Notes

## 1.0.0 (2026-06-05)

Initial Splunkbase-targeted release. The SplunkGate app surfaces runtime AI-
agent safety verdicts as a sourcetype that colocates with the Cisco
Security Cloud add-on (Splunkbase 7404), exposes three Dashboard Studio
v2 dashboards (Agent Risk Overview, Verdict Inspector, Regulator
Evidence Pack), and integrates with Enterprise Security via
Risk-Based Alerting.

Major surfaces shipped in 1.0.0:

- **Sourcetype** `cisco_ai_defense:splunkgate_verdict` for HEC-ingested
  SplunkGate verdicts (OTel `gen_ai.evaluation.result` events).
- **3 dashboards** under `default/data/ui/views/`:
  agent_risk_overview, verdict_inspector, regulator_evidence_pack.
- **KV-store collections** for verdict history + jurisdictional
  profile index (`collections.conf` + seed lookup).
- **MLTK macros** mirroring DNS Guard AI 2025's winning shape: fit
  DensityFunction + fit KMeans k=2 + anomalydetection.
- **ES Risk-Based Alerting** integration via `risk_factors.conf`
  (11 per-rule scoring stanzas + HIGH severity multiplier + whitelist
  exclusion) + correlation alert wired to `action.risk.param.*`.
- **MITRE ATLAS** lookup mapping every Cisco AI Defense rule name to
  its ATLAS technique ID.
- **Profile-gated regulatory panels** (FSI / HIPAA / PCI / PUBSEC)
  with verbatim SR 26-2 + NIST AI RMF + EU AI Act framings.
- **AppInspect compliance**: 25-check manualcheck.yaml verbatim
  mirror of CIMplicity AI 2025 winner; empty expect.yaml (no
  binaries to suppress).

For the full changelog see GitHub releases:
https://github.com/Blockchain-Oracle/splunkgate/releases
