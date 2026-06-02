# Story — Splunk app conf + metadata skeleton (app.conf, default.meta, README)

**ID:** story-app-01-app-conf-and-metadata-skeleton
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** None
**Estimate:** ~1h
**Status:** PENDING

---

## User story

**As a** Splunk admin (or `splunk-appinspect`) installing the Aegis app on Splunk Cloud 10.4 or Enterprise 9.4+
**I want to** drop the `aegis_app` directory into `$SPLUNK_HOME/etc/apps/`, restart Splunkd, and see the app appear in the Apps menu with proper version + label + visibility
**So that** every downstream EPIC-09 story (props, savedsearches, dashboards) has a valid Splunk app skeleton to land in and the package passes the App Setup AppInspect checks

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/aegis_app/default/app.conf` — NEW — five stanzas: `[install]` (`is_configured = 0`, `state = enabled`, `build = 1`), `[launcher]` (`author = Aegis Project`, `description = <one-line pitch>`, `version = 1.0.0`), `[ui]` (`is_visible = 1`, `label = Aegis — Agentic AI Safety`), `[package]` (`id = aegis_app`, `check_for_updates = true`), `[triggers]` (`reload.risk_factors = simple`). Mirrors DNS Guard's app.conf structure verbatim (`../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/app.conf`).
- `splunk_apps/aegis_app/metadata/default.meta` — NEW — application-level permissions: `[]` allows `read : [ * ], write : [ admin, power, sc_admin ]`; explicit `export = system` stanzas for `[eventtypes]`, `[props]`, `[transforms]`, `[lookups]`, `[macros]`, `[collections]`, `[tags]`, plus `[viewstates]` with `access = read : [ * ], write : [ * ]`. Mirrors DNS Guard's `metadata/default.meta` verbatim.
- `splunk_apps/aegis_app/README` — NEW — extension-less file (required for Splunkbase per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`); contains: app name, one-line description, version (1.0.0), supported Splunk versions ("9.4, 10.0, 10.1, 10.2, 10.3, 10.4"), supported platforms ("Splunk Cloud, Splunk Enterprise"), install instructions, license (Apache-2.0), author, link to top-level `README.md`.
- `splunk_apps/aegis_app/default/data/ui/nav/default.xml` — NEW — minimal nav XML listing the three dashboards that land in story-app-05/06/07 as `<view>` entries (`agent_risk_overview`, `verdict_inspector`, `regulator_evidence_pack`) plus the standard `search` view. Required so the app's left-rail nav resolves on first install before later stories add dashboard XMLs.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/default/app.conf exists
When  grep -c "^\[install\]\|^\[launcher\]\|^\[ui\]\|^\[package\]\|^\[triggers\]" runs against it
Then  the count is exactly 5

Given splunk_apps/aegis_app/default/app.conf is parsed
When  grep "^version = " runs
Then  the value is exactly "1.0.0"

Given splunk_apps/aegis_app/default/app.conf is parsed
When  grep "^id = " runs
Then  the value is exactly "aegis_app"

Given splunk_apps/aegis_app/README exists
When  grep -c "9.4\|10.0\|10.1\|10.2\|10.3\|10.4" runs against it
Then  count >= 1 (Splunk compatibility line present)

Given splunk_apps/aegis_app/README exists
When  grep "Apache-2.0" runs
Then  exactly one match (license declared)

Given splunk_apps/aegis_app/metadata/default.meta exists
When  grep -c "^export = system" runs
Then  count >= 7 (eventtypes, props, transforms, lookups, macros, collections, tags exported)

Given splunk_apps/aegis_app/default/data/ui/nav/default.xml exists
When  python -c "import xml.etree.ElementTree as ET; ET.parse('splunk_apps/aegis_app/default/data/ui/nav/default.xml')" runs
Then  exit code is 0 (well-formed XML)

Given splunk-appinspect is installed
When  splunk-appinspect inspect splunk_apps/aegis_app/ --mode test --included-tags cloud runs
Then  zero "error"-severity findings against tags check_for_updates, app_conf_required_stanzas, README_required
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Required files exist
test -f splunk_apps/aegis_app/default/app.conf
test -f splunk_apps/aegis_app/metadata/default.meta
test -f splunk_apps/aegis_app/README
test -f splunk_apps/aegis_app/default/data/ui/nav/default.xml

# 2. app.conf has the five required stanzas with correct values
grep -q '^version = 1.0.0$' splunk_apps/aegis_app/default/app.conf
grep -q '^id = aegis_app$' splunk_apps/aegis_app/default/app.conf
grep -q '^is_visible = 1$' splunk_apps/aegis_app/default/app.conf
grep -q '^label = Aegis' splunk_apps/aegis_app/default/app.conf
grep -q '^is_configured = 0$' splunk_apps/aegis_app/default/app.conf
test "$(grep -cE '^\[(install|launcher|ui|package|triggers)\]$' splunk_apps/aegis_app/default/app.conf)" -eq 5

# 3. README mentions Splunk compatibility line verbatim
grep -q '9.4, 10.0, 10.1, 10.2, 10.3, 10.4' splunk_apps/aegis_app/README
grep -q 'Apache-2.0' splunk_apps/aegis_app/README

# 4. default.meta exports all required namespaces system-wide
for ns in eventtypes props transforms lookups macros collections tags; do
  grep -A1 "^\[${ns}\]$" splunk_apps/aegis_app/metadata/default.meta | grep -q '^export = system$'
done

# 5. nav default.xml is well-formed
python -c "import xml.etree.ElementTree as ET; ET.parse('splunk_apps/aegis_app/default/data/ui/nav/default.xml')"

# 6. AppInspect dry run for cloud tag (skeleton-level checks only)
uv run splunk-appinspect inspect splunk_apps/aegis_app/ --mode test --included-tags cloud \
  --output-file appinspect-report.json --data-format json || true
python - <<'PY'
import json, sys
report = json.load(open("appinspect-report.json"))
errors = [r for r in report.get("reports", []) for g in r.get("groups", []) for c in g.get("checks", []) if c.get("result") == "error"]
if errors:
    print("AppInspect errors:", errors); sys.exit(1)
PY

# 7. LOC sanity — none of the conf files should exceed 400 LOC
for f in splunk_apps/aegis_app/default/app.conf splunk_apps/aegis_app/metadata/default.meta splunk_apps/aegis_app/README splunk_apps/aegis_app/default/data/ui/nav/default.xml; do
  test "$(grep -cve '^\s*$' -e '^\s*#' "$f" 2>/dev/null || wc -l < "$f")" -le 400
done
```

All seven blocks must exit 0 before opening the PR.

---

## Notes for coding agent

- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, DNS Guard AI (Splunkbase 7922, 1st place AI/ML 2025) shipped zero Python, zero LLM, pure SPL + MLTK; mirror its app.conf shape verbatim (see `../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/app.conf`).
- Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`, every Splunkbase-targeted app requires: `default/app.conf`, `metadata/default.meta`, and a top-level `README` (extension-less). AppInspect rejects packages missing any of these.
- Per `../../../context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md`, Abu's verified Splunk Cloud instance runs 10.4.2604.5. Splunk compatibility line in README MUST include 10.4 to be installable on the demo instance.
- Per `docs/architecture.md` § "ADR-008", we use Dashboard Studio v2 (JSON-in-XML) for views; nav default.xml is Classic Simple XML format — these coexist fine. DNS Guard does the same.
- Splunk compatibility line ("9.4, 10.0, 10.1, 10.2, 10.3, 10.4") matches the published support matrix for CIMplicity AI (2025 winner) and DNS Guard AI per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`.
- Author field in `[launcher]` is "Aegis Project" — anonymized per Apache-2.0 norms; sponsor credits live in top-level README.
- The `[triggers] reload.risk_factors = simple` stanza is required so changes to `risk_factors.conf` (lands in story-app-08) hot-reload without a Splunk restart. DNS Guard ships the same line.
- Do NOT create `bin/` or any Python scripts in `splunk_apps/aegis_app/` — DNS Guard's win was the no-Python-in-app pattern. All Python lives under `packages/`.
- The four placeholder dashboard `<view>` entries in nav/default.xml refer to files that land in stories app-05/06/07. Splunk tolerates missing views at install time (logged warning, no error) — verify by reading the AppInspect output.
- This story is intentionally small (~1h) to unblock the other 9 EPIC-09 stories. Do not bundle scope from later stories here.
