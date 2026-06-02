# Story — Splunkbase submission package (build_splunk_app_tgz.sh) + submission checklist doc

**ID:** story-app-12-splunkbase-submission-package-and-checklist
**Epic:** EPIC-12 — AppInspect hardening
**Depends on:** story-app-11-appinspect-expect-yaml-and-manual-checks
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** Splunk Build-a-thon-style judge who wants to see Aegis's Splunk app installed locally to demo it
**I want to** run a single `scripts/build_splunk_app_tgz.sh` invocation that produces a Splunkbase-ready `.tar.gz` artifact in `dist/aegis_app-<version>.tar.gz` matching the conventions in `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`, and read `docs/splunkbase-submission-checklist.md` to confirm every Splunkbase requirement is met
**So that** Splunkbase submission is unblocked post-hackathon and the build artifact is reproducible from the repo — the submission itself is OPTIONAL for the hackathon but the artifact is required per the spec

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `scripts/build_splunk_app_tgz.sh` — NEW — bash script: validates `splunk_apps/aegis_app/default/app.conf` has a `version = X.Y.Z` line (semver), reads that version, strips dev cruft (`__pycache__/`, `.pytest_cache/`, `*.pyc`, `.DS_Store`, `tests/`, `.appinspect.*.yaml.bak`, `appinspect-report.json`, etc.), runs AppInspect once (via story-app-11's `run_appinspect.sh`) to confirm zero-error pre-flight, then creates `dist/aegis_app-<version>.tar.gz` via `tar -czf dist/aegis_app-<version>.tar.gz -C splunk_apps aegis_app/` from the repo root. Computes and prints sha256 + size of the resulting artifact. Exit 1 if app.conf version line is missing or non-semver, or if AppInspect fails.
- `scripts/_strip_dev_cruft.sh` — NEW — bash helper invoked by `build_splunk_app_tgz.sh` that walks `splunk_apps/aegis_app/` and removes dev-only files (listed in a stable inline allowlist of patterns) before packaging. Idempotent. Logs which files were removed.
- `splunk_apps/aegis_app/META-INF/manifest.json` — NEW — Splunk-standard app manifest per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`. Fields per the documented schema (see Notes): `schemaVersion`, `info.id`, `info.title`, `info.version`, `info.author`, `info.license`, `info.releaseDate`, `info.description`, `info.classification.intendedAudience`, `info.classification.categories`, `info.classification.developmentStatus`, `dependencies`, `targetWorkloads` (`["_search_head_instances"]`). Match the `app.conf` version field exactly.
- `docs/splunkbase-submission-checklist.md` — NEW — markdown document containing the full Splunkbase submission checklist: (1) AppInspect green, (2) `manifest.json` present and valid, (3) `README` (extension-less) at app root, (4) `LICENSE` references Apache-2.0, (5) `static/appIcon*.png` icons present in 4 sizes per story-app-09, (6) `default/data/ui/nav/default.xml` exists, (7) signing manifest (if Splunkbase requires — see Notes), (8) eval results table referenced in README, (9) demo video URL, (10) supported Splunk versions verified against `app.conf`. Each item has a verification command and an expected output.
- `scripts/verify_splunkbase_artifact.sh` — NEW — runs the artifact end-to-end checks: extracts the tarball to a temp dir, runs `splunk-appinspect inspect <extracted>/aegis_app --included-tags cloud`, validates manifest.json schema (Pydantic model `eval/.../manifest_schema.py` or inline Python), checks for the required README + LICENSE files in the extracted tree. Exit 0 if all pass. Used by `release.yml` (story-cicd-08).
- `tests/test_build_artifact.py` — NEW (at repo root tests dir, per existing CI pattern) — ≥ 10 tests: `build_splunk_app_tgz.sh` produces `dist/aegis_app-<version>.tar.gz`; the produced archive contains `aegis_app/default/app.conf`; contains `aegis_app/README`; contains `aegis_app/META-INF/manifest.json`; does NOT contain `__pycache__/` or `*.pyc`; does NOT contain `tests/`; the version in `manifest.json` equals the version in `app.conf`; the version string matches semver regex; the script runs idempotently (second invocation produces an artifact with the same sha256); `verify_splunkbase_artifact.sh` exits 0 on a freshly built artifact.
- `splunk_apps/aegis_app/LICENSE` — NEW (or symlink) — Apache-2.0 license file at the app root (required by Splunkbase per the submission checklist).

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/META-INF/manifest.json exists
When  `python -c "import json; d=json.load(open('splunk_apps/aegis_app/META-INF/manifest.json')); print(d['info']['id'], d['info']['version'])"` runs
Then  exit code is 0
And   output starts with "aegis_app "

Given splunk_apps/aegis_app/META-INF/manifest.json and splunk_apps/aegis_app/default/app.conf
When  versions are compared
Then  manifest.json's info.version equals app.conf's `version =` value byte-equal

Given `bash scripts/build_splunk_app_tgz.sh` runs from the repo root
When  it completes
Then  exit code is 0
And   a single tarball matching `dist/aegis_app-*.tar.gz` exists
And   the printed sha256 is a 64-character hex string

Given the produced tarball
When  `tar -tzf dist/aegis_app-*.tar.gz | head -20` runs
Then  the listing includes `aegis_app/default/app.conf`
And   includes `aegis_app/README`
And   includes `aegis_app/META-INF/manifest.json`
And   does not include `__pycache__`, `*.pyc`, `.DS_Store`, or `tests/`

Given the produced tarball
When  `bash scripts/verify_splunkbase_artifact.sh dist/aegis_app-*.tar.gz` runs
Then  exit code is 0

Given the build script is run twice on a clean tree
When  the two sha256 outputs are compared
Then  they are equal (deterministic tarball under the same source tree)

Given docs/splunkbase-submission-checklist.md exists
When  it is grepped for the verbatim line patterns
Then  it contains the substring "AppInspect"
And   contains "Apache-2.0"
And   contains "manifest.json"
And   contains "README"
And   contains "appIcon"
And   contains "demo video"
And   contains "eval results"

Given the LICENSE file at splunk_apps/aegis_app/LICENSE
When  the first 5 lines are read
Then  it contains the substring "Apache License" and "Version 2.0"

Given `uv run pytest tests/test_build_artifact.py -v`
When  it runs
Then  >= 10 tests pass and 0 fail

Given every modified or new file
When  `wc -l` is run
Then  each file is <= 400 LOC
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Manifest exists and parses, version matches app.conf
test -f splunk_apps/aegis_app/META-INF/manifest.json
uv run python - <<'PY'
import json, re
m = json.load(open("splunk_apps/aegis_app/META-INF/manifest.json"))
assert m["info"]["id"] == "aegis_app", m["info"]
mv = m["info"]["version"]
av = None
for line in open("splunk_apps/aegis_app/default/app.conf"):
    if line.startswith("version = "):
        av = line.strip().split(" = ", 1)[1]
        break
assert av == mv, f"app.conf version {av} != manifest version {mv}"
assert re.match(r"^\d+\.\d+\.\d+$", mv), mv
print("OK")
PY

# 2. LICENSE file present + Apache-2.0
test -f splunk_apps/aegis_app/LICENSE
head -5 splunk_apps/aegis_app/LICENSE | grep -q 'Apache License'
head -5 splunk_apps/aegis_app/LICENSE | grep -q 'Version 2.0'

# 3. Build script produces deterministic artifact
chmod +x scripts/build_splunk_app_tgz.sh
rm -rf dist
bash scripts/build_splunk_app_tgz.sh
sha_a=$(find dist -name 'aegis_app-*.tar.gz' -exec sha256sum {} \; | awk '{print $1}')
n=$(find dist -name 'aegis_app-*.tar.gz' | wc -l)
[ "$n" -eq 1 ] || { echo "FAIL: expected 1 tarball, got $n"; exit 1; }

# 4. Tarball contents are clean
artifact=$(find dist -name 'aegis_app-*.tar.gz' | head -1)
tar -tzf "$artifact" | grep -q 'aegis_app/default/app.conf'
tar -tzf "$artifact" | grep -q 'aegis_app/README'
tar -tzf "$artifact" | grep -q 'aegis_app/META-INF/manifest.json'
! tar -tzf "$artifact" | grep -E '__pycache__|\.pyc$|\.DS_Store|/tests/' || { echo "FAIL: dev cruft in artifact"; exit 1; }

# 5. Verify script passes
chmod +x scripts/verify_splunkbase_artifact.sh
bash scripts/verify_splunkbase_artifact.sh "$artifact"

# 6. Deterministic — second build produces same sha256
rm -rf dist
bash scripts/build_splunk_app_tgz.sh
sha_b=$(find dist -name 'aegis_app-*.tar.gz' -exec sha256sum {} \; | awk '{print $1}')
[ "$sha_a" = "$sha_b" ] || { echo "FAIL: non-deterministic build: $sha_a vs $sha_b"; exit 1; }

# 7. Checklist doc mentions every required item
for item in AppInspect Apache-2.0 manifest.json README appIcon 'demo video' 'eval results'; do
  grep -q "$item" docs/splunkbase-submission-checklist.md || { echo "FAIL: checklist missing '$item'"; exit 1; }
done

# 8. Tests pass
uv run pytest tests/test_build_artifact.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# 9. 400-LOC cap
for f in \
  scripts/build_splunk_app_tgz.sh \
  scripts/_strip_dev_cruft.sh \
  scripts/verify_splunkbase_artifact.sh \
  splunk_apps/aegis_app/META-INF/manifest.json \
  docs/splunkbase-submission-checklist.md \
  tests/test_build_artifact.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
echo "ALL CHECKS PASS"
```

---

## Notes for coding agent

- **Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md` (the canonical packaging doc)**: every Splunkbase-targeted app requires `default/app.conf`, `metadata/default.meta`, an extension-less `README` at app root, and (for modern submissions) a `META-INF/manifest.json` that mirrors the `app.conf` declarations in JSON form. The `manifest.json` schema and field list are documented in the spec file — read it before authoring the manifest. If the spec doc enumerates a different field set than this story lists, follow the spec doc.
- **Per `docs/architecture.md` § "Submission checklist gates"**, the Aegis-specific gates are: (a) `splunk-appinspect inspect splunk_apps/aegis_app/` passes with zero error-severity findings (this gate is implemented by story-app-11 + this story's `verify_splunkbase_artifact.sh`); (b) `LICENSE` file is Apache-2.0 at the app root; (c) `README` extension-less file at app root. All three must be present in the produced tarball.
- **Per the spec: "The submission is OPTIONAL for hackathon but the build artifact is required."** The tarball is what the demo video will reference ("install this by uploading to Splunk Web > Manage Apps > Install from file") — judges may verify the install works. The Splunkbase submission itself is post-hackathon.
- **Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`**, CIMplicity AI ships as a Splunkbase release; DNS Guard AI same. Both are TGZ distributions. The TGZ root contains the `aegis_app/` directory (NOT bare conf files at the top level). This is what `tar -czf ... -C splunk_apps aegis_app/` produces — the `-C splunk_apps` strips the `splunk_apps/` parent prefix.
- **Signing manifest**: Splunkbase historically did not require code signing for community apps. Newer Splunk Cloud deployment paths may require Splunk's app-signing service (server-side). Verify against `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md` whether signing is required at submission upload time — if yes, the `META-INF/manifest.json` is the input; if not, document in the checklist that signing happens server-side at Splunkbase ingestion. Do not invent a `META-INF/CERT.RSA` file out of nothing.
- **Deterministic tarball**: by default, `tar` includes mtimes from the filesystem, breaking determinism. Use `--mtime='UTC 2026-01-01'` + `--sort=name` + `--owner=0 --group=0 --numeric-owner` to produce a reproducible artifact. GNU tar supports all of these; BSD tar (macOS default) does not — script must check `tar --version` and either use GNU tar or `gtar` (Homebrew). If on macOS, install gtar via brew or fall back to `python -c "import tarfile; ..."` for determinism.
- **Version semver**: `app.conf` has `version = 1.0.0` per story-app-01. The manifest.json `info.version` must match exactly. The build script reads `app.conf` once, writes it into the tarball filename and the manifest, ensuring a single source of truth.
- **Per `docs/architecture.md` § "Repo structure" (line 117)**: `splunk_apps/aegis_app/` is the package root. The tarball must contain `aegis_app/` as the top-level directory inside the archive — Splunk expects this convention.
- **The checklist doc** is markdown — render as a numbered list with check-boxes (`- [ ]`). The acceptance criterion greps for specific keywords; the actual content can be more thorough. Cross-reference each item to the story that fulfills it (e.g., "appIcon — see story-app-09-static-icons-and-app-assets").
- **`verify_splunkbase_artifact.sh` is invoked by CI at release time** (per `docs/cicd-spec.md` story-cicd-08-release-pipeline-signed). The release workflow downloads the produced artifact and re-runs verification before publishing the GitHub Release. The script must accept the tarball path as `$1`.
- **`tests/test_build_artifact.py` at repo root**: per existing CI pattern (look at any existing top-level `tests/` directory in the repo skeleton from EPIC-02 / story-skel-01 — if none exists, this story creates the top-level `tests/` dir as part of its scope). The tests use `subprocess.run(["bash", "scripts/build_splunk_app_tgz.sh"], check=True)` and then inspect the produced artifact via `tarfile`.
- **Per `../../../context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md`**: Abu's verified Splunk Cloud instance runs 10.4.2604.5; `manifest.json` `info.classification.developmentStatus = "GA"` and the supported Splunk versions field includes 10.4 so the artifact installs on the demo target.
- Estimate breakdown: ~30 min build script + dev-cruft stripping + determinism, ~20 min manifest.json + LICENSE placement, ~20 min checklist doc, ~20 min verify script, ~20 min tests + verification.
