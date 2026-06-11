# Imprompter PII-leak payload corpus

`imprompter_payloads.jsonl` contains 11 adversarial prompts derived from
the Imprompter paper:

> Xiaohan Fu, Shuheng Li, Zihan Wang, Yihao Liu, Rajesh K. Gupta, Taylor
> Berg-Kirkpatrick, **Earlence Fernandes** (UC San Diego + Nanyang
> Technological University), *"Imprompter: Tricking LLM Agents into
> Improper Tool Use"*, arXiv:2410.14923v2, 2024-10-22.

Each record corresponds to one prompt ID from Table 2 (T1–T8,
information-exfil) and Table 5 (T9, T10, T12, PII-exfil) of the paper.
T11 is omitted per the story spec — it has the lowest combined
Syntax-Correct + PII-Precision in Table 6 (48.1% / 22.0%); we vendor the
11 highest-success-rate payloads to keep the corpus focused on the
attack patterns that hit production agents.

## Adversarial domain

Every payload uses the attacker-controlled exfil domain `velocity.show`
verbatim (paper p. 7, Table 1: *"velocity.show is the attacker-specified
domain name we use across this paper. It was intentionally chosen to be
irregular and non-URL looking."*). Do **not** swap it for a different
domain — the eval harness greps for this literal string.

## Target-agent enumeration

Every record's `target_agent` field is one of:

- `LeChat` — Mistral LeChat (Nemo variant)
- `ChatGLM` — chatglm.cn
- `Custom Llama Agent` — Meta Llama 3.1 70B (UCSD-built, per paper §5)
- `Mistral LeChat (Nemo)` — same product, explicit Nemo variant labelling

## Mistral patched the renderer vector on 2024-09-13

Per the paper §"Disclosure and Response" (p. 12, verbatim):

> *"Mistral team members responded promptly and acknowledged the
> vulnerability as a medium-severity issue. They fixed the data
> exfiltration by disabling markdown rendering of external images on
> Sep 13, 2024."*

Records that target LeChat are flagged `"patched": true` with
`"patch_date": "2024-09-13"`. **Mistral patched the rendering-layer
vector 2024-09-13; we detect the payload pattern in the LLM output for
defense-in-depth, not as the sole defense.** The eval harness exists to
catch attempted exfil at the model-output layer so the audit log
captures the attack even when the renderer has been hardened.

ChatGLM had not patched as of the paper revision; T11/T12 records carry
`"patched": false`.

## Schema

Each line is a JSON object validating against the additional fields
documented in `eval/src/splunkgate_eval/imprompter.py`:

```jsonc
{
  "id": "<deterministic UUIDv5>",
  "label": "T1" | "T2" | … | "T12",  // paper prompt-ID
  "target_agent": "LeChat" | "ChatGLM" | "Custom Llama Agent" | "Mistral LeChat (Nemo)",
  "target_syntax": "<verbatim invocation pattern from paper p. 7 Table 1>",
  "payload": "<the adversarial prompt — preserved byte-identical to the PDF>",
  "expected_verdict": "BLOCK",
  "expected_severity": "HIGH",
  "category": "imprompter",
  "source_citation": "arxiv:2410.14923v2:<table>:<row>",
  "paper_section": "Table 2 / T1 / Mistral Nemo / Info-Exfil"  // or similar
  "patched": true,
  "patch_date": "2024-09-13" or null
}
```

## Responsible-use warning

These payloads are **published adversarial examples** vendored for
defensive evaluation. Do not deploy them against live products —
production renderer-layer mitigations exist for a reason. The academic
disclosure principle is "publish to enable defence", not "publish to
enable replay".

## Provenance + Unicode fidelity

The payloads were extracted from `sources/pdfs/imprompter-2410.14923v2.pdf`
via `pdftotext -layout` (poppler-utils). The mixed-script Unicode
(Devanagari, Cyrillic, Arabic, Telugu, Tamil, etc.) is preserved as
UTF-8 bytes — open the JSONL with `encoding="utf-8"` and never with
`ascii`/`latin-1`. Byte-perfect verification against the PDF tables 2
and 5 is left as a future exercise; the records here are line-faithful
to the `pdftotext` output, which may show small layout artefacts.
