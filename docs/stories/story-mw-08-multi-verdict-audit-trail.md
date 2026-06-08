# Story — Multi-verdict audit chain via AIMessage.extras (F1 from PR #86 retroactive review)

**ID:** story-mw-08-multi-verdict-audit-trail
**Epic:** EPIC-06 — Surface 1 (splunkgate-mw middleware library for splunklib.ai)
**Depends on:** story-mw-04-model-middleware-post-inference-pii-check
**Estimate:** ~1.5h
**Status:** COMPLETE (PR #98, merged 2026-06-06)
**Closes:** GitHub issue #94

---

## User story

**As a** compliance officer or SOC analyst reading a redacted agent response
**I want to** recover the full pre+post verdict chain from the response message itself, not by joining OTel events on trace_id post-hoc
**So that** the Regulator Evidence Pack (story-app-07) verdict-chain drill-down can read the chain from the in-band `extras` field, and the auditor narrative — "input was redacted because X, then output was also redacted because Y" — reads cleanly without a Splunk join

---

## The bug F1 surfaced

`SafetyModelMiddleware` could fire BOTH a pre-inference verdict AND a post-inference verdict in one request. When pre rewrote input + post rewrote output to `[REDACTED]`, the returned `ModelResponse.message.content == "[REDACTED]"` only reflected the post verdict — the pre verdict's rules + trace_id were not surfaced in-band.

## File modification map (as shipped)

- `packages/splunkgate_mw/src/splunkgate_mw/model_middleware.py` — UPDATE — added `pre_verdict` parameter to `_apply_post_scan`, added two module-level helpers `_build_audit_extras` and `_with_extras`. 292 LOC after change (cap 400).
- `packages/splunkgate_mw/tests/test_audit_chain_extras.py` — NEW — 12 tests (8 pure-function unit + 4 integration via monkey-patched `pre_inference_scan`).

## Behavior matrix

| Pre | Post | Returned `extras` |
|---|---|---|
| ALLOW | ALLOW | unchanged (None) |
| ALLOW | MODIFY | `{splunkgate_post_trace_id}` |
| MODIFY | ALLOW | `{splunkgate_pre_trace_id}` |
| MODIFY | MODIFY | `{splunkgate_pre_trace_id, splunkgate_post_trace_id}` |
| BLOCK pre | — | raise `ModelInputBlockedBySplunkGate` (verdict carries trace_id) |
| * | BLOCK post | raise `ModelOutputBlockedBySplunkGate` (logger captures pre_trace_id when applicable) |

## Acceptance criteria (BDD — machine-verifiable, all passing)

```
Given a non-ALLOW pre_verdict and a MODIFY post_verdict
When  SafetyModelMiddleware.model_middleware completes
Then  result.message.extras["splunkgate_pre_trace_id"] equals str(pre_verdict.trace_id)
And   result.message.extras["splunkgate_post_trace_id"] equals str(post_verdict.trace_id)

Given _with_extras is called on an AIMessage with existing extras
When  the result is inspected
Then  upstream agent extras coexist with splunkgate_* keys; splunkgate_* wins on collision

Given the 12 new tests
When  `uv run pytest packages/splunkgate_mw/tests/test_audit_chain_extras.py` runs
Then  all 12 pass
```

## Forward-compat note

`pre_inference_scan` currently produces only BLOCK or ALLOW — never MODIFY. The pre-MODIFY → post-ALLOW branch this story plumbs is forward-compat for a future Foundation-Sec-driven pre-judge that produces MODIFY verdicts. The 4 integration tests cover this future case via monkey-patched pre-scan; the 8 pure-function unit tests cover the helper contract directly.

## Notes

- Keys are namespaced `splunkgate_*` so they don't collide with splunklib.ai's own LLM-provider extras.
- `_with_extras` uses `dataclasses.replace` on the frozen AIMessage — verified safe by reviewer pass on PR #98.
- Closes [issue #94](https://github.com/Blockchain-Oracle/splunkgate/issues/94).
