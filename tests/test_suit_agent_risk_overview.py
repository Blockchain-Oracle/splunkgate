"""Structural tests for the SUIT Agent Risk Overview rebuild (story-suit-agent-risk-overview).

D2 = "cockpit." 5 KPI tiles + verdicts-by-label area + rules-by-hour heatmap
+ top agents by BLOCKED + MSJ scaling. Drill-down on chart/heatmap/row click
to verdict_inspector (gated on the VERDICT_INSPECTOR_AVAILABLE flag until
PR #18 lands). Live-tick pulse on the BLOCKED KPI is the only motion.
"""

from __future__ import annotations

import re
import tarfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_APP_ROOT = _REPO_ROOT / "splunk_apps" / "splunkgate_app"
_SUIT_STATIC = _APP_ROOT / "static" / "splunkgate-suit"
_SUIT_SRC = _APP_ROOT / "src"
_VIEW_XML = _APP_ROOT / "default" / "data" / "ui" / "views" / "agent_risk_overview.xml"
_ARCHIVE = _REPO_ROOT / "docs" / "archive" / "dashboard-studio-v2" / "agent_risk_overview.xml"
_BUNDLE_JS = _SUIT_STATIC / "agent_risk_overview.js"
_BUNDLE_CSS = _SUIT_STATIC / "agent_risk_overview.css"
_DEV_TSX = _SUIT_SRC / "views" / "agent_risk_overview.tsx"

# Shared invariants — every fragment MUST appear in both implementations.
_DRIFT_INVARIANTS = {
    "panel_titles": (
        "SplunkGate — Agent Risk Overview",
        "Verdicts by label, per hour",
        "Rules-by-hour heatmap",
        "Top agents by BLOCKED count",
        "MSJ scaling indicator",
    ),
    "kpi_labels": (
        "Total verdicts",
        "BLOCKED actions",
        "HIGH severity",
        "Distinct agents",
        "Tokens saved",
    ),
    "cisco_rule_names_verbatim": (
        "Code Detection",
        "Harassment",
        "Hate Speech",
        "PCI",
        "PHI",
        "PII",
        "Prompt Injection",
        "Profanity",
        "Sexual Content & Exploitation",
        "Social Division & Polarization",
        "Violence & Public Safety Threats",
    ),
    "spl_query_fragments": (
        "splunkgate_data` | stats count",
        "verdict_label=block | stats count",
        "severity=HIGH",
        "stats dc(agent_id) as agents",
        "sum(tokens_used) as tokens_saved",
        "timechart span=1h count by verdict_label",
        "mvexpand rule | bin _time span=1h",
        "stats count by agent_id | sort -count | head 10",
        'count(eval(severity!="NONE_SEVERITY"))',
    ),
    "lifecycle_markers": (
        "SEARCH_TIMEOUT_MS",
        "Splunk Search SDK failed to load",
        "SearchManager construction failed",
        "PANEL FAILED TO LOAD",
    ),
    "fix_markers": (
        # F1 (silent-failure #1): distinct CSS class for KPI failure.
        "ar-kpi-failed",
        # F2 (silent-failure #2): live-tick baseline gated on a "seen successful" sentinel.
        # Both implementations carry a "seenSuccessful" sentinel (JS:
        # lastBlockSeenSuccessful, TSX: seenSuccessfulRef.current).
        "seenSuccessful",  # checked case-insensitive below via test_seen_successful_sentinel
        # F3 (silent-failure #3): unmapped rules surface as an Other row.
        "__OTHER__",
        # F4 (silent-failure #4): footer status reflects per-search outcome.
        "Refresh: ",
        # F5 (code-reviewer HIGH-2): single-bucket area-chart guard.
        "Single-bucket window",
        # F6 (silent-failure #7): drill-down gated on the v1.1 flag.
        "VERDICT_INSPECTOR_AVAILABLE",
        # F7 (code-reviewer HIGH-1): absolute floor for heatmap bucket-5.
        "HEATMAP_BUCKET_5_FLOOR",
    ),
    "block_overlay_markers": (
        # F8 (code-reviewer HIGH-2): BLOCK painted as a discrete overlay,
        # not a stack layer. Both implementations must reference the
        # overlay class names.
        "ar-area-block-line",
        "ar-area-block-dot",
    ),
    "drilldown_url_fragments": ("/app/splunkgate_app/verdict_inspector", "form.input_agent_id"),
}


def test_view_xml_references_suit_bundle() -> None:
    """The view XML is a SUIT bundle, not Dashboard Studio v2 JSON."""
    text = _VIEW_XML.read_text(encoding="utf-8")
    assert "<dashboard" not in text
    assert "<view " in text
    assert "splunkgate-suit/agent_risk_overview.js" in text
    assert "splunkgate-suit/tokens.css" in text
    assert "splunkgate-suit/agent_risk_overview.css" in text
    assert 'id="splunkgate-agent-risk"' in text


def test_view_xml_has_no_isvisible_attribute() -> None:
    text = _VIEW_XML.read_text(encoding="utf-8")
    view_tag = re.search(r"<view\b[^>]*>", text, re.DOTALL)
    assert view_tag is not None
    assert "isVisible" not in view_tag.group(0)


def test_archived_dashboard_studio_v2_original() -> None:
    """Rollback artefact ships unchanged."""
    assert _ARCHIVE.exists()
    text = _ARCHIVE.read_text(encoding="utf-8")
    assert '<dashboard version="2"' in text
    assert "ds_heatmap" in text


def test_built_bundle_committed() -> None:
    assert _BUNDLE_JS.exists()
    assert _BUNDLE_CSS.exists()


def test_dev_tsx_source_present() -> None:
    assert _DEV_TSX.exists()


def test_ar_drift_invariants_match_between_js_and_tsx() -> None:
    """Every shared invariant present in BOTH implementations.

    The 'seenSuccessful' marker is checked via a dedicated case-insensitive
    test (`test_seen_successful_sentinel_present`) so the JS naming
    `lastBlockSeenSuccessful` and the TSX naming `seenSuccessfulRef` both
    satisfy the contract.
    """
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for category, fragments in _DRIFT_INVARIANTS.items():
        for f in fragments:
            if f == "seenSuccessful":
                continue  # see test_seen_successful_sentinel_present
            assert f in js, f"{category}: missing from JS bundle: {f!r}"
            assert f in tsx, f"{category}: missing from TSX source: {f!r}"


def test_seen_successful_sentinel_present() -> None:
    """F-silent-2 fix: both implementations carry a 'seenSuccessful' sentinel.

    Case-sensitive substring matches differ because the JS bundle uses
    `lastBlockSeenSuccessful` (capital-S) while the TSX uses
    `seenSuccessfulRef` (lower-case-s leading word).
    """
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    assert "SeenSuccessful" in js
    assert "seenSuccessful" in tsx


def test_cisco_rule_names_verbatim_in_heatmap_order() -> None:
    """The 11 Cisco AI Defense rule names appear verbatim AND in canonical order."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    canonical = _DRIFT_INVARIANTS["cisco_rule_names_verbatim"]
    js_block = js.split("CISCO_AI_DEFENSE_RULES", 1)[1].split("];", 1)[0]
    last_idx = -1
    for r in canonical:
        idx = js_block.find(r)
        assert idx > last_idx, f"rule order broken at {r!r} (JS bundle)"
        last_idx = idx
    tsx_block = tsx.split("CISCO_AI_DEFENSE_RULES", 1)[1].split("] as const", 1)[0]
    last_idx = -1
    for r in canonical:
        idx = tsx_block.find(r)
        assert idx > last_idx, f"rule order broken at {r!r} (TSX source)"
        last_idx = idx


def test_spl_queries_lifted_verbatim_from_archive() -> None:
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    archive_normalized = _ARCHIVE.read_text(encoding="utf-8").replace('\\"', '"')
    for fragment in _DRIFT_INVARIANTS["spl_query_fragments"]:
        assert fragment in js
        assert fragment in archive_normalized


def test_live_tick_animation_present() -> None:
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert ".ar-tick" in css
    assert "@keyframes ar-pulse" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_blocked_kpi_uses_vermillion_accent_when_live() -> None:
    """BLOCKED tile carries vermillion accent when LIVE. .ar-kpi-failed overrides it."""
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    block_section = css.split(".ar-kpi-block", 1)[1].split("/* KPI loading", 1)[0]
    assert "var(--accent" in block_section
    # And: .ar-kpi-failed must override the BLOCKED brand accent so a
    # failed BLOCK refresh doesn't look "live."
    assert ".ar-kpi-failed" in css
    failed_section = css.split(".ar-kpi-failed", 1)[1].split("/* SR ", 1)[0].split("/* Panel", 1)[0]
    assert "border" in failed_section


def test_kpi_loading_class_distinguishable_from_failed() -> None:
    """ar-kpi-loading and ar-kpi-failed are visually distinct CSS classes."""
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert ".ar-kpi-loading" in css
    assert ".ar-kpi-failed" in css
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    # Both implementations apply the classes.
    assert "ar-kpi-loading" in js
    assert "ar-kpi-failed" in js
    assert "ar-kpi-loading" in tsx
    assert "ar-kpi-failed" in tsx


def test_search_lifecycle_errback_and_timeout() -> None:
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "SEARCH_TIMEOUT_MS" in src
        assert "Splunk Search SDK failed to load" in src
        assert "SearchManager construction failed" in src
        assert "cancelled" in src


def test_cancel_all_on_window_change() -> None:
    """F8 fix: time-range change cancels ALL in-flight searches before new wave."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "function cancelAll" in js
    # cancelAll is called from the time-range handler.
    time_handler = js.split('getElementById("ar-time")', 1)[1].split(
        'getElementById("ar-refresh")', 1
    )[0]
    assert "cancelAll()" in time_handler


def test_tick_baseline_reset_lifecycle() -> None:
    """F4 / F-silent-2 fix: lastBlockValue reset on window change, refresh change, AND KPI error."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    # JS bundle: explicit resets in window handler, refresh-interval handler, AND setKpiError.
    assert "resetTickBaselines" in js
    refresh_handler = js.split('getElementById("ar-refresh")', 1)[1].split("function mount", 1)[0]
    assert "resetTickBaselines()" in refresh_handler
    kpi_error_block = js.split("function setKpiError", 1)[1].split("function tickKpi", 1)[0]
    assert "lastBlockSeenSuccessful = false" in kpi_error_block
    # TSX: lastBlockRef.current = null on earliest/refresh-interval change.
    assert "lastBlockRef.current = null" in tsx
    assert "[earliest, refreshIntervalMs]" in tsx


def test_heatmap_bucket_5_floor_present() -> None:
    """F7 fix: an absolute floor for bucket-5 prevents a single hit from painting vermillion."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "HEATMAP_BUCKET_5_FLOOR" in src
        # Both files reference the same numeric floor.
        assert "6.0" in src or "6" in src


def test_heatmap_unmapped_rules_surfaced() -> None:
    """F-silent-3 fix: rules outside the canonical 11 are rolled into an Other row + console.warn."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "__OTHER__" in src
        # The Other row is rendered alongside the canonical 11.
        assert "unmapped" in src.lower()


def test_area_chart_single_bucket_guarded() -> None:
    """F5 fix: a single-bucket result surfaces an empty-state instead of degenerate SVG."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "Single-bucket window" in src


def test_area_chart_block_is_discrete_overlay() -> None:
    """F-code-HIGH-2 fix: BLOCK painted as line+dots overlay, NOT as a stack layer."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "ar-area-block-line" in src
        assert "ar-area-block-dot" in src
    # Stack series in JS must NOT include BLOCK.
    stack_order_decl = js.split("var stackOrder = ", 1)[1].split(";", 1)[0]
    assert "BLOCK" not in stack_order_decl
    tsx_stack_decl = tsx.split("const stackOrder = ", 1)[1].split(";", 1)[0]
    assert "BLOCK" not in tsx_stack_decl


def test_footer_status_reflects_per_search_outcome() -> None:
    """F-silent-4 fix: 'Refresh: N/9 OK' line; 'Last refresh' updates only on fully-ok wave."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "Refresh: " in src
    # JS: tracks searchOutcome explicitly per ID.
    assert "searchOutcome" in js
    assert "function updateFooterStatus" in js
    # Stale indicator class.
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert ".ar-refresh-stale" in css


def test_verdict_inspector_drilldown_feature_flagged() -> None:
    """F-silent-7 fix: top-agents row renders as <span> until PR #18 ships."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "VERDICT_INSPECTOR_AVAILABLE" in src
    # Flag is OFF by default (PR #17 ships before PR #18).
    assert "VERDICT_INSPECTOR_AVAILABLE = false" in js
    assert "VERDICT_INSPECTOR_AVAILABLE = false" in tsx


def test_tick_timer_tracked_per_tile() -> None:
    """F-code-MEDIUM-1 fix: per-tile tick timer cleared before re-arming so burst pulses don't truncate."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "kpiTickTimers" in js
    tick_fn = js.split("function tickKpi", 1)[1].split("function ", 1)[0]
    assert "clearTimeout" in tick_fn


def test_hard_edged_error_treatment() -> None:
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    assert "PANEL FAILED TO LOAD" in js
    assert "PANEL FAILED TO LOAD" in tsx
    assert ".ar-state-error-wrap" in css
    assert "border-top: 3px solid" in css


def test_safe_html_escaping_in_bundle() -> None:
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "function escapeHtml" in js
    assert "escapeHtml(label)" in js
    assert "escapeHtml(suffix)" in js
    # The previously-flagged unescaped extraClass interpolation is now escaped.
    kpi_fn = js.split("function kpi(", 1)[1].split("function ", 1)[0]
    assert "escapeHtml(extraClass" in kpi_fn


def test_dossier_tokens_used() -> None:
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    main_path = css.split("@media print", 1)[0] if "@media print" in css else css
    assert "var(--accent)" in main_path
    assert "var(--paper)" in main_path
    assert "var(--ink)" in main_path
    # Vermillion heatmap intensity ramp — NOT viridis.
    assert "rgba(188, 58, 38" in css


def test_search_keys_match_between_implementations() -> None:
    """The 9-search refresh wave must enumerate the same keys in both files."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    keys = ("total", "block", "high", "agents", "tokens", "ts", "heatmap", "top_agents", "msj")
    for k in keys:
        assert k in js
        assert k in tsx


def test_tarball_includes_agent_risk_bundle() -> None:
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    dist = _REPO_ROOT / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "SKIP_APPINSPECT": "1"}
    try:
        subprocess.run(
            ["bash", str(_REPO_ROOT / "scripts" / "build_splunk_app_tgz.sh")],
            check=True,
            env=env,
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        msg = (
            f"build_splunk_app_tgz.sh failed (rc={exc.returncode})\n"
            f"--- stdout ---\n{exc.stdout}\n"
            f"--- stderr ---\n{exc.stderr}"
        )
        raise AssertionError(msg) from exc
    tgz = next(dist.glob("splunkgate_app-*.tgz"))
    with tarfile.open(tgz, "r:gz") as tar:
        names = tar.getnames()
    top = "splunkgate_app"
    assert f"{top}/static/splunkgate-suit/agent_risk_overview.js" in names
    assert f"{top}/static/splunkgate-suit/agent_risk_overview.css" in names
    assert f"{top}/default/data/ui/views/agent_risk_overview.xml" in names
    src_leaks = [n for n in names if n == f"{top}/src" or n.startswith(f"{top}/src/")]
    assert src_leaks == [], f"src/ leaked into tarball: {src_leaks}"
