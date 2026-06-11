# Dashboard Studio v2 — Rollback Procedure

If the SUIT-rebuilt dashboards (PRs #16-#18) need to be reverted to the
Dashboard Studio v2 originals — examiner deadline pressure, mid-incident
AppInspect failure, or any reason — this directory holds the verbatim
originals.

**Rollback is per-dashboard.** You can revert one without touching the others.

## Files in this directory

```
regulator_evidence_pack.xml   <- archived original of S4 D1 (PR #16)
agent_risk_overview.xml       <- archived original of S4 D2 (PR #17; added then)
verdict_inspector.xml         <- archived original of S4 D3 (PR #18; added then)
```

Live destination for each:

```
splunk_apps/splunkgate_app/default/data/ui/views/<name>.xml
```

## Procedure

Run from the repo root.

### 1. Restore the file

```bash
# Regulator Evidence Pack (PR #16)
cp docs/archive/dashboard-studio-v2/regulator_evidence_pack.xml \
   splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml

# Agent Risk Overview (PR #17, after that PR ships)
cp docs/archive/dashboard-studio-v2/agent_risk_overview.xml \
   splunk_apps/splunkgate_app/default/data/ui/views/agent_risk_overview.xml

# Verdict Inspector (PR #18, after that PR ships)
cp docs/archive/dashboard-studio-v2/verdict_inspector.xml \
   splunk_apps/splunkgate_app/default/data/ui/views/verdict_inspector.xml
```

### 2. Rebuild + AppInspect

```bash
bash scripts/build_splunk_app_tgz.sh
# AppInspect runs as part of the build; failure aborts.
```

The resulting `dist/splunkgate_app-1.0.0.tgz` ships the restored Dashboard
Studio v2 view alongside the still-SUIT views (unless you restored all three).

### 3. Reinstall

```bash
# Splunk Web > Manage Apps > Install from file > select the .tgz, "Upgrade" checked.
# Or via CLI on a Splunk instance:
splunk install app dist/splunkgate_app-1.0.0.tgz -update 1 -auth admin:<password>
splunk restart
```

### 4. Verify

Open Splunk Web. The dashboard should render with the Dashboard Studio v2
chrome (the dark navy + Splunk-native palette, NOT the Dossier paper
substrate). If you still see the Dossier paper substrate, the Splunk
bundle cache is stale — `splunk reload` or a full restart resolves it.

## Important: rollback gotchas

- The bundle files at `static/splunkgate-suit/*.js` and `static/splunkgate-suit/*.css`
  stay shipped after a partial rollback. They are reachable to authenticated
  users with `read` capability on the app but no view references them after
  rollback. To fully strip them, delete from the working tree before rebuilding.
- `metadata/default.meta` is NOT affected by the rollback. The
  `[views/_suit_hello]` stanza (PR #15 scaffold artefact) was already removed
  in PR #18; if you're rolling back from a pre-PR-18 state this stanza is fine.
- Rolling back the live `regulator_evidence_pack.xml` to Dashboard Studio v2
  does NOT delete `evidence_pack.{js,css}` from `static/splunkgate-suit/`.
  If you need them removed (clean tarball for Splunkbase), `git rm` them
  before rebuild.

## Do NOT

- **`git checkout` the archive file** — that updates the archive copy, not the
  live view. The rollback requires `cp`, not git.
- **Edit the archive in place** — it is the rollback contract; treat it as
  immutable. To update it deliberately, write a follow-up PR with the new
  archive content.
