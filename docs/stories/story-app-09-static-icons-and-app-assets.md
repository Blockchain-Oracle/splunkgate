# Story — Static app icons (appIcon, appIconAlt, 2x variants)

**ID:** story-app-09-static-icons-and-app-assets
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-01-app-conf-and-metadata-skeleton
**Estimate:** ~1h
**Status:** PENDING

---

## User story

**As a** Splunk admin browsing the Splunk Web Apps menu after installing aegis_app
**I want to** see a distinct Aegis app icon (and a 2x hi-DPI variant) in the launcher and an alternate icon on the App: Manager page, instead of the generic Splunk app placeholder
**So that** the app is visually identifiable in production, passes AppInspect's icon-required check, and meets Splunkbase submission asset requirements without needing a designer in the loop for v1

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/aegis_app/static/appIcon.png` — NEW — 36x36 PNG icon (Splunk's required launcher size per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`). Programmatically generated via PIL: dark navy background (#1A1C20 matching the dashboard theme), centered shield-or-A glyph in Splunk blue (#1A8FFF), no text. Acceptable for v1 per the story brief.
- `splunk_apps/aegis_app/static/appIcon_2x.png` — NEW — 72x72 PNG (2x hi-DPI variant; same design, doubled resolution).
- `splunk_apps/aegis_app/static/appIconAlt.png` — NEW — 36x36 PNG used on the App: Manager page (slightly different — Splunk renders this on a light background, so this variant has a light surface (#F8F9FA) with the same shield-or-A glyph in Splunk blue).
- `splunk_apps/aegis_app/static/appIconAlt_2x.png` — NEW — 72x72 PNG (2x hi-DPI variant of appIconAlt).
- `splunk_apps/aegis_app/static/screenshot.png` — NEW — 1280x720 PNG screenshot for Splunkbase listing; programmatically generated placeholder showing the app name + "Real-time AI agent safety verdicts" tagline on the dashboard dark background, replaced by a real dashboard screenshot in story-app-12 (Splunkbase submission prep). Story-app-12 owns the swap; this story owns the placeholder.
- `scripts/generate_app_icons.py` — NEW — Python script (~80 LOC, ≤ 400) using PIL/Pillow that generates the 4 icon files + the screenshot placeholder deterministically from a single source spec. Reproducibility hatch: committed PNGs are the canonical artifacts; the script lets future contributors regenerate when the brand evolves. Script lives in `scripts/` (outside the app dir, so no Python ships inside `splunk_apps/aegis_app/` per the DNS Guard winning pattern).

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/static/appIcon.png exists
When  python -c "from PIL import Image; im = Image.open('splunk_apps/aegis_app/static/appIcon.png'); print(im.size)" runs
Then  output is "(36, 36)"

Given splunk_apps/aegis_app/static/appIcon_2x.png exists
When  python -c "from PIL import Image; im = Image.open(...); print(im.size)" runs
Then  output is "(72, 72)"

Given splunk_apps/aegis_app/static/appIconAlt.png exists
When  python -c "from PIL import Image; im = Image.open(...); print(im.size)" runs
Then  output is "(36, 36)"

Given splunk_apps/aegis_app/static/appIconAlt_2x.png exists
When  python -c "from PIL import Image; im = Image.open(...); print(im.size)" runs
Then  output is "(72, 72)"

Given splunk_apps/aegis_app/static/screenshot.png exists
When  python -c "from PIL import Image; im = Image.open(...); print(im.size)" runs
Then  output dimensions >= (1280, 720)

Given each PNG file
When  file <icon>.png runs
Then  output contains "PNG image data" (not corrupted)

Given each PNG file
When  python -c "from PIL import Image; im = Image.open(...); print(im.mode)" runs
Then  the mode is "RGBA" or "RGB" (valid PNG color mode, Splunk renders both)

Given scripts/generate_app_icons.py exists
When  python scripts/generate_app_icons.py --output-dir /tmp/icon_test runs
Then  exit code is 0
And   the four icon files appear in /tmp/icon_test
And   md5sum of generated files matches the committed PNGs (deterministic generation)

Given scripts/generate_app_icons.py
When  wc -l runs
Then  output <= 400

Given splunk-appinspect runs against splunk_apps/aegis_app/
When  the output is parsed
Then  zero "error"-severity findings against tags app_icon_required, app_icon_correct_dimensions, app_alt_icon_present
```

---

## Shell verification

```bash
set -euo pipefail

# 1. All four icon files + screenshot exist
test -f splunk_apps/aegis_app/static/appIcon.png
test -f splunk_apps/aegis_app/static/appIcon_2x.png
test -f splunk_apps/aegis_app/static/appIconAlt.png
test -f splunk_apps/aegis_app/static/appIconAlt_2x.png
test -f splunk_apps/aegis_app/static/screenshot.png

# 2. PIL verifies dimensions
uv run python - <<'PY'
from PIL import Image
expected = {
    "splunk_apps/aegis_app/static/appIcon.png": (36, 36),
    "splunk_apps/aegis_app/static/appIcon_2x.png": (72, 72),
    "splunk_apps/aegis_app/static/appIconAlt.png": (36, 36),
    "splunk_apps/aegis_app/static/appIconAlt_2x.png": (72, 72),
}
for path, want in expected.items():
    im = Image.open(path)
    assert im.size == want, f"{path}: got {im.size}, want {want}"
    assert im.mode in ("RGB", "RGBA"), f"{path}: mode {im.mode} not valid"
# Screenshot >= 1280x720
ss = Image.open("splunk_apps/aegis_app/static/screenshot.png")
assert ss.size[0] >= 1280 and ss.size[1] >= 720, f"Screenshot too small: {ss.size}"
print("All icon dimensions + modes valid.")
PY

# 3. PNG signature check
for f in splunk_apps/aegis_app/static/appIcon.png splunk_apps/aegis_app/static/appIcon_2x.png splunk_apps/aegis_app/static/appIconAlt.png splunk_apps/aegis_app/static/appIconAlt_2x.png splunk_apps/aegis_app/static/screenshot.png; do
  file "$f" | grep -q "PNG image data"
done

# 4. Deterministic regeneration round-trip
test -f scripts/generate_app_icons.py
mkdir -p /tmp/icon_test
uv run python scripts/generate_app_icons.py --output-dir /tmp/icon_test
for f in appIcon.png appIcon_2x.png appIconAlt.png appIconAlt_2x.png; do
  test -f "/tmp/icon_test/$f"
  # md5sum determinism — committed icons should byte-match regenerated
  committed=$(md5sum "splunk_apps/aegis_app/static/$f" | cut -d' ' -f1)
  regenerated=$(md5sum "/tmp/icon_test/$f" | cut -d' ' -f1)
  test "$committed" = "$regenerated" || { echo "non-deterministic generation: $f"; exit 1; }
done
rm -rf /tmp/icon_test

# 5. LOC sanity
test "$(wc -l < scripts/generate_app_icons.py)" -le 400

# 6. AppInspect
uv run splunk-appinspect inspect splunk_apps/aegis_app/ --mode test --included-tags cloud \
  --output-file appinspect-report.json --data-format json
python - <<'PY'
import json, sys
r = json.load(open("appinspect-report.json"))
errors = [c for rep in r.get("reports", []) for g in rep.get("groups", []) for c in g.get("checks", []) if c.get("result") == "error"]
icon_errors = [e for e in errors if "icon" in (e.get("name","") + " ".join(str(m) for m in e.get("messages",[]))).lower()]
if errors:
    print("All errors:", [(e.get("name"), e.get("messages")) for e in errors[:10]])
if icon_errors:
    print("ICON errors:", icon_errors); sys.exit(1)
PY
```

All six blocks must exit 0 before opening the PR.

---

## Notes for coding agent

- Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`, Splunk requires `static/appIcon.png` (36x36) AND `static/appIcon_2x.png` (72x72) for AppInspect's `app_icon_required` + `app_icon_correct_dimensions` checks. `appIconAlt.png` + `appIconAlt_2x.png` are required for Splunk's "App: Manager" page display.
- Per the story brief, "placeholder icons generated programmatically (PIL or similar) acceptable for v1." Do NOT spend time hand-designing in Figma — a clean PIL-rendered shield-or-A glyph on a Splunk-blue background reads as professional and ships fast.
- Per `docs/ux-spec.md` § "Design tokens", the brand colors are: dark background `#1A1C20`, light surface `#F8F9FA`, primary action `#1A8FFF` (Splunk blue). Use these exact hex values in the PIL script — do not introduce new brand colors.
- `appIcon.png` (used in dark-theme launcher) = dark navy `#1A1C20` background + `#1A8FFF` Splunk-blue glyph. `appIconAlt.png` (used on App: Manager light-background page) = light `#F8F9FA` background + `#1A8FFF` glyph. Same glyph, inverted surface.
- The glyph itself: a simple shield outline (an Aegis is a shield in Greek mythology — apt) OR a stylized "A" inside a circle. Either works; pick whichever the script generates more legibly at 36x36. Don't add text — at 36x36, text is illegible.
- Use PIL's `ImageDraw` (`pip install Pillow` via `uv add --dev Pillow` if not already in the toolchain). Generate to RGBA mode with a transparent canvas, draw the shape, save as PNG with `optimize=True` for size.
- Determinism: PIL output is deterministic when input is identical. Make sure the script doesn't use any time-based or random inputs (no `time.time()`, no `random.seed()`). MD5 hash of generated PNGs should be stable across runs. The shell verification block 4 enforces this.
- `screenshot.png` is the Splunkbase listing image; minimum 1280x720 per Splunkbase submission docs. The placeholder shows: dark background, large "Aegis" wordmark in Splunk Sans, "Real-time AI agent safety verdicts" tagline beneath. Story-app-12 swaps this for an actual dashboard screenshot before Splunkbase submission. Don't over-invest in the placeholder.
- `scripts/generate_app_icons.py` lives OUTSIDE `splunk_apps/aegis_app/` to preserve the DNS Guard "zero Python in app dir" pattern per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`. The script's job is to regenerate icons at build time if a designer eventually replaces the glyph spec; until then, the committed PNGs are the canonical artifacts.
- The script CLI: `python scripts/generate_app_icons.py --output-dir <path>` — outputs the 4 icon files and screenshot.png into `<path>`. Default `<path>` = `splunk_apps/aegis_app/static/`. Easy to call from CI for regeneration verification.
- Do NOT add the icons as raw binary base64 in the PR description — large binary diffs are fine in git, just don't paste them. Git's binary diff handles PNGs cleanly.
- AppInspect tag `app_icon_correct_dimensions` is strict — 36x36 and 72x72 exactly, not 32x32 or 64x64. Verify with `python -c "from PIL import Image; print(Image.open(...).size)"` before committing.
- If `Pillow` is not in the dev toolchain yet, add via `uv add --dev Pillow` (Pillow is the maintained fork of PIL). Document in PR description.
- The 5th file `screenshot.png` is technically not required at AppInspect time (it's a Splunkbase submission asset), but adding it here saves a story-app-12 churn cycle. AppInspect ignores extra files in `static/`.
- This story is intentionally small (~1h). Do not bundle the brand-redesign upgrade scope — that's a separate post-hackathon story.
