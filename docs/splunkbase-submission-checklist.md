# Splunkbase Submission Checklist — SplunkGate

This checklist gates the SplunkGate app's Splunkbase submission. Every item
links the story that fulfils it + the verification command + the
expected output. Run the full checklist before opening a Splunkbase
listing.

Per `docs/architecture.md` § "Submission checklist gates" + the
hackathon scope note: **the Splunkbase submission itself is optional
for the hackathon, but the produced artifact is required**. The demo
video references "install via dist/splunkgate_app-X.Y.Z.tgz", so the
artifact must build cleanly and install on Splunk Cloud 10.4+.

---

## Pre-submission gates

- [ ] **1. AppInspect passes (zero unsuppressed error-severity findings)**
  - Owned by: story-app-11
  - Verify: `bash splunk_apps/splunkgate_app/scripts/run_appinspect.sh`
  - Expect: exit 0; `appinspect-summary.txt` reports "No unsuppressed blocking findings."
- [ ] **2. `META-INF/manifest.json` is present and version matches `default/app.conf`**
  - Owned by: this story (app-12)
  - Verify: `bash scripts/verify_splunkbase_artifact.sh dist/splunkgate_app-1.0.0.tgz`
  - Expect: exit 0; output includes "OK: ... passed all checks"
- [ ] **3. Extension-less `README` at app root**
  - Owned by: story-app-01 (skeleton)
  - Verify: `test -f splunk_apps/splunkgate_app/README`
  - Expect: exit 0
- [ ] **4. `LICENSE` at app root contains Apache-2.0 text**
  - Owned by: this story (app-12)
  - Verify: `head -5 splunk_apps/splunkgate_app/LICENSE | grep -E 'Apache License|Version 2.0'`
  - Expect: both substrings match
- [ ] **5. Icons present at the AppInspect-required sizes**
  - Owned by: story-app-09
  - Verify: `ls splunk_apps/splunkgate_app/static/appIcon{,_2x,Alt,Alt_2x}.png | wc -l`
  - Expect: `4`
- [ ] **6. Navigation XML present**
  - Owned by: story-app-02 (or app-01)
  - Verify: `test -f splunk_apps/splunkgate_app/default/data/ui/nav/default.xml`
  - Expect: exit 0
- [ ] **7. Build artifact is deterministic + free of dev cruft**
  - Owned by: this story (app-12)
  - Verify: `bash scripts/build_splunk_app_tgz.sh` runs twice; sha256 outputs match
  - Expect: identical sha256 between the two runs

## Submission attachments

- [ ] **8. Demo video URL referenced in the README**
  - Owned by: EPIC-11 (story-readme + story-demo)
  - Verify: `grep -E 'youtu\.be|youtube\.com|loom\.com' splunk_apps/splunkgate_app/README`
  - Expect: at least one demo video link
- [ ] **9. Evaluation results table referenced in the README**
  - Owned by: EPIC-10 + EPIC-11
  - Verify: `grep -i "eval results" splunk_apps/splunkgate_app/README`
  - Expect: at least one match
- [ ] **10. Supported Splunk versions match the Splunk Cloud demo target**
  - Owned by: this story (app-12) — encoded in `manifest.json` platformRequirements
  - Verify: `uv run python -c "import json; m=json.load(open('splunk_apps/splunkgate_app/META-INF/manifest.json')); assert m['platformRequirements']['splunk']['Cloud'].startswith('10.4')"`
  - Expect: exit 0

## Signing

Splunkbase signing has historically been server-side at ingestion; this
checklist does not include a client-side signing step. Splunk's app
signing service handles it post-upload. If a future Splunkbase release
moves to client-required signing, add a step here referencing
`META-INF/CERT.RSA` and the signing keypair location.

## Build artifact reference

The latest produced artifact location and metadata:

| Field | Value |
|---|---|
| Path | `dist/splunkgate_app-1.0.0.tgz` |
| Source of truth for version | `splunk_apps/splunkgate_app/default/app.conf` |
| SHA-256 | (re-run `bash scripts/build_splunk_app_tgz.sh` to print) |
| Splunk Enterprise floor | 9.4.0 |
| Splunk Cloud floor | 10.4.0 |

## Cross-references

- AppInspect compliance: `docs/stories/story-app-11-...md`
- Icon set: `docs/stories/story-app-09-static-icons-and-app-assets.md`
- Verify script: `scripts/verify_splunkbase_artifact.sh`
- Build script: `scripts/build_splunk_app_tgz.sh`
- Tarball helper (Python, cross-platform deterministic): `scripts/_pack_tarball.py`
