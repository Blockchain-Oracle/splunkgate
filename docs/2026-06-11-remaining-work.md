# What's truly remaining — 2026-06-11

Deadline: **Devpost submission 2026-06-15 09:00 PDT** (3 days, 18 hours).

Sprint state: 44 COMPLETE · 21 PENDING · 5 DEFERRED.

This note answers the conversation Abu asked for: "what is truly remaining
for what we're building truly." Not what sprint-status looks pretty — what
actually matters by Sunday.

---

## Hackathon-critical (must-ship)

These directly affect whether the submission lands or whether the demo can
be shot. Ordered by deadline pressure.

### 1. Demo screencast — `story-demo-01` (PENDING)
- **Why blocking:** Devpost form requires a video link. Without it, the
  submission can't be filed.
- **Scope:** the 90-second walkthrough described in `grounding.md`
  "Demo moment" — terminal BLOCK → Splunk dashboard ticks → Verdict
  Inspector drill-down → SAIA NL→SPL query → Regulator Evidence Pack
  Export PDF.
- **Estimate:** 1 day script + 1 day record/edit/upload
- **Dependency:** the live splunkgate-local container working end-to-end
  (see #3).

### 2. SAIA NL→SPL demo moment — `story-demo-02` (PENDING)
- **Why blocking:** integrates as step 5 of the same video. Not a
  separate deliverable — same video, one extra scene.
- **Scope:** type a natural-language question, watch SAIA produce SPL,
  show the result against the splunkgate index.
- **Estimate:** folds into demo-01 work; ~2 hours additional rehearsal.

### 3. AppInspect re-validation at HEAD
- **Why blocking:** submission gate #1. We have the CI gate (story-cicd-
  05, merged PR #122) but no run-of-record against the current built
  tarball.
- **Estimate:** ~30 minutes mechanical:
  `splunk-appinspect inspect dist/splunkgate_app-1.0.0.tgz`
- **Risk:** if a finding surfaced since the last clean run, may need
  ~1-2 hours to expect-list or fix.

### 4. Devpost submission form fill
- **Why blocking:** the form itself is the submission.
- **Scope:** title, tagline, description (from `grounding.md`), Built
  With list, GitHub URL, video URL, screenshots (from
  `docs/screenshots/*` — already in repo per memory #10542).
- **Estimate:** ~1-2 hours.
- **Dependency:** items 1-2 (video URL).

**Critical-path total:** ~3.5 days. Fits inside the 3-day, 18-hour
window only if we start the demo work now.

---

## Splunk-app redesign (decision pending)

Abu's ask earlier today: rework the Splunk app dashboards to look more
on-brand with the landing page. Three options laid out in
`docs/design/splunk-app-redesign-brief.md` with effort estimates and
risk profile.

Recommendation: **Option A** (theme-only JSON tweaks) if we're already
behind on demo recording. **Option C** (hybrid — Evidence Pack as SUIT
custom React view, operational dashboards stay Dashboard Studio) if we
have slack.

**This is not in the critical path.** The dashboards work today.

---

## Honest-signals items (ship structure-only)

Per HALLUCINATION-AUDIT discipline, these stories were always going to
ship as "structure ready, results pending." They are PENDING in
sprint-status but **not blockers** — the design said so from the start.

- `story-eval-01` — synthetic data generator
- `story-eval-02` — JailbreakBench + AdvBench loaders
- `story-eval-03` — Imprompter corpus from PDF
- `story-eval-04` — three baselines (defenseclaw / gpt-oss / AI Defense)
- `story-eval-05` — metrics + report generator
- `story-eval-06` — agent-to-Splunk integration test
- `story-cicd-06` — eval-smoke CI job (gates results we don't have)
- `story-cicd-08` — signed release pipeline (gates a release we won't cut)

The eval workspace package exists, the docs page shows the table
structure with "pending" cells, the README explains the discipline. These
are on-brand non-shipping items.

---

## Middleware extras (PENDING but unblocked-by-deferred decisions)

- `story-judges-03` — AI Defense circuit breaker via tenacity. The
  middleware ships without it today; degraded mode falls back to
  splunklib.security first-pass. Worth doing if we have slack; not
  blocking submission.
- `story-judges-05` — AI Defense end-to-end integration test against
  a mock. Quality bar item, not user-visible.
- `story-mw-05` — subagent middleware. Class is exported as a stub;
  real implementation defers per ADR-013.
- `story-mw-06` — agent middleware + trace correlation. Same shape.
- `story-mw-07` — profiles FSI/HIPAA/PCI/PUBSEC. Currently only DEFAULT
  ships. Docs page is honest about this ("FSI/HIPAA/PCI land with
  story-mw-07").
- `story-dc-01` — DefenseClaw config-delta docs + example. The landing
  page + docs page link to a "pending" page for this; would close the
  S3 surface fully if shipped.

**My call:** none of these block the submission. They're quality polish.
Pick one or two if Track A1 (Splunk-app redesign) decision goes to
Option A.

---

## Operational hygiene (skippable)

- `story-skel-03` — CLAUDE.md polish
- `story-skel-04` — LOC check script + pre-commit (already covered by
  existing pre-commit chain)
- `story-app-10` — Playwright vision-loop validation (use the
  `sahil-visual-loop` skill ad-hoc instead)
- `story-ops-01` — branch protection config
- `story-ops-02` — GitHub secrets + ADR template

None are user-visible. Defer.

---

## DEFERRED items (per ADR-013 — do not reopen)

These five were deliberate scope cuts and should NOT come back in scope:

- `story-foundsec-01/02/03` — Foundation-Sec swap (Splunk Hosted Models
  access unverified; `memory:aegis_hosted_models_gap`)
- `story-mcp-04` (output leak), `story-mcp-05` (audit trace) — **already
  shipped** in the MCP server (`splunkgate_check_output_leak`,
  `splunkgate_audit_trace`). Sprint-status should be flipped; these were
  marked DEFERRED but the work actually happened.
- `story-dc-02` (DefenseClaw upstream PR)
- `story-dc-03` (LangGraph example agent)
- `story-judges-06` (DefenseClaw Python shim)

---

## Submission readiness checklist (the actual hill)

| Item | State |
|------|-------|
| Working dashboards (3) | ✅ |
| Built `splunkgate_app-1.0.0.tgz` | ✅ |
| `manifest.json` Splunk Cloud 10.4 | ✅ |
| AppInspect zero error-severity (re-validated at HEAD) | 🟡 needs ~30 min |
| README + banner + architecture brief | ✅ |
| Built-on credits | ✅ |
| Demo video URL | ❌ — story-demo-01 / -02 |
| Devpost form filled | ❌ — depends on video URL |
| Screenshots in repo (`docs/screenshots/*`) | ✅ per memory #10542 |
| GitHub repo public + Apache-2.0 | ✅ |

**The two ❌'s are the entire remaining critical path.** Everything else
is decoration or polish.

---

## Concrete next move (my recommendation)

1. **Write the demo script** — `docs/demo/script.md`. ~2 hours.
2. **Dry-run the end-to-end on the live container** — verify the BLOCK
   demo, the Splunk row tick, the SAIA query, the Evidence Pack PDF
   export all work as one flow. ~1 hour.
3. **Record the screencast** — 90 seconds finished, plan ~3 hours
   including retakes + edit. Upload unlisted to YouTube.
4. **Re-run AppInspect against the tarball at HEAD.** ~30 min.
5. **Fill the Devpost form.** ~1.5 hours.

That's ~8 hours of focused work. Leaves a ~3-day buffer for the
Splunk-app brief decision + any rework.

If we get all of the above by EOD Friday Jun 12, we ship Saturday with
slack. If we slip to Saturday Jun 13, we ship Sunday morning with no
slack.

---

## What I'm explicitly not doing tonight

- Track A1 (Splunk-app redesign brief implementation) — waiting for
  Abu's A/B/C decision.
- Eval harness implementation — out of scope per HALLUCINATION-AUDIT.
- Foundation-Sec swap — DEFERRED.
- DefenseClaw upstream PR — DEFERRED.

I am ready to start on the demo script as soon as Abu signals go.
