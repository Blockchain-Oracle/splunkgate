# Story — Visual loop validation (Playwright + odiff + Opus 4.7 vision review)

**ID:** story-app-10-app-vision-loop-validation
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-05-dashboard-agent-risk-overview, story-app-06-dashboard-verdict-inspector, story-app-07-dashboard-regulator-evidence-pack
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent finishing an EPIC-09 dashboard story (app-05/06/07) or any later visual touch-up
**I want to** have an automated visual-validation gate that: (a) loads each of the 3 dashboards in Playwright against a live Splunk instance with synthetic events, (b) screenshots them, (c) `odiff`s against committed anchor screenshots, (d) sends both to a fresh-context Opus 4.7 vision reviewer that scores slop and blocking-count, (e) fails the PR if `slop_score > 2` OR `blocking_count > 0`
**So that** dashboard regressions never ship without a fresh-eyes review, the DNS Guard winning aesthetic stays the bar, and "looks fine to me" gets replaced with a structured slop-delta report attached to every PR

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `playwright.config.ts` — NEW — minimal Playwright config (no TypeScript app exists yet — config is pure JS-as-TS, ~50 LOC); declares `chromium` + `webkit` projects, viewport 1440x900, `ignoreHTTPSErrors: true`, `baseURL: process.env.AEGIS_SPLUNK_URL || "https://localhost:8000"`, screenshot path `screenshots/current/`, test directory `tests/visual/`.
- `tests/visual/dashboards.spec.ts` — NEW — Playwright test file (~120 LOC). 3 tests (one per dashboard): each navigates to `${baseURL}/en-US/app/aegis_app/<dashboard_name>`, waits for `[data-test="visualization"]` selector with 15s timeout, scrolls to bottom + back to top to ensure full render, captures `screenshots/current/<dashboard>--desktop.png` full-page screenshot. Tests fail on any browser console error.
- `scripts/visual_loop.sh` — NEW — bash orchestrator (~80 LOC). Steps: (1) ensure Splunk Docker is running (`docker compose -f infra/splunk-docker-compose.yml up -d` if not running), (2) emit synthetic verdict events via `scripts/emit_sample_verdict.py` (loop ~500 events covering all 4 surfaces + 11 rules + all severities + jurisdictional_tags), (3) wait 30s for indexing, (4) `uv run playwright test`, (5) run `odiff` per dashboard comparing `screenshots/current/<name>.png` vs `screenshots/anchor/<name>.png` with threshold 0.05, output diff PNGs to `screenshots/diff/`, (6) call `scripts/vision_review.py` for each dashboard, (7) parse the structured JSON output, (8) exit 0 only if all 3 dashboards have `slop_score <= 2 AND blocking_count == 0`.
- `scripts/vision_review.py` — NEW — Python script (~150 LOC, ≤ 400). CLI: `--anchor <path> --current <path> --diff <path> --dashboard-name <name> --output <json>`. Loads the 3 images, posts them to Claude API (Opus 4.7) with a fresh-context reviewer prompt (no project history), receives back a JSON verdict: `{ "dashboard": "<name>", "slop_score": int 0-10, "blocking_count": int, "blocking_issues": [str], "minor_issues": [str], "verdict": "ok" | "block" }`. Saves verdict to `.claude/visual-reviews/<dashboard>--<timestamp>.json` and prints summary.
- `.claude/hooks/post_dashboard_edit.sh` — NEW — PostToolUse hook (~30 LOC). Triggers on any Write/Edit to `splunk_apps/aegis_app/default/data/ui/views/*.xml`. Body: spawns `scripts/visual_loop.sh` in background, posts result to the build thread. Wired via `.claude/settings.json` PostToolUse matcher (this story owns hook script + matcher addition).
- `.claude/settings.json` — UPDATE — append a PostToolUse matcher entry: `{ "matcher": "Write|Edit", "filePathPattern": "splunk_apps/aegis_app/default/data/ui/views/.*\\.xml$", "command": ".claude/hooks/post_dashboard_edit.sh" }`.
- `screenshots/anchor/agent_risk_overview--desktop.png` — NEW — captured one-time from the first clean build of dashboard 1 (story app-05). Committed as the visual anchor.
- `screenshots/anchor/verdict_inspector--desktop.png` — NEW — captured from story app-06.
- `screenshots/anchor/regulator_evidence_pack--desktop.png` — NEW — captured from story app-07 (default profile).
- `screenshots/anchor/regulator_evidence_pack--fsi.png` — NEW — captured from story app-07 (FSI profile, profile-gated panels hidden).
- `infra/splunk-docker-compose.yml` — NEW — minimal Docker Compose (~40 LOC) for local Splunk Enterprise dev instance (image `splunk/splunk:9.4.0`, HEC enabled, `SPLUNK_PASSWORD` from env, port 8000 + 8088 + 8089 exposed, volume mount for `splunk_apps/aegis_app/` into `/opt/splunk/etc/apps/aegis_app/`).

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given playwright.config.ts exists
When  `uv run playwright test --list` runs
Then  exit code is 0
And   3 tests appear (one per dashboard: agent_risk_overview, verdict_inspector, regulator_evidence_pack)

Given the 3 anchor screenshots exist in screenshots/anchor/
When  `ls screenshots/anchor/*.png | wc -l` runs
Then  output is >= 4 (3 dashboards + 1 FSI variant)

Given each anchor PNG
When  `file <path>.png` runs
Then  output contains "PNG image data" (not corrupted)

Given the Splunk Docker container is running with the app installed and synthetic events loaded
When  `scripts/visual_loop.sh` runs
Then  exit code is 0
And   `screenshots/current/agent_risk_overview--desktop.png` exists and is fresh (mtime within last 5 min)
And   `screenshots/current/verdict_inspector--desktop.png` exists and is fresh
And   `screenshots/current/regulator_evidence_pack--desktop.png` exists and is fresh
And   `screenshots/diff/*.png` exists for each dashboard with non-corrupted PNG output
And   `.claude/visual-reviews/<dashboard>--<timestamp>.json` exists for each dashboard

Given a vision review JSON file
When  `jq '.slop_score, .blocking_count, .verdict' <file>.json` runs
Then  slop_score is an integer 0-10
And   blocking_count is an integer >= 0
And   verdict is "ok" or "block"

Given all three vision review JSON files
When  the passing rule is checked
Then  all three have `slop_score <= 2 AND blocking_count == 0` for the loop to exit 0

Given .claude/hooks/post_dashboard_edit.sh exists
When  `bash -n .claude/hooks/post_dashboard_edit.sh` runs (syntax check)
Then  exit code is 0

Given .claude/settings.json is updated
When  `jq '.hooks.PostToolUse[] | select(.filePathPattern | contains("aegis_app"))' .claude/settings.json` runs
Then  the matcher entry is present

Given a coding agent edits splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml
When  the file is saved
Then  the PostToolUse hook fires .claude/hooks/post_dashboard_edit.sh
And   scripts/visual_loop.sh runs in the background

Given scripts/vision_review.py
When  `wc -l scripts/vision_review.py` runs
Then  output <= 400

Given odiff is installed and the visual loop ran end-to-end
When  any pixel-difference exceeds 5% (default odiff threshold) on any dashboard
Then  scripts/visual_loop.sh exits non-zero before reaching the vision review step

Given any vision review returns verdict="block"
When  scripts/visual_loop.sh inspects the JSON
Then  the script exits 1 with a clear error message naming the failing dashboard

Given all four blocks pass (Playwright, odiff, vision review per dashboard)
When  the loop exits
Then  the exit code is 0 and the orchestrator can merge the PR
```

---

## Shell verification

```bash
set -euo pipefail

# 1. Required files exist
test -f playwright.config.ts
test -f tests/visual/dashboards.spec.ts
test -f scripts/visual_loop.sh
test -f scripts/vision_review.py
test -f .claude/hooks/post_dashboard_edit.sh
test -f infra/splunk-docker-compose.yml
test -f screenshots/anchor/agent_risk_overview--desktop.png
test -f screenshots/anchor/verdict_inspector--desktop.png
test -f screenshots/anchor/regulator_evidence_pack--desktop.png
test -f screenshots/anchor/regulator_evidence_pack--fsi.png

# 2. Anchor PNGs valid
for f in screenshots/anchor/*.png; do
  file "$f" | grep -q "PNG image data"
done

# 3. Playwright config lists 3 tests
uv run playwright test --list 2>&1 | tee /tmp/pw-list.txt
test "$(grep -c 'agent_risk_overview\|verdict_inspector\|regulator_evidence_pack' /tmp/pw-list.txt)" -ge 3

# 4. Visual loop script syntax + LOC sanity
bash -n scripts/visual_loop.sh
bash -n .claude/hooks/post_dashboard_edit.sh
test "$(wc -l < scripts/vision_review.py)" -le 400
test "$(wc -l < scripts/visual_loop.sh)" -le 400
test "$(wc -l < .claude/hooks/post_dashboard_edit.sh)" -le 400

# 5. settings.json hook matcher present
jq -e '.hooks.PostToolUse[] | select(.command | contains("post_dashboard_edit"))' .claude/settings.json >/dev/null

# 6. Full loop dry-run (gated on AEGIS_SPLUNK_HOST + ANTHROPIC_API_KEY)
if [ -n "${AEGIS_SPLUNK_HOST:-}" ] && [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  bash scripts/visual_loop.sh
  # Verify outputs
  for d in agent_risk_overview verdict_inspector regulator_evidence_pack; do
    test -f "screenshots/current/${d}--desktop.png" || { echo "Missing current screenshot: $d"; exit 1; }
    test -f "screenshots/diff/${d}--diff.png" || { echo "Missing diff screenshot: $d"; exit 1; }
    LATEST=$(ls -t .claude/visual-reviews/${d}--*.json | head -1)
    test -f "$LATEST" || { echo "Missing vision review JSON: $d"; exit 1; }
    SLOP=$(jq -r '.slop_score' "$LATEST")
    BLOCKING=$(jq -r '.blocking_count' "$LATEST")
    test "$SLOP" -le 2 || { echo "$d slop_score $SLOP > 2"; exit 1; }
    test "$BLOCKING" -eq 0 || { echo "$d blocking_count $BLOCKING != 0"; exit 1; }
  done
  echo "All dashboards pass slop_score <= 2 AND blocking_count == 0"
fi

# 7. Hook triggers on file write (integration test, gated on env)
if [ -n "${AEGIS_SPLUNK_HOST:-}" ]; then
  # Simulate a Write tool call by touching the file
  touch splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml
  # The hook runs in background; just verify the script is executable
  test -x .claude/hooks/post_dashboard_edit.sh
fi

# 8. Anchor screenshots are stable (md5 doesn't change between commits)
# Sanity: if anchor PNGs change, the slop budget gets refreshed which is the intended flow.
# This block just records the current md5 for change-detection in PR review.
md5sum screenshots/anchor/*.png | tee screenshots/anchor/.md5-manifest.txt
```

All eight blocks must exit 0 before opening the PR (blocks 6 and 7 gated on env vars).

---

## Notes for coding agent

- Per `docs/ux-spec.md` § "Visual loop validation", the gate is `slop_score <= 2 AND blocking_count == 0`. Do not relax this threshold. If a dashboard scores 3, fix the dashboard — do not adjust the threshold.
- Per `docs/ux-spec.md` § "Visual loop validation" + the `sahil-visual-loop` skill spec (mentioned in the workflow), the loop is: build → screenshot → diff vs anchor → vision reviewer → structured slop-delta report → iterate. This story implements the full loop for Splunk dashboards specifically.
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, DNS Guard 1st-place winner's visual aesthetic is the bar. Anchor screenshots are captured the first clean time each dashboard renders, and stay the immutable reference for "this is the DNS Guard-quality look."
- The vision review prompt for `scripts/vision_review.py` should be drafted with the Sahil anti-slop skill conventions in mind: structured JSON output, binary verdict per category, no "good job" prose. The reviewer is a fresh-context Opus 4.7 instance (no project history) so it scores what it sees, not what it expects to see.
- The 5 reviewer categories: (1) layout integrity (no overlapping panels, no truncated text), (2) Splunk-native styling preservation (no custom CSS slop, no `rounded-xl`-looking panels), (3) data freshness (panels show events, not empty states), (4) drill-down affordances visible (clickable rows, hover states implied), (5) accessibility hints (color + text labels paired). Each scored 0-2 (0 = bad, 1 = mediocre, 2 = good); blocking issues are any category scoring 0.
- The Anthropic API call uses Claude Opus 4.7 (1M context model alias `claude-opus-4-7[1m]` per `docs/architecture.md` development notes). Use `anthropic` Python SDK; gate behind `ANTHROPIC_API_KEY` env var.
- `odiff` is preferred over `pixelmatch` per the visual-loop skill spec — faster, deterministic, handles anti-aliasing. Install via `npm install -g odiff-bin` or call via npx in `visual_loop.sh`.
- The Splunk Docker image `splunk/splunk:9.4.0` is the floor of our compatibility line; testing against 9.4 catches Dashboard Studio v2 features that don't backport. CI uses the same image.
- Synthetic event emission: `scripts/emit_sample_verdict.py` lives outside this story's file modification map (it's a dependency from story-app-02). If the script doesn't exist yet, this story's `visual_loop.sh` should gracefully skip event emission and run against whatever data is already in the index. Flag the dependency in PR description.
- The PostToolUse hook fires on file write; it spawns the visual loop asynchronously and posts the verdict back to the build thread (Telegram/Discord per `docs/sprint-status.yaml` thread_surface field). The hook does NOT block the file write — async so the coding agent's workflow stays fast.
- Anchor screenshots are committed to git. Yes, this means binary blobs in the repo. For ~4 PNGs at ~500KB each (2MB total), this is acceptable; the alternative (anchor in S3) adds infra dependency for a tiny benefit.
- When a dashboard story (app-05/06/07) lands, the coding agent for THAT story commits the anchor PNG as part of THEIR PR. This story (app-10) consumes the committed anchors. If an anchor is missing, this story's loop fails with "anchor not found — capture from story-app-XX first".
- Per the story brief: "passing threshold slop_score ≤ 2 AND blocking_count = 0" — the loop short-circuits at the first failed gate (odiff failure → don't bother with vision review; vision review failure → return the structured report).
- `screenshots/diff/` is .gitignored — diffs are ephemeral CI artifacts, not committed. Add the .gitignore entry as part of this story's PR if not already present.
- `.claude/visual-reviews/` is also .gitignored — vision review JSONs are CI artifacts. But uploaded to the build thread for human review.
- The Playwright tests in `tests/visual/dashboards.spec.ts` are NOT part of the Python pytest suite — they run via `npx playwright test` (or `uv run playwright test` if playwright-python is used). Stick with the Node Playwright runner; it's faster for screenshot capture and is what the `sahil-visual-loop` skill standardizes on.
- If `infra/splunk-docker-compose.yml` proves heavy to spin up in CI, the loop can hit a long-lived shared Splunk Cloud dev instance instead (gated on `AEGIS_SPLUNK_URL`). Document both modes in the script's `--help`.
- This is the last EPIC-09 story. After this lands, EPIC-12 (AppInspect hardening + Splunkbase submission) is unblocked.
