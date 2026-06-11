"""Structural tests for the SUIT Regulator Evidence Pack rebuild (story-suit-evidence-pack).

Goal: lock the contract that the new SUIT view ships:
1. The verbatim SR 26-2 footnote 3 quote (load-bearing trust signal).
2. The unchanged SPL queries lifted from the archived Dashboard Studio v2 view.
3. The Dossier styling overlay with hard-edged error treatment.
4. Profile-gating via `display: none` (NOT "excluded" text in the PDF).
5. Export-PDF gated on all-active-panels-resolved.
6. AMD-load errback + try/catch around new SearchManager + 30s timeout.
7. Cross-implementation drift detection: the JS bundle and TSX source-of-truth
   must carry the same invariants.
8. ROLLBACK.md is present at the archive path.
"""

from __future__ import annotations

import re
import tarfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_APP_ROOT = _REPO_ROOT / "splunk_apps" / "splunkgate_app"
_SUIT_STATIC = _APP_ROOT / "static" / "splunkgate-suit"
_SUIT_SRC = _APP_ROOT / "src"
_VIEW_XML = _APP_ROOT / "default" / "data" / "ui" / "views" / "regulator_evidence_pack.xml"
_ARCHIVE = _REPO_ROOT / "docs" / "archive" / "dashboard-studio-v2" / "regulator_evidence_pack.xml"
_ARCHIVE_ROLLBACK = _REPO_ROOT / "docs" / "archive" / "dashboard-studio-v2" / "ROLLBACK.md"
_BUNDLE_JS = _SUIT_STATIC / "evidence_pack.js"
_BUNDLE_CSS = _SUIT_STATIC / "evidence_pack.css"
_DEV_TSX = _SUIT_SRC / "views" / "evidence_pack.tsx"

# Shared invariants that MUST appear in both implementations. The drift
# detector test asserts every fragment is present in both the JS bundle
# AND the TSX source. The other panel-coverage tests reuse these.
_DRIFT_INVARIANTS = {
    "panel_titles": (
        "NIST AI RMF function mapping",
        "SR 26-2 footnote 3",
        "EU AI Act Article 6 — high-risk classification mapping",
        "HIPAA Safe Harbor 18 — PHI detection counts",
        "PCI DSS 11.x — PCI detection counts",
    ),
    "kpi_labels": (
        "Coverage period",
        "Total decisions",
        "Unique trace IDs",
        "Attested decisions",
    ),
    "sr_26_2_sentences": (
        "Generative AI and agentic AI models are novel and rapidly evolving.",
        "As such, they are not within the scope of this guidance.",
        "a banking organization's risk management and governance practices",
        "the principles described in this guidance apply",
        "to traditional statistical and quantitative models and non-generative",
    ),
    "sr_26_2_attribution": (
        "SR 26-2 Attachment, footnote 3, p. 3",
        "Federal Reserve",
        "OCC",
        "FDIC",
        "April 17, 2026",
    ),
    "spl_query_fragments": (
        "stats count as total_decisions",
        'case(row=1,"GOVERN", row=2,"MAP", row=3,"MEASURE", row=4,"MANAGE")',
        "Critical infrastructure (Annex III §2)",
        "rule=PHI",
        "rule=PCI",
        "SplunkGate v1.0.0",
    ),
    "scope_statements": (
        "Scope: HIPAA Safe Harbor 18",
        "Scope: PCI DSS 11.x",
        "Scope: FSI (FFIEC-AIML / SR 26-2)",
        "Scope: PUBSEC (NIST AI RMF)",
        "All in-scope profiles are included in this artifact",
    ),
    "lifecycle_markers": (
        # Search timeout (both files must enforce it).
        "SEARCH_TIMEOUT_MS",
        # The errback is the bug we fixed: AMD load failure must surface.
        "Splunk Search SDK failed to load",
        # SearchManager construction failure must surface.
        "SearchManager construction failed",
        # Hard-edged error treatment in the print path.
        "PANEL FAILED TO LOAD",
    ),
}


def test_view_xml_references_suit_bundle() -> None:
    """The view XML is a SUIT bundle, not Dashboard Studio v2 JSON."""
    text = _VIEW_XML.read_text(encoding="utf-8")
    assert "<dashboard" not in text, "Dashboard Studio v2 still in place; SUIT rebuild not applied"
    assert "<view " in text
    assert "splunkgate-suit/evidence_pack.js" in text
    assert "splunkgate-suit/tokens.css" in text
    assert "splunkgate-suit/evidence_pack.css" in text
    assert 'id="splunkgate-evidence-pack"' in text


def test_view_xml_has_no_isvisible_attribute() -> None:
    """isVisible is not a valid <view> attribute (the SUIT scaffold lesson)."""
    text = _VIEW_XML.read_text(encoding="utf-8")
    view_tag = re.search(r"<view\b[^>]*>", text, re.DOTALL)
    assert view_tag is not None
    assert "isVisible" not in view_tag.group(0)


def test_archived_dashboard_studio_v2_original() -> None:
    """Rollback artefact: the Dashboard Studio v2 original ships untouched."""
    assert _ARCHIVE.exists()
    text = _ARCHIVE.read_text(encoding="utf-8")
    assert '<dashboard version="2"' in text
    assert "ds_header_kpis" in text


def test_rollback_runbook_present() -> None:
    """`docs/archive/dashboard-studio-v2/ROLLBACK.md` documents the exact cp command."""
    assert _ARCHIVE_ROLLBACK.exists()
    text = _ARCHIVE_ROLLBACK.read_text(encoding="utf-8")
    # The cp command (not git checkout — that's a gotcha) must be present.
    assert "cp docs/archive/dashboard-studio-v2/regulator_evidence_pack.xml" in text
    assert "splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml" in text
    # The gotcha section must call out the `git checkout` antipattern.
    assert "git checkout" in text


def test_built_bundle_committed() -> None:
    """The hand-written evidence_pack.js + evidence_pack.css ship in static/."""
    assert _BUNDLE_JS.exists()
    assert _BUNDLE_CSS.exists()


def test_dev_tsx_source_present() -> None:
    """The TypeScript/React source-of-truth lives under src/views/."""
    assert _DEV_TSX.exists()


def test_drift_invariants_match_between_js_and_tsx() -> None:
    """Every shared invariant is present in BOTH the JS bundle and the TSX source.

    Catches the silent-failure F5 finding: a bug fixed in only one file
    while the other ships the regression. The TSX has an explicit DRIFT
    CONTRACT in its header comment; this test enforces it for the
    invariants we can detect via string presence.
    """
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for category, fragments in _DRIFT_INVARIANTS.items():
        for f in fragments:
            assert f in js, f"{category}: missing from JS bundle: {f!r}"
            assert f in tsx, f"{category}: missing from TSX source: {f!r}"


def test_sr_26_2_quote_verbatim() -> None:
    """The SR 26-2 footnote 3 quote is verbatim in both the bundle and the TSX source."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for sentence in _DRIFT_INVARIANTS["sr_26_2_sentences"]:
        assert sentence in js
        assert sentence in tsx
    for fragment in _DRIFT_INVARIANTS["sr_26_2_attribution"]:
        assert fragment in js
        assert fragment in tsx


def test_panel_inventory_covered_in_bundle() -> None:
    """All examiner panels are present in the bundle."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    for title in _DRIFT_INVARIANTS["panel_titles"]:
        assert title in js
    for label in _DRIFT_INVARIANTS["kpi_labels"]:
        assert label in js
    assert "Export PDF for examiner record" in js


def test_spl_queries_lifted_verbatim_from_archive() -> None:
    """The 6 SPL data sources are lifted verbatim from the archived Dashboard Studio v2 definition.

    Archive embeds queries inside JSON, so `"` appears as `\\\"`. The
    bundle uses raw JS strings; normalize before comparing.
    """
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    archive_normalized = _ARCHIVE.read_text(encoding="utf-8").replace('\\"', '"')
    for fragment in _DRIFT_INVARIANTS["spl_query_fragments"]:
        assert fragment in js, f"SPL fragment missing from bundle: {fragment!r}"
        assert fragment in archive_normalized, f"SPL fragment missing from archive: {fragment!r}"


def test_export_pdf_uses_window_print() -> None:
    """The Export PDF button calls window.print() — the browser-print export path is the contract."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "window.print()" in js


def test_export_pdf_button_starts_disabled() -> None:
    """The button ships `disabled` in the initial shell HTML; updateExportGate() enables it only when all-ok.

    This is the F3 fix: prevent users from exporting while panels are still
    loading or after a search error.
    """
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    # The button is rendered with `disabled` and gated by updateExportGate.
    assert 'id="ep-export" disabled>' in js
    assert "updateExportGate" in js
    # The gate function checks both loading and errored counts.
    assert "loading === 0 && errored === 0" in js


def test_profile_gate_uses_display_none_not_excluded_text() -> None:
    """F4 fix: profile-gated panels are hidden via class toggle + CSS display:none.

    No "Profile gate excludes X — select X or All profiles" text reaches the
    PDF. Instead, the jurisdictional banner at the top tells the examiner
    what's in scope, and out-of-scope panels are removed from the DOM in
    print mode.
    """
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")

    # No UI-instruction text anywhere.
    forbidden_phrases = (
        "Profile gate excludes HIPAA",
        "Profile gate excludes PCI",
        "select HIPAA or All profiles",
        "select PCI or All profiles",
    )
    for phrase in forbidden_phrases:
        assert phrase not in js, f"UI-instruction text leaked to bundle: {phrase!r}"
        assert phrase not in tsx, f"UI-instruction text leaked to TSX: {phrase!r}"

    # display:none mechanic in CSS + class toggle in JS + conditional render in TSX.
    assert ".ep-hidden" in css
    assert "display: none" in css
    assert "ep-hidden" in js
    # TSX uses conditional render rather than a class toggle.
    assert "hipaaEnabled &&" in tsx
    assert "pciEnabled &&" in tsx


def test_jurisdiction_banner_renders_scope_statement() -> None:
    """The jurisdictional banner is the examiner-facing scope statement; survives print."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert "ep-jurisdiction-banner" in js
    assert "ep-jurisdiction-banner" in css
    # Banner must NOT be hidden in print — examiner needs to see the scope.
    print_block = css.split("@media print", 1)[1] if "@media print" in css else ""
    assert "ep-jurisdiction-banner" in print_block
    # The display: none rule that hides controls must NOT apply to the banner.
    # We assert positively: the banner appears within the print block with
    # border + page-break-inside avoid, not display: none.
    assert "page-break-inside: avoid" in print_block


def test_hard_edged_error_treatment() -> None:
    """F2 fix: error and empty states are visually distinguishable in the PDF."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    # Bold "PANEL FAILED TO LOAD" header in both implementations.
    assert "PANEL FAILED TO LOAD" in js
    assert "PANEL FAILED TO LOAD" in tsx
    # CSS error-wrap class has top + bottom border so it survives B&W print.
    assert ".ep-state-error-wrap" in css
    assert "border-top: 3px solid" in css


def test_search_lifecycle_errback_and_timeout() -> None:
    """F1 fix: require() has an errback; new SearchManager() is wrapped in try/catch; 30s timeout fires onError."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    tsx = _DEV_TSX.read_text(encoding="utf-8")
    for src in (js, tsx):
        assert "SEARCH_TIMEOUT_MS" in src
        assert "Splunk Search SDK failed to load" in src
        assert "SearchManager construction failed" in src
        # The cancelled-flag pattern matches between both implementations.
        assert "cancelled" in src


def test_print_styles_strip_chrome_and_collapse_grid() -> None:
    """@media print drops Splunk header/footer + collapses the 2-col grid for A4 portrait."""
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert "@media print" in css
    assert "display: none" in css
    assert "grid-template-columns: 1fr" in css


def test_dossier_tokens_used_no_hex_in_main_path() -> None:
    """evidence_pack.css uses tokens — hex literals only in the @media print fallback block."""
    css = _BUNDLE_CSS.read_text(encoding="utf-8")
    assert "var(--accent)" in css
    assert "var(--paper)" in css
    assert "var(--ink)" in css
    # Spot-check: the main-path :root/.ep-* rules carry token references, not raw hex.
    main_path = css.split("@media print", 1)[0]
    # The only acceptable hex outside print mode is in url(...) or comments.
    # We don't enforce zero hex (the brand glyph hex is fine as a comment),
    # but the kpi label / panel border / accent rules must use tokens.
    assert ".ep-kpi-value" in main_path
    assert "color: var(" in main_path or "background: var(" in main_path


def test_safe_html_escaping_present() -> None:
    """The bundle defines escapeHtml and applies it in the kpi() + renderTable() helpers (F1-fix layer 2)."""
    js = _BUNDLE_JS.read_text(encoding="utf-8")
    assert "function escapeHtml" in js
    # The kpi() helper escapes value + suffix (was unescaped pre-fix).
    assert "escapeHtml(value)" in js
    assert "escapeHtml(suffix)" in js
    # renderTable escapes every cell.
    assert "escapeHtml(row[c.field]" in js
    # SR 26-2 quote is escaped (constant is trusted; this is defense-in-depth).
    assert "escapeHtml(SR_26_2_QUOTE)" in js


def test_tarball_includes_evidence_pack_bundle() -> None:
    """The tarball ships evidence_pack.js, evidence_pack.css, the new view XML, and the archive."""
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
    assert f"{top}/static/splunkgate-suit/evidence_pack.js" in names
    assert f"{top}/static/splunkgate-suit/evidence_pack.css" in names
    assert f"{top}/default/data/ui/views/regulator_evidence_pack.xml" in names
    # AppInspect rule: src/ stays out (PR-15 lesson).
    src_leaks = [n for n in names if n == f"{top}/src" or n.startswith(f"{top}/src/")]
    assert src_leaks == [], f"src/ leaked into tarball: {src_leaks}"
