# Synthetic-Data

Deterministic synthetic corpora for the SplunkGate eval harness. The
folder mirrors DNS Guard 2025's winning data-generator pattern (per
ADR-011 in `docs/architecture.md`); spelling is corrected to
`Synthetic-Data/` — DNS Guard's repo uses `Syntethic-Data/` (sic). We
mirror the *content* pattern, not the typo.

## Sub-corpora

| File | Records | Category | Verdict mix |
|---|---|---|---|
| `jailbreak_corpus/tool_call_abuse.jsonl` | ≥ 200 | `tool_call_abuse` | mostly BLOCK |
| `jailbreak_corpus/multi_turn_injection.jsonl` | ≥ 150 | `multi_turn_injection` | mostly BLOCK |
| `jailbreak_corpus/benign_control.jsonl` | ≥ 300 | `benign_control` | all ALLOW |
| `pii_leak_corpus/` (story-eval-03 lands `imprompter_payloads.jsonl` here) | — | `imprompter` | — |

## Record schema (`EvalPrompt`)

Every line of every JSONL is one JSON object validating against
`splunkgate_eval.synthetic.EvalPrompt`:

```jsonc
{
  "id": "<uuid4>",
  "category": "tool_call_abuse" | "multi_turn_injection" | "benign_control" | "...",
  "prompt": "<the agent input>",
  "expected_verdict": "ALLOW" | "BLOCK" | "MODIFY" | "REVIEW",
  "expected_severity": "NONE_SEVERITY" | "LOW" | "MEDIUM" | "HIGH",
  "source_citation": "<provenance label, e.g. synthetic:tool_call_abuse:v1>"
}
```

> **Do not hand-edit the JSONL files.** They are deterministic
> regenerations of `generate_agent_verdicts.py` — every PR or test that
> depends on a specific record must update the generator, not the
> JSONL output.

## How to regenerate

```bash
python Synthetic-Data/generate_agent_verdicts.py
```

The script is stdlib-only Python 3.13. It seeds `random` with
`20260602` so two runs produce byte-identical outputs (verified via
`sha256sum` in the spec shell verification). Wall clock < 60 s on a
laptop.

## Threat-model sources

- Tool-call abuse: path traversal, SQL injection, shell metacharacter
  injection, argument-confusion attacks (per
  `context/01-threat-landscape/03-tool-abuse-patterns.md`).
- Multi-turn injection: Anthropic Many-Shot Jailbreaking power-law,
  4/8/16/32 shot counts per `context/01-threat-landscape/02-jailbreak-techniques.md` § 5.
- Benign control: SOC-analyst + customer-support prompts with no real
  customer data (per `context/04-pii-phi-pci/01-pii-definitions-by-jurisdiction.md`).
