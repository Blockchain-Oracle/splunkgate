# Deploy guide — SplunkGate

Two paths, in the order you should run them.

## Phase 1 — local Docker Splunk Enterprise (test first)

Spin up Splunk Enterprise locally to verify the tarball installs cleanly + screenshot dashboards. Docker required.

```bash
# Builds + tests the local environment in one shot.
bash scripts/build_splunk_app_tgz.sh
bash scripts/local_docker_splunk.sh up

# Wait ~60s for first-time setup. Then:
#   Splunk Web: http://localhost:8000
#   admin / splunked99 (overridable via SPLUNKGATE_LOCAL_SPLUNK_PASSWORD)
#   HEC token: 00000000-1111-2222-3333-444444444444

# Populate dashboards:
bash scripts/local_docker_splunk.sh emit 500

# Now navigate Splunk Web -> Apps -> SplunkGate -> Agent Risk Overview.
# All 5 KPI tiles should show non-zero values; heatmap + time series populated.

# When done:
bash scripts/local_docker_splunk.sh down
```

**What to verify locally before touching Cloud:**

1. App appears under Apps menu with version 1.0.0.
2. Three dashboards (Agent Risk Overview, Verdict Inspector, Regulator Evidence Pack) all render.
3. KPI tiles + time series populate after `emit 500`.
4. No red error banners in any panel.

If anything is off, fix locally + rebuild the tarball before deploying to Cloud — Cloud deploys cost time + AppInspect throttling.

## Phase 2 — Splunk Cloud deploy via ACS API

Splunk Cloud (Victoria stack v10.4+) **removed the "Install app from file" UI**. Private apps deploy through the Admin Configuration Service (ACS) API only. The flow is:

1. Run AppInspect with the `private_victoria` tag — gets a server-side AppInspect cert token.
2. Mint a Splunk Cloud JWT inside your stack's Splunk Web.
3. POST the tarball to ACS with both tokens.

### Step 2.1 — AppInspect cloud-tag certification

This runs against `appinspect.splunk.com` (Splunk's hosted validation service). You need a **splunk.com SSO account** (same login you use for Splunkbase, docs, support).

```bash
export SPLUNK_COM_USERNAME="<your splunk.com email>"
export SPLUNK_COM_PASSWORD="<your splunk.com password>"
bash scripts/run_appinspect_cloud.sh
```

Output:
- `dist/appinspect-report.json` — full validation report
- `dist/appinspect-token.txt` — the AppInspect cert token (1-hour TTL)

If errors/failures > 0, the script exits non-zero. Read the report to see what to fix — usually a Cloud-policy violation we missed.

### Step 2.2 — Mint a Splunk Cloud JWT

This is **NOT** done at `console.scs.splunk.com` (that's a different Splunk product entirely — Splunk Cloud Services, which is unrelated to your Splunk Cloud Platform stack).

Instead:

1. Open `https://prd-p-t9irr.splunkcloud.com` in a browser.
2. Sign in as `sc_admin`.
3. **Settings → Tokens** (under the SYSTEM section, OR navigate directly to `https://prd-p-t9irr.splunkcloud.com/en-US/manager/search/authorization/tokens`).
4. Click **New Token**.
5. **User:** `sc_admin`. **Audience:** `splunkgate-deploy` (free text). **Expires:** 30 days max.
6. Click **Create**. **Copy the token value** — you won't see it again.

### Step 2.3 — Deploy

```bash
export SPLUNKGATE_STACK_NAME="prd-p-t9irr"
export SPLUNKGATE_CLOUD_JWT="<paste the JWT from Step 2.2>"
export SPLUNK_COM_APPINSPECT_TOKEN="$(cat dist/appinspect-token.txt)"

bash scripts/deploy_to_splunk_cloud.sh
```

Expected output: `HTTP 200` or `202`, and the SplunkGate app appears under `https://prd-p-t9irr.splunkcloud.com` → Apps → Manage Apps within ~30 seconds.

### Step 2.4 — Populate Cloud dashboards

Same emitter, pointed at your Cloud HEC:

```bash
source .env  # SPLUNKGATE_SPLUNK_HEC_URL + SPLUNKGATE_SPLUNK_HEC_TOKEN
uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 500
```

Dashboards on your Cloud tenant will show data within ~10 seconds of the first POST.

## Troubleshooting

### AppInspect FAILURE

The report at `dist/appinspect-report.json` lists every check that failed. Most common failures on first run:

- `check_for_binary_files_without_source_code` → we don't ship binaries; if this fires, something snuck in. Run `find splunk_apps/splunkgate_app -name '*.so' -o -name '*.dll'`.
- `check_for_secret_disclosure` → a fixture file probably has an `AKIA…`-shaped string in it. Verify `.appinspect.expect.yaml` (empty by default per ADR-008).
- `check_for_explicit_exports_in_default_meta` → metadata permissions issue.

Add to `.appinspect.expect.yaml` only if the check is a false positive AND we can justify it to a Splunkbase reviewer.

### ACS HTTP 401 / 403

JWT is invalid or expired. Mint a fresh one in Splunk Web → Settings → Tokens.

### ACS HTTP 404 with "stack not found"

`SPLUNKGATE_STACK_NAME` should be `prd-p-t9irr` (the part before `.splunkcloud.com`). Don't include the domain.

### ACS HTTP 422 with AppInspect error

`SPLUNK_COM_APPINSPECT_TOKEN` is expired (1-hour TTL). Re-run `scripts/run_appinspect_cloud.sh`.

## Sources

- [Splunk Cloud Platform ACS — Manage private apps](https://help.splunk.com/en/splunk-cloud-platform/administer/admin-config-service-manual/10.3.2512/administer-splunk-cloud-platform-using-the-admin-config-service-acs-api/manage-private-apps-in-splunk-cloud-platform)
- [ACS requirements + compatibility matrix](https://help.splunk.com/en/splunk-cloud-platform/administer/admin-config-service-manual/10.3.2512/using-the-admin-config-service-acs--api/admin-config-service-acs-requirements-and-compatibility-matrix)
- [AppInspect API reference](https://dev.splunk.com/enterprise/docs/developapps/testvalidate/appinspect/splunkappinspectapi/)
- [Splunk private apps demo repo](https://github.com/splunk/acs-privateapps-demo)
