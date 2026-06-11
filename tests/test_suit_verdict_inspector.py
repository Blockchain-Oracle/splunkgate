"""Structural tests for the SUIT Verdict Inspector rebuild (story-suit-verdict-inspector).

D3 = "microscope": filter bar (time + 4 dropdowns) → verdict list (left)
→ detail panel + related events (right). Drill into ES investigation
workbench from the detail panel. trace_id copy-to-clipboard is the hero
micro-interaction.

PR #18 also closes the PR-15 scaffold loop: _suit_hello.xml + its
default.meta stanza + the hello.js / hello.tsx bundle files are all
removed. The agent_risk_overview's VERDICT_INSPECTOR_AVAILABLE flag is
flipped to true so its top-agents drill-downs now anchor at this view.
"""

from __future__ import annotations

import re
import tarfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_APP_ROOT = _REPO_ROOT / "splunk_apps" / "splunkgate_app"
_SUIT_STATIC = _APP_ROOT / "static" / "splunkgate-suit"
_SUIT_SRC = _APP_ROOT / "src"
_VIEW_XML = _APP_ROOT / "default" / "data" / "ui" / "views" / "verdict_inspector.xml"
_ARCHIVE = _REPO_ROOT / "docs" / "archive" / "dashboard-studio-v2" / "verdict_inspector.xml"
_BUNDLE_JS = _SUIT_STATIC / "verdict_inspector.js"
_BUNDLE_CSS = _SUIT_STATIC / "verdict_inspector.css"
_DEV_TSX = _SUIT_SRC / "views" / "verdict_inspector.tsx"

_AR_BUNDLE_JS = _SUIT_STATIC / "agent_risk_overview.js"
_AR_DEV_TSX = _SUIT_SRC / "views" / "agent_risk_overview.tsx"

# Shared invariants — every fragment MUST appear in both implementations.
_DRIFT_INVARIANTS = {
    "panel_titles": (
        "SplunkGate — Verdict Inspector",
        "Verdicts (latest 200)",
        "Verdict detail",
        "Related events for this trace_id",
    ),
    "filter_controls": (
        "Time range",
        "Agent",
        "Rule",
        "Severity",
        "Verdict label",
    ),
    "verdict_labels": ("block", "modify", "review", "allow"),
    "severities": ("HIGH", "MEDIUM", "LOW", "NONE_SEVERITY"),
    "spl_query_fragments": (
        "splunkgate_data` | stats values(agent_id)",
        "mvexpand rule | stats values(rule)",
        'agent_id="{AGENT}"',
        'severity="{SEVERITY}"',
        'verdict_label="{VERDICT_LABEL}"',
        'rule="{RULE}"',
        'trace_id="{TRACE_ID}"',
        "atlas_technique_id atlas_technique_name atlas_tactic_id",
        "explanation_short",
    ),
    "lifecycle_markers": (
        "SEARCH_TIMEOUT_MS",
        "Splunk Search SDK failed to load",
        "SearchManager construction failed",
        "PANEL FAILED TO LOAD",
    ),
    "drilldown_url_fragments": (
        "/app/SplunkEnterpriseSecuritySuite/investigation_workbench",
        "form.search=trace_id",
    ),
    "trace_chip_markers": (
        "vi-trace-chip",
        "navigator.clipboard",
        # HTTP-fallback path: Splunk Web isn't always HTTPS.
        'execCommand("copy")',
    ),
    "sanitizer_markers": (
        # SPL-injection guard: the template substitution strips
        # everything outside the safe alphabet.
        "sanitizeSplValue",
        "A-Za-z0-9",
    ),
    "fix_markers": (
        # F1 (silent-failure #1): mutation detection — refuses to query.
        "mutated",
        "Refusing to query",
        # F2 (silent-failure #2): click-sequence epoch protects against
        # detail/related race.
        # JS bundle: lastClickSeq state var; TSX: detailEnabled gating.
        # Verified separately by test_click_seq_or_enabled_gating.
        # F3 (silent-failure #3): visible copy-fail feedback.
        "vi-copy-failed",
        "copy failed",
        # F4 (silent-failure #4): formatSplunkTime helper handles epoch.
        "formatSplunkTime",
        "unparseable",
        # F5 (code-reviewer #3): monotonic SEARCH_ID_SEQ counter — no
        # same-ms collisions.
        "SEARCH_ID_SEQ",
    ),
}


def test_view_xml_references_suit_bundle() -> None:
    text = _VIEW_XML.read_text(encoding="utf-8")
    assert "<dashboard" not in text
    assert "<view " in text
    assert "splunkgate-suit/verdict_inspector.js" in text
    assert "splunkgate-suit/tokens.css" in text
    assert "splunkgate-suit/verdict_inspector.css" in text
    assert 'id="splunkgate-verdict-inspector"' in text


def test_view_xml_has_no_isvisible_attribute() -> None:
    text = _VIEW_XML.read_text(encoding="utf-8")
    view_tag = re.search(r"<view\b[^>]*>", text, re.DOTALL)
    assert view_tag is not None
    assert "isVisible" not in view_tag.group(0)


def test_archived_dashboard_studio_v2_original() -> None:
    assert _ARCHIVE.exists()
    text = _ARCHIVE.read_text(encoding="utf-8")
    assert '<dashboard version="2"' in text
    assert "ds_detail" in text
    assert "ds_related" in text


def test_built_bundle_committed() -> None:
    assert _BUNDLE_JS.exists()
    assert _BUNDLE_CSS.exists()


def test_dev_tsx_source_present() -> None:
    assert _DEV_TSX.exists()


def test_vi_drift_invariants_match_between_js_and_tsx() -> None:
    """Every shared invariant present in BOTH implementations."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for category, fragments in _DRIFT_INVARIANTS.items():
        for f in fragments:
            assert f in js, f"{category}: missing from JS bundle: {f!r}"
            assert f in tsx, f"{category}: missing from TSX source: {f!r}"


def test_spl_queries_lifted_verbatim_from_archive() -> None:
    """The 5 SPL data sources are lifted verbatim from the archive (with token substitution markers)."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    archive_normalized = _ARCHIVE.read_text(encoding="utf-8").replace('\\"', '"')
    # The Dashboard Studio v2 archive uses $input_*$ tokens; the SUIT
    # bundle substitutes them client-side via {AGENT}/{SEVERITY}/etc.
    # markers. The SPL body around those tokens is identical though, so
    # we spot-check the load-bearing fragments outside the substitution.
    for fragment in (
        "stats values(agent_id) as agent_id",
        "mvexpand rule | stats values(rule)",
        "explanation_short = if(len(explanation)>120",
        "head 200",
        "atlas_technique_id atlas_technique_name",
    ):
        assert fragment in js, f"SPL fragment missing from bundle: {fragment!r}"
        assert fragment in archive_normalized, f"SPL fragment missing from archive: {fragment!r}"


def test_search_lifecycle_errback_and_timeout() -> None:
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "SEARCH_TIMEOUT_MS" in src
        assert "Splunk Search SDK failed to load" in src
        assert "SearchManager construction failed" in src
        assert "cancelled" in src


def test_trace_id_copy_chip_with_http_fallback() -> None:
    """The trace_id chip is the hero micro-interaction. Both implementations
    must use navigator.clipboard AND fall back to document.execCommand for
    Splunk Web deployments that don't serve over HTTPS."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "navigator.clipboard" in src
        assert "isSecureContext" in src
        assert 'execCommand("copy")' in src
        # The "copied" visual feedback (800ms green confirmation).
        assert "vi-copied" in src


def test_severity_chips_independent_from_result_chips() -> None:
    """Per brief: severity (ordinal) and result (categorical) are independent
    visual axes. CSS must define both chip families with distinct treatments."""
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    # Severity chips: ordinal pill family.
    for s in ("vi-sev-HIGH", "vi-sev-MEDIUM", "vi-sev-LOW"):
        assert s in css
    # Result chips: dot+label family (visually different shape).
    for r in ("vi-result-block", "vi-result-modify", "vi-result-review", "vi-result-allow"):
        assert r in css
    # The .vi-chip pill rule and the .vi-result inline-flex rule have
    # distinct CSS definitions.
    assert ".vi-chip {" in css
    assert ".vi-result {" in css


def test_two_column_layout_with_filter_bar() -> None:
    """D3 layout: sticky filter bar + 2-column body (list / detail+related)."""
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert ".vi-filter-bar" in css
    assert "position: sticky" in css
    assert ".vi-body" in css
    # The two-column grid.
    assert "grid-template-columns: 1.5fr 1fr" in css


def test_spl_injection_sanitizer_present() -> None:
    """trace_id / agent_id / rule values are sanitized before substitution into SPL."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "sanitizeSplValue" in src
        # Whitelist: alnum + @._-: (per the SPL injection guard).
        assert "A-Za-z0-9" in src


def test_drilldown_to_es_investigation_workbench() -> None:
    """Detail panel opens ES Investigation Workbench in a new tab."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "/app/SplunkEnterpriseSecuritySuite/investigation_workbench" in src
        assert "form.search=trace_id" in src


def test_hard_edged_error_treatment() -> None:
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    assert "PANEL FAILED TO LOAD" in js
    assert "PANEL FAILED TO LOAD" in tsx
    assert ".vi-state-error-wrap" in css
    assert "border-top: 3px solid" in css


def test_dossier_tokens_used() -> None:
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert "var(--accent)" in css
    assert "var(--paper)" in css
    assert "var(--ink)" in css


def test_pr15_scaffold_placeholder_fully_removed() -> None:
    """PR #18 closes the PR-15 scaffold loop: hello.* files + meta stanza all gone."""
    assert not (_APP_ROOT / "default" / "data" / "ui" / "views" / "_suit_hello.xml").exists()
    assert not (_SUIT_STATIC / "hello.js").exists()
    assert not (_SUIT_SRC / "views" / "hello.tsx").exists()
    meta = (_APP_ROOT / "metadata" / "default.meta").read_text(encoding="utf-8")
    assert "[views/_suit_hello]" not in meta


def test_agent_risk_drilldown_flag_flipped() -> None:
    """PR #18 flips VERDICT_INSPECTOR_AVAILABLE to true so AR top-agents anchors land here."""
    ar_js = _AR_BUNDLE_JS.read_text(encoding="utf-8")
    ar_tsx = _AR_DEV_TSX.read_text(encoding="utf-8")
    assert "VERDICT_INSPECTOR_AVAILABLE = true" in ar_js
    assert "VERDICT_INSPECTOR_AVAILABLE = true" in ar_tsx


def test_nav_default_includes_three_dashboards() -> None:
    """nav/default.xml lists all three SUIT dashboards; verdict_inspector is reachable."""
    nav = (_APP_ROOT / "default" / "data" / "ui" / "nav" / "default.xml").read_text(
        encoding="utf-8"
    )
    for view_name in ("agent_risk_overview", "verdict_inspector", "regulator_evidence_pack"):
        assert f'name="{view_name}"' in nav, f"nav missing {view_name}"


def test_sanitizer_returns_mutation_flag() -> None:
    """F1 fix: sanitizer returns { value, mutated }. Callers refuse to query when mutated."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    # JS bundle: returns plain object with `mutated` field.
    assert "mutated: false" in js
    # TSX: SanitizedSpl interface declares the shape.
    assert "interface SanitizedSpl" in tsx
    assert "mutated: boolean" in tsx


def test_refuses_to_query_mutated_identifiers() -> None:
    """F1 fix: the search refusal text reaches both implementations."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "Refusing to query" in src or "REFUSING TO QUERY" in src


def test_click_seq_or_enabled_gating() -> None:
    """F2 fix: detail/related results bind to the current click only."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    # JS bundle: lastClickSeq + per-callback seq comparison.
    assert "lastClickSeq" in js
    assert "seq === state.lastClickSeq" in js
    # TSX: relies on useEffect's cleanup + the cancelled-flag inside
    # useSplunkSearch, which is keyed on the query string changing —
    # so a new selectedTraceId tears down the old hook before the new
    # one starts.
    assert "detailEnabled" in tsx
    assert "relatedEnabled" in tsx


def test_copy_failure_is_visible() -> None:
    """F3 fix: copy-to-clipboard failure produces a visible red chip + 'copy failed' text."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    assert "vi-copy-failed" in js
    assert "vi-copy-failed" in tsx
    assert ".vi-trace-chip.vi-copy-failed" in css
    # The user-facing failure copy:
    assert "copy failed" in js
    assert "copy failed" in tsx
    # Chip uses idempotent onclick assignment (not addEventListener) in the JS bundle.
    assert "btn.onclick = " in js


def test_format_splunk_time_handles_epoch_and_iso() -> None:
    """F4 fix: formatSplunkTime detects ISO-8601 OR numeric epoch, surfaces unparseable."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "formatSplunkTime" in src
        assert "parseFloat" in src
        assert "unparseable" in src
    # The render paths now call formatSplunkTime. The only `.substring` /
    # `.replace("T", " ")` calls left in either file are inside the
    # formatSplunkTime helper itself. There are exactly 2 such .replace
    # calls in formatSplunkTime (ISO branch + epoch branch).
    js_iso_replace = js.count('.substring(0, 19).replace("T", " ")')
    assert js_iso_replace == 2, (
        f"JS bundle has {js_iso_replace} ISO substring/replace calls; expected 2 (inside formatSplunkTime only)"
    )
    tsx_iso_replace = tsx.count('.substring(0, 19).replace("T", " ")')
    assert tsx_iso_replace == 2, (
        f"TSX has {tsx_iso_replace} ISO substring/replace calls; expected 2 (inside formatSplunkTime only)"
    )


def test_monotonic_search_id_counter() -> None:
    """F5 (code-reviewer): monotonic SEARCH_ID_SEQ — no Date.now() same-ms collisions."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "SEARCH_ID_SEQ" in src
        # Date.now() used to live inside the SearchManager id; it's gone now.
        # (Date.now() may still appear elsewhere for the click-seq debounce etc.)
        # We only need to verify the SearchManager id template references
        # SEARCH_ID_SEQ, not Date.now().
        sm_id_chunk = src.split("id:", 2)[1].split("\n", 2)[0]
        assert "SEARCH_ID_SEQ" in sm_id_chunk, "SearchManager id must use SEARCH_ID_SEQ"


def test_filter_change_debounced() -> None:
    """F-medium #5: rapid-fire filter changes are debounced before firing SPL."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "debouncedRefreshList" in js
    assert "listRefreshTimer" in js


def test_facet_load_failure_surfaces_warning() -> None:
    """F-medium #5: agents/rules facet failure no longer swallowed silently."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "agents facet load failed" in js
    assert "rules facet load failed" in js
    assert "dropdown unavailable" in js.lower()


def test_row_click_delegation_wired_once() -> None:
    """The row-click delegate attaches once at mount() to the persistent container,
    not re-bound on every render."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "function wireListDelegate" in js
    # wireListDelegate called in mount(); NOT in renderList (which would
    # re-bind on every render).
    mount_block = js.split("function mount", 1)[1].split("function ", 1)[0]
    assert "wireListDelegate()" in mount_block


def test_tarball_includes_verdict_inspector_bundle_and_excludes_hello() -> None:
    """The tarball ships verdict_inspector.{js,css} and the new view XML.
    It also ships agent_risk_overview.* and regulator_evidence_pack.* but
    NOT _suit_hello.xml or hello.js (PR-15 scaffold cleaned up)."""
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
    # Verdict Inspector ships.
    assert f"{top}/static/splunkgate-suit/verdict_inspector.js" in names
    assert f"{top}/static/splunkgate-suit/verdict_inspector.css" in names
    assert f"{top}/default/data/ui/views/verdict_inspector.xml" in names
    # The other two SUIT dashboards still ship.
    assert f"{top}/default/data/ui/views/agent_risk_overview.xml" in names
    assert f"{top}/default/data/ui/views/regulator_evidence_pack.xml" in names
    # PR-15 scaffold placeholder fully removed from the tarball.
    assert f"{top}/default/data/ui/views/_suit_hello.xml" not in names
    assert f"{top}/static/splunkgate-suit/hello.js" not in names
    # AppInspect rule: src/ stays out.
    src_leaks = [n for n in names if n == f"{top}/src" or n.startswith(f"{top}/src/")]
    assert src_leaks == [], f"src/ leaked into tarball: {src_leaks}"
