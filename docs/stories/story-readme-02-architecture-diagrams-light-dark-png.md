# Story — architecture_diagram.png + architecture_diagram_dark.png at repo root (Devpost submission artifact)

**ID:** story-readme-02-architecture-diagrams-light-dark-png
**Epic:** EPIC-11 — README + demo
**Depends on:** None
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Devpost judge (specifically the engineering-leaning Splunk-internal staff judges) who clicks on the repo and immediately looks for an architecture diagram
**I want to** find `architecture_diagram.png` (light variant) and `architecture_diagram_dark.png` (dark variant) at the repo root — not nested in `docs/` — showing the four surfaces (S1 middleware, S2 MCP server, S3 DefenseClaw, S4 Splunk app), the judgment layer (Cisco AI Defense + Foundation-Sec + Luna-2 stub), and the data flow from agent → judgment → OTel emit → Splunk HEC → Dashboard Studio v2 dashboards
**So that** the Devpost pass/fail Stage One submission check passes (architecture diagram is one of the named non-negotiable artifacts), the tiebreaker Technological Implementation criterion has a clean visual anchor, and the diagram source is regeneratable from a checked-in `.mmd` file so post-merge architecture changes don't drift away from the PNG

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `architecture_diagram.png` — NEW — light-variant PNG at the repo root (NOT in `docs/`, NOT nested). Per `../../../context/01-prizes-tracks.md`, filename pattern is verbatim `architecture_diagram.(md|pdf|png)` at root. Rendered from `docs/assets/architecture.mmd` via mermaid-cli (mmdc) using the default light theme. Dimensions ≥ 1600×900 (readable on a 27" monitor without zoom). PNG must include all four surfaces labelled S1–S4, the judgment layer labelled with the three named models (Cisco AI Defense, Foundation-Sec-1.1-8B-Instruct, Luna-2 stub), the OTel emit arrow labelled `gen_ai.evaluation.result`, the Splunk HEC arrow labelled `cisco_ai_defense:aegis_verdict` sourcetype, and the three dashboard names verbatim (Agent Risk Overview, Verdict Inspector, Regulator Evidence Pack).
- `architecture_diagram_dark.png` — NEW — dark-variant PNG at the repo root (same content, dark theme). Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, DNS Guard 2025 winner shipped light + dark variants of all visual assets — mirror this. Rendered from the same `docs/assets/architecture.mmd` source via mermaid-cli with the `dark` theme flag.
- `docs/assets/architecture.mmd` — NEW — single Mermaid source file (`flowchart LR` or `flowchart TB`, agent decides which reads better at 1600×900). Defines: agent client node → 4 surface nodes (S1 `aegis-mw`, S2 `aegis-mcp`, S3 DefenseClaw, S4 `aegis_app`) → judgment-layer subgraph (3 model nodes) → OTel emitter → Splunk HEC → 3 dashboard nodes. Comments at top of the file cite `docs/architecture.md` § "Repo structure" + § "API schemas" + ADR-005 (sourcetype) + ADR-007 (Luna-2 stub). Mermaid spec stable since v10.0.0; mermaid-cli 11.x renders this without breaking changes.
- `scripts/build_diagrams.sh` — NEW — POSIX sh build script (≤ 60 LOC). Renders both PNGs from the single `.mmd` source via `mmdc` (mermaid-cli). Two invocations: one for light, one for dark (via `-t dark` flag). Uses `puppeteer-config.json` for headless-chromium sandboxing flags (required on GitHub Actions runners — known mermaid-cli pitfall). Exits non-zero if `mmdc` is not on PATH or if either PNG fails to render. Re-run-safe: produces byte-identical output on identical input (mermaid-cli is deterministic given fixed theme + viewport).
- `scripts/puppeteer-config.json` — NEW — single JSON object `{"args": ["--no-sandbox", "--disable-setuid-sandbox"]}` consumed by mermaid-cli on Linux runners.
- `.github/workflows/diagrams.yml` — NEW — GitHub Actions workflow that runs `scripts/build_diagrams.sh` on every push to `main` that touches `docs/assets/architecture.mmd`, and commits the regenerated PNGs back to the same branch via the standard `stefanzweifel/git-auto-commit-action` pattern. Workflow runs `mmdc --version` first; fails fast if mermaid-cli install failed. Optional pre-merge job runs the script in dry-run mode on PRs that touch the `.mmd` to verify the source still renders, but does not commit on PRs.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the repo root
When  test -f architecture_diagram.png runs
Then  exit code is 0 (light variant at repo root — non-negotiable Devpost submission requirement per ../../../context/01-prizes-tracks.md)

Given the repo root
When  test -f architecture_diagram_dark.png runs
Then  exit code is 0 (dark variant at repo root — DNS Guard 2025 pattern per ../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md)

Given architecture_diagram.png exists
When  python -c "from PIL import Image; im = Image.open('architecture_diagram.png'); w,h = im.size; assert w >= 1600 and h >= 900, (w,h)" runs
Then  exit code is 0 (light variant readable at 27" monitor scale)

Given architecture_diagram_dark.png exists
When  python -c "from PIL import Image; im = Image.open('architecture_diagram_dark.png'); w,h = im.size; assert w >= 1600 and h >= 900, (w,h)" runs
Then  exit code is 0 (dark variant readable at 27" monitor scale)

Given docs/assets/architecture.mmd exists
When  grep -cE "^(flowchart|graph)" docs/assets/architecture.mmd runs
Then  count is exactly 1 (single Mermaid diagram declaration)

Given docs/assets/architecture.mmd exists
When  grep -cE "aegis-mw|aegis-mcp|DefenseClaw|aegis_app" docs/assets/architecture.mmd runs
Then  count is >= 4 (all four surfaces named verbatim per docs/architecture.md § "Repo structure")

Given docs/assets/architecture.mmd exists
When  grep -cE "Cisco AI Defense|Foundation-Sec|Luna-2" docs/assets/architecture.mmd runs
Then  count is >= 3 (all three judgment-layer models named per docs/architecture.md § "Judgment layer")

Given docs/assets/architecture.mmd exists
When  grep -cE "gen_ai\.evaluation\.result|cisco_ai_defense:aegis_verdict" docs/assets/architecture.mmd runs
Then  count is >= 2 (OTel event name + sourcetype both labelled — per docs/architecture.md § "OTel emission shape" + ADR-005)

Given docs/assets/architecture.mmd exists
When  grep -cE "Agent Risk Overview|Verdict Inspector|Regulator Evidence Pack" docs/assets/architecture.mmd runs
Then  count is >= 3 (three dashboards named verbatim per docs/PRD.md § Demo moment)

Given scripts/build_diagrams.sh exists
When  bash -n scripts/build_diagrams.sh runs (syntax check)
Then  exit code is 0

Given scripts/build_diagrams.sh exists and mmdc is on PATH
When  bash scripts/build_diagrams.sh runs against a clean checkout
Then  exit code is 0 and both architecture_diagram.png and architecture_diagram_dark.png are regenerated

Given scripts/build_diagrams.sh ran once
When  it runs a second time on unchanged source
Then  the resulting PNGs are byte-identical to the first run (deterministic output — sha256 equal across runs)

Given scripts/puppeteer-config.json exists
When  python -c "import json; cfg = json.load(open('scripts/puppeteer-config.json')); assert '--no-sandbox' in cfg['args']" runs
Then  exit code is 0 (headless-chromium runner-safe flag present)

Given .github/workflows/diagrams.yml exists
When  python -c "import yaml; yaml.safe_load(open('.github/workflows/diagrams.yml'))" runs
Then  exit code is 0 (valid YAML)

Given .github/workflows/diagrams.yml exists
When  grep -cE "scripts/build_diagrams\.sh|mermaid-cli|mmdc" .github/workflows/diagrams.yml runs
Then  count is >= 2 (workflow actually invokes the build script with mermaid-cli)
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 0. mermaid-cli installed (one-time setup; CI workflow installs in its own job)
command -v mmdc >/dev/null || npm install -g @mermaid-js/mermaid-cli@latest

# 1. Required files exist
test -f architecture_diagram.png
test -f architecture_diagram_dark.png
test -f docs/assets/architecture.mmd
test -f scripts/build_diagrams.sh
test -f scripts/puppeteer-config.json
test -f .github/workflows/diagrams.yml

# 2. Files at repo root — NOT in docs/, NOT nested
test "$(dirname architecture_diagram.png)" = "."
test "$(dirname architecture_diagram_dark.png)" = "."

# 3. PNGs are valid + readable size
python -c "from PIL import Image; im = Image.open('architecture_diagram.png'); w,h = im.size; assert w >= 1600 and h >= 900, (w,h); assert im.mode in ('RGB','RGBA'), im.mode"
python -c "from PIL import Image; im = Image.open('architecture_diagram_dark.png'); w,h = im.size; assert w >= 1600 and h >= 900, (w,h); assert im.mode in ('RGB','RGBA'), im.mode"

# 4. Mermaid source covers the architecture surface verbatim
grep -cE "^(flowchart|graph)" docs/assets/architecture.mmd | grep -qx 1
for surface in "aegis-mw" "aegis-mcp" "DefenseClaw" "aegis_app"; do
  grep -qF "$surface" docs/assets/architecture.mmd
done
for model in "Cisco AI Defense" "Foundation-Sec" "Luna-2"; do
  grep -qF "$model" docs/assets/architecture.mmd
done
grep -qF "gen_ai.evaluation.result" docs/assets/architecture.mmd
grep -qF "cisco_ai_defense:aegis_verdict" docs/assets/architecture.mmd
for dash in "Agent Risk Overview" "Verdict Inspector" "Regulator Evidence Pack"; do
  grep -qF "$dash" docs/assets/architecture.mmd
done

# 5. Build script syntactically valid + executable
bash -n scripts/build_diagrams.sh
test -x scripts/build_diagrams.sh || chmod +x scripts/build_diagrams.sh

# 6. Build script regenerates both PNGs deterministically
bash scripts/build_diagrams.sh
SHA_LIGHT_1=$(sha256sum architecture_diagram.png | awk '{print $1}')
SHA_DARK_1=$(sha256sum architecture_diagram_dark.png | awk '{print $1}')
bash scripts/build_diagrams.sh
SHA_LIGHT_2=$(sha256sum architecture_diagram.png | awk '{print $1}')
SHA_DARK_2=$(sha256sum architecture_diagram_dark.png | awk '{print $1}')
test "$SHA_LIGHT_1" = "$SHA_LIGHT_2"
test "$SHA_DARK_1" = "$SHA_DARK_2"

# 7. Puppeteer config has the right sandboxing flag
python -c "import json; cfg = json.load(open('scripts/puppeteer-config.json')); assert '--no-sandbox' in cfg['args'], cfg"

# 8. GitHub Actions workflow is valid YAML and invokes the script
python -c "import yaml; yaml.safe_load(open('.github/workflows/diagrams.yml'))"
grep -qE "scripts/build_diagrams\.sh|mmdc" .github/workflows/diagrams.yml

# 9. LOC cap on build script
test "$(grep -cve '^\s*$' -e '^\s*#' scripts/build_diagrams.sh)" -le 60

# 10. §14 carve-out — diagram artifacts are submission deliverables, not mock data; ensure no spurious "mock"/"fake" tokens leak
git diff main...HEAD -- 'architecture_diagram*.png' 'docs/assets/architecture.mmd' 'scripts/' '.github/workflows/diagrams.yml' | grep -E "^\+" | grep -iE "(mock|fake|dummy|hardcoded|simulated)" | grep -v "test\|spec\|comment" || true
```

All ten blocks must exit 0 before opening the PR.

---

## Notes for coding agent

- Per `../../../context/01-prizes-tracks.md`, the architecture diagram filename MUST be `architecture_diagram.(md|pdf|png)` at the repo root — NOT in `docs/`, NOT nested. We pick `.png` because Devpost judges open it inline without a viewer (PDF requires a download click) and Markdown auto-renders less reliably in the preview pane. Light + dark variant filenames mirror the DNS Guard pattern (see next bullet).
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, DNS Guard 2025 winner (Splunkbase 7922, 1st-place AI/ML) shipped `Images/architecture/architecture.png` + `Images/architecture/architecture_dark.png` from a single `architecture.drawio` source. We use Mermaid instead of drawio because: (a) Mermaid source is plain-text and grep-friendly so BDD checks #5–#9 can verify content without parsing binary, (b) mermaid-cli is npm-installable with no GUI dependency, (c) drawio's CLI requires an X server which doesn't run on GitHub Actions runners without extra setup. The visual look-and-feel mirrors DNS Guard's dual-variant pattern even if the source format differs.
- Per `docs/architecture.md` § "Repo structure", the four surfaces are `aegis-mw` (S1), `aegis-mcp` (S2), DefenseClaw (S3), `aegis_app` (S4) — use these exact names in the Mermaid node labels. The eval BDD criterion #6 grep-checks each by literal substring.
- Per `docs/architecture.md` § "Judgment layer", the three models are Cisco AI Defense, Foundation-Sec-1.1-8B-Instruct, and Luna-2 (stub per ADR-007). The diagram should visually mark Luna-2 as dashed-border / "future" so judges see the realistic-honesty signal — Cisco hasn't published a Luna-2 SDK yet.
- Per `docs/architecture.md` § "OTel emission shape", the emit-event name is `gen_ai.evaluation.result` — quote it verbatim as an edge label in the Mermaid. Per `docs/architecture.md` § "ADR-005", events land in `cisco_ai_defense:aegis_verdict` sourcetype — also verbatim as an edge label downstream of the OTel emitter, before the HEC arrow into Splunk.
- Per `docs/PRD.md` § "Demo moment", the three dashboard names are verbatim "Agent Risk Overview", "Verdict Inspector", "Regulator Evidence Pack" — use these exact strings in the Mermaid node labels for the three terminal nodes. BDD criterion #9 grep-checks each.
- Mermaid theme switching for dark variant: `mmdc -t dark -i input.mmd -o output.png` produces a dark-theme rendering of the same source. The light variant is the default theme. Use the same source `.mmd` for both — single source of truth for content.
- Mermaid-cli viewport: pass `-w 1920 -H 1080` (or higher) so the PNG dimensions exceed the 1600×900 BDD threshold without manual scaling. Higher resolution is fine; smaller fails BDD criteria #3 and #4.
- Puppeteer/headless-chromium pitfall on Linux runners: without `--no-sandbox --disable-setuid-sandbox` flags, mermaid-cli silently fails with a non-zero exit and an opaque error. The `scripts/puppeteer-config.json` file is mermaid-cli's documented way to pass these flags. Local macOS dev doesn't need them but the GitHub Actions workflow does.
- Build script determinism: mermaid-cli output is deterministic given fixed input + fixed theme + fixed viewport. BDD criterion #12 enforces this by comparing sha256s across two runs. If determinism breaks (mermaid-cli version drift), pin the version in `.github/workflows/diagrams.yml` via `npm install -g @mermaid-js/mermaid-cli@<exact-version>`.
- The `.github/workflows/diagrams.yml` workflow regenerates the PNGs on push to main that touches `docs/assets/architecture.mmd`. This is intentional separation from the always-on `ci.yml` workflow — we don't want every PR to re-render the diagram (slow + introduces merge-conflict churn on the binary PNG); we only re-render on the source-of-truth change.
- This story has NO upstream story dependency in `sprint-status.yaml` (`depends_on: []`) — it can run in parallel with everything else. Diagram content is fully specified by `docs/architecture.md` which is already DRAFT-locked.
- Do NOT add Splunk or Cisco logos to the diagram. Per `../../../context/01-prizes-tracks.md` § Demo video rules, "no unlicensed third-party trademarks" — this rule extends to the architecture diagram which sits next to the demo video as a submission artifact. Use plain text + Mermaid's default node shapes only.
- Do NOT create a `docs/assets/architecture.drawio` source — the deliverable is the `.mmd` (grep-friendly, single source of truth). If someone wants a drawio version later, they can convert from the PNG.
- This story is ~2h because the Mermaid source + dual-variant render + deterministic build + CI workflow + 15 BDD checks together add real surface. The actual diagram content is mostly translation of `docs/architecture.md` into Mermaid syntax — not new architecture work.
