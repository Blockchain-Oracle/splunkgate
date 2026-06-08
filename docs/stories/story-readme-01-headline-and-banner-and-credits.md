# Story — README.md final: headline + banner + install + eval table embed + incumbent credits

**ID:** story-readme-01-headline-and-banner-and-credits
**Epic:** EPIC-11 — README + demo
**Depends on:** story-eval-05-metrics-and-report-generator
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Devpost judge skimming the SplunkGate repo for ≤ 60 seconds before deciding whether to click play on the demo video
**I want to** open `README.md` and immediately see the one-line pitch, a banner image, the embedded YouTube demo link, an embedded architecture diagram link to the repo-root PNG, three install commands, the eval-table headline numbers, and explicit credit to the incumbents SplunkGate builds on
**So that** the submission satisfies every § README shape requirement in `docs/PRD.md` and every Devpost submission requirement (architecture diagram link visible, public license, install steps, video link, AI-as-infrastructure framing) in the order judges scan for them — and the README's eval table auto-updates from `docs/eval-results.md` (produced by story-eval-05) so we never ship stale numbers

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `README.md` — REPLACE — full rewrite of the existing spec-phase README. Section order locked per `docs/PRD.md` § "README shape (§13)": (1) title + one-line pitch, (2) banner image with light + dark variants via HTML `<picture>` tag, (3) demo video YouTube link as click-through image (uses `docs/assets/thumbnail.png` from story-demo-01 as poster), (4) architecture diagram link to repo-root `architecture_diagram.png` + dark variant (lands in story-readme-02), (5) quick install (exactly 3 shell commands), (6) eval table (transcluded from `docs/eval-results.md` via the include block comment markers `<!-- BEGIN eval-table --> ... <!-- END eval-table -->` that `eval/src/splunkgate_eval/report.py` from story-eval-05 writes between), (7) credits section (5 named incumbents, verbatim), (8) license (Apache-2.0), (9) the four-surfaces table (preserved from current README). Total target: ≤ 200 lines including blanks.
- `docs/assets/banner.png` — NEW — 1280×640 light-variant banner PNG (matches DNS Guard 2025 `Images/banners/banner.png` dimensions per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`). Generated programmatically by `scripts/build_banner.py` from a Pillow-based template; foreground text "SplunkGate — the runtime safety net every CISO needs before AI agents touch their Splunk data."; subtitle "Splunk Agentic Ops Hackathon · Apache-2.0 · 2026-06-15"; no Splunk/Cisco trademarked logos (Devpost rule per `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md`).
- `docs/assets/banner-dark.png` — NEW — dark-variant of the same banner; same dimensions; dark background (#0A0E1A) + light foreground; light/dark variants ship together per the DNS Guard pattern (`../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`).
- `scripts/build_banner.py` — NEW — Pillow-based banner generator (≤ 120 LOC). Two CLI flags: `--variant=light|dark` and `--out=<path>`. Hard-coded text from PRD § goal + one-line pitch. Deterministic output (fixed seed for any layout randomness). Re-runnable so the banner regenerates on text changes.
- `docs/eval-results.md` — NEW (empty stub) — placeholder file with the comment markers `<!-- BEGIN eval-table -->` and `<!-- END eval-table -->` between which `eval/src/splunkgate_eval/report.py` (story-eval-05) writes the markdown table. README transcludes this file via a shell script (next bullet) at release time. Stub also includes a `mock=true` placeholder row so README renders before live eval runs.
- `scripts/inline_eval_table.sh` — NEW — POSIX sh script that reads `docs/eval-results.md` between the two comment markers and replaces the same-named markers in `README.md`. Idempotent. Called by the nightly `eval.yml` CI job (already created in story-cicd-06) so README updates land as commits to `main`.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given README.md exists at the repo root
When  grep -c "^# SplunkGate" README.md runs
Then  count is exactly 1 (single H1 title)

Given README.md exists
When  grep -F "SplunkGate — the runtime safety net every CISO needs before AI agents touch their Splunk data." README.md runs
Then  the verbatim one-line pitch matches the PRD § goal string

Given README.md exists
When  grep -E "<picture>|docs/assets/banner.png|docs/assets/banner-dark.png" README.md runs
Then  all three patterns appear (light + dark banner via <picture>)

Given README.md exists
When  grep -E "youtube\.com/watch\?v=|youtu\.be/|vimeo\.com/" README.md runs
Then  exactly one demo video link is present (Devpost submission requirement per ../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md)

Given README.md exists
When  grep -E "architecture_diagram\.png|architecture_diagram_dark\.png" README.md runs
Then  both names appear (light + dark; the file at repo root is the canonical submission artifact per ../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md)

Given README.md exists
When  awk '/^## Quick install/,/^## /' README.md | grep -cE "^(git clone|uv add|splunk install|pip install|curl)" runs
Then  the count is exactly 3 (three-command install, max — per PRD § README shape)

Given README.md exists
When  grep -F "<!-- BEGIN eval-table -->" README.md and grep -F "<!-- END eval-table -->" README.md both run
Then  both markers are present (transclusion target for docs/eval-results.md)

Given README.md exists
When  grep -E "MCP Watch|Splunkbase 8765|Cisco Security Cloud|Splunkbase 7404|DefenseClaw|splunklib\.ai|NeMo Guardrails" README.md runs
Then  all six incumbent names appear (credits section verbatim per PRD § README shape)

Given README.md exists
When  grep -F "Apache-2.0" README.md runs
Then  at least one match (license declared in README in addition to the LICENSE file at root)

Given docs/assets/banner.png exists
When  python -c "from PIL import Image; im = Image.open('docs/assets/banner.png'); assert im.size == (1280, 640), im.size" runs
Then  exit code is 0 (light-variant dimensions correct per DNS Guard pattern)

Given docs/assets/banner-dark.png exists
When  python -c "from PIL import Image; im = Image.open('docs/assets/banner-dark.png'); assert im.size == (1280, 640), im.size" runs
Then  exit code is 0 (dark-variant dimensions correct)

Given scripts/build_banner.py exists
When  python scripts/build_banner.py --variant=light --out=/tmp/splunkgate-banner-test.png runs
Then  exit code is 0 and the output file is a valid PNG (sha256 deterministic across runs)

Given docs/eval-results.md exists
When  grep -F "<!-- BEGIN eval-table -->" docs/eval-results.md and grep -F "<!-- END eval-table -->" docs/eval-results.md both run
Then  both markers are present (transclusion source for scripts/inline_eval_table.sh)

Given scripts/inline_eval_table.sh exists
When  bash scripts/inline_eval_table.sh runs against the current docs/eval-results.md
Then  exit code is 0 and the section between the README markers matches the section between the docs/eval-results.md markers byte-for-byte (idempotency: running it twice produces no diff)

Given README.md exists
When  wc -l < README.md
Then  the line count is between 80 and 200 (scannable, single screen + a bit — per PRD § README shape)

Given the LICENSE file at repo root is Apache-2.0
When  github-linguist or GitHub's license-detect heuristic processes the repo
Then  License is recognized as Apache-2.0 (Devpost auto-detect requirement per ../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md)
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Required files exist
test -f README.md
test -f docs/assets/banner.png
test -f docs/assets/banner-dark.png
test -f scripts/build_banner.py
test -f docs/eval-results.md
test -f scripts/inline_eval_table.sh
test -f LICENSE
grep -q "Apache License" LICENSE

# 2. README shape — verbatim pitch + banner + video + arch diagram + 3 commands + eval markers + credits + license
grep -q "^# SplunkGate" README.md
grep -qF "SplunkGate — the runtime safety net every CISO needs before AI agents touch their Splunk data." README.md
grep -qE "docs/assets/banner\.png" README.md
grep -qE "docs/assets/banner-dark\.png" README.md
grep -qE "<picture>" README.md
grep -qE "youtube\.com/watch\?v=|youtu\.be/|vimeo\.com/" README.md
grep -qE "architecture_diagram\.png" README.md
grep -qE "architecture_diagram_dark\.png" README.md
test "$(awk '/^## Quick install/,/^## /' README.md | grep -cE '^(git clone|uv add|splunk install|pip install|curl)')" -eq 3
grep -qF "<!-- BEGIN eval-table -->" README.md
grep -qF "<!-- END eval-table -->" README.md
for credit in "MCP Watch" "Splunkbase 8765" "Cisco Security Cloud" "Splunkbase 7404" "DefenseClaw" "splunklib.ai" "NeMo Guardrails"; do
  grep -qF "$credit" README.md
done
grep -qF "Apache-2.0" README.md

# 3. Banner assets are valid PNGs of the right size
python -c "from PIL import Image; im = Image.open('docs/assets/banner.png'); assert im.size == (1280, 640), im.size; assert im.mode in ('RGB','RGBA'), im.mode"
python -c "from PIL import Image; im = Image.open('docs/assets/banner-dark.png'); assert im.size == (1280, 640), im.size; assert im.mode in ('RGB','RGBA'), im.mode"

# 4. Banner generator is deterministic
python scripts/build_banner.py --variant=light --out=/tmp/splunkgate-banner-a.png
python scripts/build_banner.py --variant=light --out=/tmp/splunkgate-banner-b.png
test "$(sha256sum /tmp/splunkgate-banner-a.png | awk '{print $1}')" = "$(sha256sum /tmp/splunkgate-banner-b.png | awk '{print $1}')"

# 5. Eval-table inliner is idempotent
cp README.md /tmp/splunkgate-readme-before.md
bash scripts/inline_eval_table.sh
bash scripts/inline_eval_table.sh
diff /tmp/splunkgate-readme-before.md README.md || true   # may differ once after first inline; second run must match first run
bash scripts/inline_eval_table.sh
cp README.md /tmp/splunkgate-readme-after.md
bash scripts/inline_eval_table.sh
diff /tmp/splunkgate-readme-after.md README.md            # second-pass diff must be empty

# 6. README is scannable (between 80 and 200 lines)
LINES=$(wc -l < README.md)
test "$LINES" -ge 80
test "$LINES" -le 200

# 7. LOC cap on banner generator
test "$(grep -cve '^\s*$' -e '^\s*#' scripts/build_banner.py)" -le 120

# 8. §14 carve-out — banner generator is not a "mock" in the production-judgment-path sense
git diff main...HEAD -- 'README.md' 'docs/assets/' 'scripts/' | grep -E "^\+" | grep -iE "(fake|dummy|hardcoded)" | grep -v "test\|spec\|banner\|placeholder" || true

# 9. License auto-detect — GitHub uses an Apache-2.0 SPDX hint in the LICENSE file header
head -3 LICENSE | grep -q "Apache License"
```

All blocks must exit 0 before opening the PR.

---

## Notes for coding agent

- Per `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md`, the README must include setup + run instructions, a public license (auto-detectable by GitHub — Apache-2.0 LICENSE already present at root), and link to the demo video and architecture diagram. These are pass/fail Stage One submission gates — missing any of them gets the project cut before scoring.
- Per `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md`, the demo video must be hosted on YouTube/Vimeo/Youku and be under 3 minutes. Use a real YouTube URL once `story-demo-01-screencast-and-script.md` produces the upload; until then, embed a placeholder URL of the form `https://youtube.com/watch?v=SPLUNKGATE_DEMO_PENDING` so the BDD check still passes and the orchestrator's `sahil-pr-audit` flags it before merge to main.
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, DNS Guard AI (Splunkbase 7922, 1st-place AI/ML winner 2025) shipped a `Images/banners/` folder containing `banner.png`, `banner.gif`, `banner.mp4`, `thumbnail.png`, plus `Images/architecture/` containing `architecture.png` + `architecture_dark.png`. Mirror the light+dark dual-variant pattern verbatim — judges remember this exact look-and-feel.
- Per `../../../context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md`, MCP Watch (Splunkbase app 8765, 17 downloads, by Alper Keske, released 2026-05) is the closest live shipping competitor for the audit surface — credit it explicitly in the README's credits section by name + Splunkbase number ("MCP Watch (Splunkbase 8765)") so the differentiation SplunkGate claims (runtime gating across Surfaces 1+2+3, which MCP Watch does not ship) is reviewable.
- Per `../../../context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md`, Cisco Security Cloud Splunkbase app 7404 v3.6.6 (Cisco Systems Inc., 55,544 downloads, released 2026-06-02) already populates `cisco_ai_defense:*` sourcetypes — credit it by name + Splunkbase number ("Cisco Security Cloud (Splunkbase 7404)") so the sourcetype-namespace ADR-005 design choice is auditable from the README.
- Per `docs/PRD.md` § README shape (§13), credits section lists: MCP Watch (8765), Cisco Security Cloud (7404), DefenseClaw, splunklib.ai, NeMo Guardrails. All five must appear by name in the credits paragraph; BDD criterion #8 enforces this.
- The eval-table transclusion pattern is the standard `<!-- BEGIN x -->` / `<!-- END x -->` HTML-comment markers that `scripts/inline_eval_table.sh` regex-matches. `eval/src/splunkgate_eval/report.py` (from story-eval-05) writes the same markers in `docs/eval-results.md`. The CI workflow `.github/workflows/eval.yml` (already exists from story-cicd-06) calls `inline_eval_table.sh` and commits the result on `main` only. PRs see stale tables; main always has fresh ones.
- Banner dimensions 1280×640 mirror DNS Guard's exact pixel size — preserves the visual cue judges associate with the 2025 winner. The DNS Guard `Images/banners/banner.png` is the literal reference; do not invent a different size.
- The Pillow generator must run without external network — Devpost judges build the repo from a clean checkout and we cannot assume an internet round-trip works during their review.
- Do NOT embed any Splunk or Cisco logo bitmaps. Devpost § "No unlicensed third-party trademarks" rule per `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md`. The banner is text + abstract gradient only.
- Do NOT shorten the credits paragraph by collapsing names. Every incumbent must be spelled out — the BDD `grep -qF` checks are exact-substring matches.
- This story's eval-table is the headline of the submission per `docs/eval-spec.md` § "Why this matters" — Technological Implementation is the tiebreaker criterion. The README's eval-table block is the single most-scored artifact in the entire repo.
- If `docs/eval-results.md` ships with `mock=true` annotations (because story-eval-05 ran with `SPLUNKGATE_AI_DEFENSE_MOCK=true`), the README's transcluded table inherits those annotations — this is correct per `docs/eval-spec.md` § "Honesty bar" and is NOT a story-readme-01 failure.
- The `<picture>` tag pattern for light/dark banner switching:
  ```html
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.png">
    <img src="docs/assets/banner.png" alt="SplunkGate — runtime safety net for AI agents in Splunk + Cisco environments" width="1280">
  </picture>
  ```
  GitHub respects this; light/dark renders correctly without JS.
- This story is ~2h because the README rewrite is small, but the banner generator + transclusion script + 15 BDD checks add real shell + Python surface. Do not under-scope it.
