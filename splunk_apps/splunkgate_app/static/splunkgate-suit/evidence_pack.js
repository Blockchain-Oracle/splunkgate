/* SplunkGate — Regulator Evidence Pack (SUIT bundle).
 *
 * Custom view bundle that replaces the Dashboard Studio v2 JSON-driven view.
 * Mounts to #splunkgate-evidence-pack and renders the Dossier-styled examiner
 * artifact: header + jurisdictional banner + Export PDF action (gated on
 * search completion) + 4-tile KPI strip + NIST RMF mapping + verbatim SR
 * 26-2 footnote 3 quote + EU AI Act Article 6 table + profile-conditional
 * HIPAA/PCI panels (hidden from print when gated) + footer with panel-status
 * line.
 *
 * SPL data sources are lifted verbatim from the archived Dashboard Studio v2
 * definition at docs/archive/dashboard-studio-v2/regulator_evidence_pack.xml.
 *
 * Search-lifecycle contract (matches TSX source-of-truth at
 * src/views/evidence_pack.tsx) — every search has a `cancelled` closure
 * flag; state changes cancel in-flight searches; AMD load failures + new
 * SearchManager() throws + 30s hangs all surface as setError(); Export PDF
 * is disabled while any search is in flight or any panel is in error.
 */
(function () {
    "use strict";

    var MOUNT_ID = "splunkgate-evidence-pack";
    var SEARCH_TIMEOUT_MS = 30000;
    var SEARCH_ID_SEQ = 0;

    /* SPL queries — verbatim from the archived Dashboard Studio v2 spec.
     * The $input_jurisdictional_tag$ token is dropped (we gate HIPAA/PCI
     * client-side now), so the queries are simpler than the archive's;
     * the substantive SPL is unchanged. */
    var QUERIES = {
        header_kpis: '`splunkgate_data` | stats count as total_decisions, dc(trace_id) as unique_traces, count(eval(explanation!="")) as attested_decisions',
        nist_rmf: '| makeresults count=4 | eval _time=now() | streamstats count as row | eval function = case(row=1,"GOVERN", row=2,"MAP", row=3,"MEASURE", row=4,"MANAGE"), splunkgate_components = case(row=1,"S1 middleware policy enforcement; S4 dashboards expose accountability roles", row=2,"S2 MCP server enumerates agent boundaries; splunkgate_verdict_history KV-store maps decision context", row=3,"S4 eval harness produces precision/recall/F1/ECE; OTel gen_ai.evaluation.result events emit per-decision scores", row=4,"S1 model_middleware blocks/redacts; story-mw-08 audit chain threads pre+post trace_ids; story-app-08 RBA closes the loop in ES"), evidence_query = case(row=1,"`splunkgate_data` surface=mw_model | stats count", row=2,"`splunkgate_data` | stats dc(agent_id) as agents dc(surface) as surfaces", row=3,"index=cisco_ai_defense sourcetype=cisco_ai_defense:splunkgate_verdict | stats count", row=4,"`splunkgate_data` verdict_label=block | stats count by agent_id") | table function splunkgate_components evidence_query',
        eu_article_6: '| makeresults count=5 | eval _time=now() | streamstats count as row | eval annex_iii_use_case = case(row=1,"Critical infrastructure (Annex III §2)", row=2,"Employment, worker management (Annex III §4)", row=3,"Essential private/public services (Annex III §5)", row=4,"Law enforcement (Annex III §6)", row=5,"Administration of justice + democratic processes (Annex III §8)"), article_6_trigger = case(row=1,"Article 6(2) — Annex III listed", row=2,"Article 6(2) — Annex III + profiling clause (paragraph 3 last subparagraph)", row=3,"Article 6(2) — Annex III", row=4,"Article 6(2) — Annex III", row=5,"Article 6(2) — Annex III + profiling clause"), splunkgate_response = case(row=1,"S1 model_middleware blocks injection attempts; verdicts logged with trace_id for Article 9 risk-management evidence", row=2,"S1 PII/PHI redaction; story-app-07 HIPAA panel renders detection counts by Safe Harbor 18 identifier", row=3,"All 4 surfaces emit OTel events; story-app-08 RBA escalates HIGH-severity to ES analyst", row=4,"Foundation-Sec explainer (or template v1) attaches WHY-string for due-process review", row=5,"PCI panel + audit-chain trace_ids satisfy decision-traceability obligations") | table annex_iii_use_case article_6_trigger splunkgate_response',
        hipaa: '`splunkgate_data` rule=PHI | stats count by surface, agent_id | sort -count | head 18',
        pci: '`splunkgate_data` rule=PCI | stats count by surface, agent_id, severity | sort -count',
        footer: '| makeresults | eval _time=now() | eval generated = strftime(now(),"%Y-%m-%d %H:%M:%S %Z") | eval app_version = "SplunkGate v1.0.0" | table app_version generated'
    };

    /* The SR 26-2 footnote 3 quote — verbatim from the joint Federal Reserve
     * / OCC / FDIC SR 26-2 Attachment, p. 3, April 17, 2026. DO NOT
     * paraphrase, summarize, or abridge — this is the load-bearing trust
     * signal of the entire artifact. escapeHtml() is applied at render time
     * as defense-in-depth; the constant itself is trusted. Wire form of the
     * apostrophe will be &#39; (HTML entity); the rendered DOM displays it
     * as a normal ASCII apostrophe. */
    var SR_26_2_QUOTE =
        "Generative AI and agentic AI models are novel and rapidly evolving. " +
        "As such, they are not within the scope of this guidance. Nonetheless, " +
        "a banking organization's risk management and governance practices " +
        "should guide the determination of appropriate governance and " +
        "controls for any tools, processes, or systems not covered in this " +
        "document. However, the principles described in this guidance apply " +
        "to traditional statistical and quantitative models and non-generative, " +
        "non-agentic AI models.";

    var SR_26_2_ATTRIBUTION =
        "SR 26-2 Attachment, footnote 3, p. 3 — joint Federal Reserve / OCC / FDIC, April 17, 2026.";

    var JURISDICTIONAL_PROFILES = [
        { value: "ALL", label: "All profiles" },
        { value: "FSI", label: "FSI (FFIEC-AIML / SR 26-2)" },
        { value: "HIPAA", label: "HIPAA (Safe Harbor 18)" },
        { value: "PCI", label: "PCI (PCI-DSS 11.x)" },
        { value: "PUBSEC", label: "PUBSEC (NIST AI RMF)" }
    ];

    var TIME_PRESETS = [
        { value: "-24h@h", label: "Last 24 hours" },
        { value: "-7d@d", label: "Last 7 days" },
        { value: "-30d@d", label: "Last 30 days" },
        { value: "-90d@d", label: "Last 90 days" },
        { value: "-365d@d", label: "Last 365 days" }
    ];

    /* Local state — single source of truth for renders. */
    var state = {
        jurisdictionalTag: "ALL",
        earliest: "-30d@d",
        latest: "now",
        searches: {},
        panelStatus: {
            header_kpis: "idle",
            nist_rmf: "idle",
            eu_article_6: "idle",
            hipaa: "idle",
            pci: "idle",
            footer: "idle"
        }
    };

    function escapeHtml(s) {
        if (s === null || s === undefined) {
            return "";
        }
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatLabel(earliest) {
        var preset = TIME_PRESETS.filter(function (p) { return p.value === earliest; })[0];
        return preset ? preset.label : earliest + " → now";
    }

    function profileLabel(tag) {
        var p = JURISDICTIONAL_PROFILES.filter(function (x) { return x.value === tag; })[0];
        return p ? p.label : tag;
    }

    function isHipaaActive() {
        return state.jurisdictionalTag === "HIPAA" || state.jurisdictionalTag === "ALL";
    }

    function isPciActive() {
        return state.jurisdictionalTag === "PCI" || state.jurisdictionalTag === "ALL";
    }

    function renderShell(root) {
        var optsJur = JURISDICTIONAL_PROFILES.map(function (p) {
            var sel = p.value === state.jurisdictionalTag ? " selected" : "";
            return '<option value="' + escapeHtml(p.value) + '"' + sel + ">" + escapeHtml(p.label) + "</option>";
        }).join("");
        var optsTime = TIME_PRESETS.map(function (p) {
            var sel = p.value === state.earliest ? " selected" : "";
            return '<option value="' + escapeHtml(p.value) + '"' + sel + ">" + escapeHtml(p.label) + "</option>";
        }).join("");

        root.innerHTML = [
            '<div class="splunkgate-suit">',
            '<div class="ep-page">',
            '<header class="ep-header">',
            '<div>',
            '<h1 class="ep-header-title">SplunkGate — Regulator Evidence Pack</h1>',
            '<div class="ep-header-subtitle">Single-shot examiner artifact. Choose your jurisdictional profile and time window; export to PDF for the record.</div>',
            '</div>',
            '<div class="ep-controls">',
            '<div class="ep-control"><label for="ep-jur">Jurisdictional profile</label>',
            '<select id="ep-jur">' + optsJur + '</select></div>',
            '<div class="ep-control"><label for="ep-time">Coverage period</label>',
            '<select id="ep-time">' + optsTime + '</select></div>',
            '<button type="button" class="ep-export-btn" id="ep-export" disabled>Export PDF for examiner record</button>',
            '</div>',
            '</header>',
            '<div class="ep-jurisdiction-banner" id="ep-jurisdiction-banner"></div>',
            '<section class="ep-kpis" id="ep-kpis-section"></section>',
            '<section class="ep-grid">',
            '<div class="ep-panel" id="ep-nist-panel">',
            '<h2>NIST AI RMF function mapping</h2>',
            '<p class="ep-panel-desc">4 functions per NIST AI RMF 1.0 Section 5: GOVERN, MAP, MEASURE, MANAGE. Each row pairs the function with the SplunkGate components that produce evidence and the SPL the examiner can run to verify the claim.</p>',
            '<div class="ep-panel-body" id="ep-nist-body"></div>',
            '</div>',
            '<div class="ep-quote-panel ep-panel" id="ep-quote-panel">',
            '<h2>SR 26-2 footnote 3 (April 2026) — out of named MRM scope</h2>',
            '<p class="ep-quote">' + escapeHtml(SR_26_2_QUOTE) + '</p>',
            '<div class="ep-quote-attribution">' + escapeHtml(SR_26_2_ATTRIBUTION) + '</div>',
            '<p class="ep-quote-framing"><strong>SplunkGate framing:</strong> SR 26-2 explicitly leaves GenAI / agentic AI out of named MRM scope. Examiners therefore rely on the bank\'s general risk management and governance practices to evaluate SplunkGate-instrumented agents. Every SplunkGate verdict carries a trace_id, an evaluator chain, and an OTel event — together these constitute the auditable evidence chain the footnote anticipates.</p>',
            '</div>',
            '</section>',
            '<div class="ep-panel" id="ep-eu-panel">',
            '<h2>EU AI Act Article 6 — high-risk classification mapping</h2>',
            '<p class="ep-panel-desc">Article 6 high-risk classification triggers (Article 6(1) product-safety integration + Article 6(2) Annex III enumeration). High-risk Annex III obligations under Article 6(2) apply from 2 August 2026. SplunkGate decisions can satisfy Article 9 (risk management) evidence obligations.</p>',
            '<div class="ep-panel-body" id="ep-eu-body"></div>',
            '</div>',
            '<div class="ep-panel ep-gated" id="ep-hipaa-panel">',
            '<h2>HIPAA Safe Harbor 18 — PHI detection counts</h2>',
            '<p class="ep-panel-desc">PHI detection counts grouped by surface and agent for the coverage window.</p>',
            '<div class="ep-panel-body" id="ep-hipaa-body"></div>',
            '</div>',
            '<div class="ep-panel ep-gated" id="ep-pci-panel">',
            '<h2>PCI DSS 11.x — PCI detection counts</h2>',
            '<p class="ep-panel-desc">PCI detection counts grouped by surface, agent, and severity. Supports PCI-DSS 4.0 11.x sub-requirements via the persisted KV-store retention of PCI-tagged trace_ids.</p>',
            '<div class="ep-panel-body" id="ep-pci-body"></div>',
            '</div>',
            '<footer class="ep-footer" id="ep-footer">',
            '<span>SplunkGate v1.0.0</span>',
            '<span id="ep-footer-coverage">' + escapeHtml(formatLabel(state.earliest)) + '</span>',
            '<span id="ep-footer-status"></span>',
            '<span id="ep-footer-generated"></span>',
            '</footer>',
            '</div>',
            '</div>'
        ].join("");
    }

    function setLoading(elId, panelKey) {
        var el = document.getElementById(elId);
        if (el) { el.innerHTML = '<div class="ep-state">Loading…</div>'; }
        if (panelKey) { state.panelStatus[panelKey] = "loading"; updateExportGate(); }
    }

    function setError(elId, errMsg, panelKey) {
        var el = document.getElementById(elId);
        if (el) {
            // Hard-edged error treatment so it survives black-and-white print:
            // red top border (handled in CSS via .ep-state-error wrapper),
            // bold "PANEL FAILED TO LOAD" header, monospace error body.
            el.innerHTML = (
                '<div class="ep-state-error-wrap">' +
                '<div class="ep-state-error-head">PANEL FAILED TO LOAD</div>' +
                '<div class="ep-state-error-msg">' + escapeHtml(errMsg) + '</div>' +
                '</div>'
            );
        }
        if (panelKey) { state.panelStatus[panelKey] = "error"; updateExportGate(); }
    }

    function setEmpty(elId, msg, panelKey) {
        var el = document.getElementById(elId);
        if (el) { el.innerHTML = '<div class="ep-state ep-state-empty">' + escapeHtml(msg) + '</div>'; }
        if (panelKey) { state.panelStatus[panelKey] = "ok"; updateExportGate(); }
    }

    function setOk(panelKey) {
        if (panelKey) { state.panelStatus[panelKey] = "ok"; updateExportGate(); }
    }

    function updateExportGate() {
        var btn = document.getElementById("ep-export");
        var status = document.getElementById("ep-footer-status");
        if (!btn || !status) { return; }
        var loading = 0;
        var errored = 0;
        var ok = 0;
        // Only count panels that are actually visible under the current profile.
        var keys = ["header_kpis", "nist_rmf", "eu_article_6", "footer"];
        if (isHipaaActive()) { keys.push("hipaa"); }
        if (isPciActive()) { keys.push("pci"); }
        keys.forEach(function (k) {
            var s = state.panelStatus[k];
            if (s === "loading" || s === "idle") { loading += 1; }
            else if (s === "error") { errored += 1; }
            else if (s === "ok") { ok += 1; }
        });
        var allOk = (loading === 0 && errored === 0 && keys.length > 0);
        btn.disabled = !allOk;
        if (loading > 0) {
            btn.textContent = "Waiting for " + loading + " panel" + (loading === 1 ? "" : "s") + "…";
            status.textContent = "Panel status: " + ok + " OK / " + errored + " errored / " + loading + " loading";
        } else if (errored > 0) {
            btn.textContent = errored + " panel" + (errored === 1 ? "" : "s") + " failed — fix before export";
            status.textContent = "Panel status: " + ok + " OK / " + errored + " errored";
        } else {
            btn.textContent = "Export PDF for examiner record";
            status.textContent = "Panel status: " + ok + " OK";
        }
    }

    function renderJurisdictionBanner() {
        var el = document.getElementById("ep-jurisdiction-banner");
        if (!el) { return; }
        var label = profileLabel(state.jurisdictionalTag);
        // Examiner-readable scope statement. Never reference UI affordances
        // here — the user will see this in the PDF.
        var scope = "";
        if (state.jurisdictionalTag === "ALL") {
            scope = "All in-scope profiles are included in this artifact (FSI / HIPAA / PCI / PUBSEC). Both the HIPAA Safe Harbor 18 and PCI DSS 11.x panels are populated below.";
        } else if (state.jurisdictionalTag === "HIPAA") {
            scope = "Scope: HIPAA Safe Harbor 18. The HIPAA panel below is populated; the PCI panel is excluded from this profile and is omitted from the artifact.";
        } else if (state.jurisdictionalTag === "PCI") {
            scope = "Scope: PCI DSS 11.x. The PCI panel below is populated; the HIPAA panel is excluded from this profile and is omitted from the artifact.";
        } else if (state.jurisdictionalTag === "FSI") {
            scope = "Scope: FSI (FFIEC-AIML / SR 26-2). Neither HIPAA nor PCI panels are in scope for this profile; both are omitted from the artifact.";
        } else if (state.jurisdictionalTag === "PUBSEC") {
            scope = "Scope: PUBSEC (NIST AI RMF). Neither HIPAA nor PCI panels are in scope for this profile; both are omitted from the artifact.";
        }
        el.innerHTML = (
            '<div class="ep-banner-label">Coverage profile</div>' +
            '<div class="ep-banner-value">' + escapeHtml(label) + '</div>' +
            '<div class="ep-banner-scope">' + escapeHtml(scope) + '</div>'
        );
    }

    function applyProfileVisibility() {
        var hipaa = document.getElementById("ep-hipaa-panel");
        var pci = document.getElementById("ep-pci-panel");
        if (hipaa) {
            hipaa.classList.toggle("ep-hidden", !isHipaaActive());
        }
        if (pci) {
            pci.classList.toggle("ep-hidden", !isPciActive());
        }
    }

    /* Kpi helpers — escape inside the helper so callers can't forget. */
    function renderHeaderKpis(rows) {
        var section = document.getElementById("ep-kpis-section");
        if (!section) { return; }
        var r = (rows && rows[0]) || {};
        var total = r.total_decisions || "0";
        var traces = r.unique_traces || "0";
        var attested = r.attested_decisions || "0";
        var pct = "0%";
        var totalNum = parseInt(total, 10) || 0;
        var attestedNum = parseInt(attested, 10) || 0;
        if (totalNum > 0) {
            pct = Math.round((attestedNum / totalNum) * 100) + "%";
        }
        section.innerHTML = [
            kpi("Coverage period", formatLabel(state.earliest), "earliest → now"),
            kpi("Total decisions", total, "verdicts in window"),
            kpi("Unique trace IDs", traces, "agent sessions"),
            kpi("Attested decisions", attested, pct + " with explanation")
        ].join("");
        setOk("header_kpis");
    }

    function kpi(label, value, suffix) {
        return [
            '<div class="ep-kpi">',
            '<div class="ep-kpi-label">' + escapeHtml(label) + '</div>',
            '<div class="ep-kpi-value">' + escapeHtml(value) + '</div>',
            '<div class="ep-kpi-suffix">' + escapeHtml(suffix) + '</div>',
            '</div>'
        ].join("");
    }

    function renderTable(bodyId, columns, rows, emptyMsg, panelKey) {
        var el = document.getElementById(bodyId);
        if (!el) { return; }
        if (!rows || rows.length === 0) {
            setEmpty(bodyId, emptyMsg, panelKey);
            return;
        }
        var header = '<tr>' + columns.map(function (c) {
            return '<th>' + escapeHtml(c.label) + '</th>';
        }).join("") + '</tr>';
        // Every cell value goes through escapeHtml — defense-in-depth against
        // hostile agent_id / explanation strings from the wire.
        var body = rows.map(function (row) {
            return '<tr>' + columns.map(function (c) {
                var cls = "";
                if (c.mono) { cls = ' class="ep-mono"'; }
                if (c.functionCol) { cls = ' class="ep-function"'; }
                return '<td' + cls + '>' + escapeHtml(row[c.field] || "") + '</td>';
            }).join("") + '</tr>';
        }).join("");
        el.innerHTML = '<table class="ep-table"><thead>' + header + '</thead><tbody>' + body + '</tbody></table>';
        setOk(panelKey);
    }

    function renderNist(rows) {
        renderTable(
            "ep-nist-body",
            [
                { field: "function", label: "Function", functionCol: true },
                { field: "splunkgate_components", label: "SplunkGate components" },
                { field: "evidence_query", label: "Evidence SPL", mono: true }
            ],
            rows,
            "No NIST RMF rows returned.",
            "nist_rmf"
        );
    }

    function renderEu(rows) {
        renderTable(
            "ep-eu-body",
            [
                { field: "annex_iii_use_case", label: "Annex III use case" },
                { field: "article_6_trigger", label: "Article 6 trigger" },
                { field: "splunkgate_response", label: "SplunkGate response" }
            ],
            rows,
            "No EU AI Act rows returned.",
            "eu_article_6"
        );
    }

    function renderHipaa(rows) {
        renderTable(
            "ep-hipaa-body",
            [
                { field: "count", label: "PHI hits" },
                { field: "surface", label: "Surface", mono: true },
                { field: "agent_id", label: "Agent ID", mono: true }
            ],
            rows,
            "No PHI verdicts in the selected coverage period.",
            "hipaa"
        );
    }

    function renderPci(rows) {
        renderTable(
            "ep-pci-body",
            [
                { field: "count", label: "PCI hits" },
                { field: "surface", label: "Surface", mono: true },
                { field: "agent_id", label: "Agent ID", mono: true },
                { field: "severity", label: "Severity" }
            ],
            rows,
            "No PCI verdicts in the selected coverage period.",
            "pci"
        );
    }

    function renderFooter(rows) {
        var r = (rows && rows[0]) || {};
        var gen = document.getElementById("ep-footer-generated");
        if (gen) { gen.textContent = "Generated " + (r.generated || ""); }
        setOk("footer");
    }

    /* runSearch — cancellable, errback-wired, timeout-bounded.
     *
     * Returns nothing; effects flow through onResults / onError. Every call
     * captures a per-call ctx with `cancelled` flag; a newer call supersedes
     * by setting the previous ctx.cancelled = true and calling mgr.cancel().
     * Late-arriving AMD callbacks / data events / search:error events all
     * check the flag before touching the DOM. */
    function runSearch(id, query, resultsCount, onResults, onError) {
        var prev = state.searches[id];
        if (prev) {
            prev.cancelled = true;
            if (prev.mgr && typeof prev.mgr.cancel === "function") {
                prev.mgr.cancel();
            }
            if (prev.timer) { clearTimeout(prev.timer); }
        }
        var ctx = { cancelled: false, mgr: null, timer: null };
        state.searches[id] = ctx;

        if (typeof require !== "function") {
            onError("Splunk runtime not detected (require is undefined)");
            return;
        }

        ctx.timer = setTimeout(function () {
            if (ctx.cancelled) { return; }
            ctx.cancelled = true;
            if (ctx.mgr && typeof ctx.mgr.cancel === "function") { ctx.mgr.cancel(); }
            onError("Search timed out after " + (SEARCH_TIMEOUT_MS / 1000) + "s — no response from Splunk Search SDK");
        }, SEARCH_TIMEOUT_MS);

        require(
            ["splunkjs/mvc/searchmanager"],
            function (SearchManager) {
                if (ctx.cancelled) { return; }
                try {
                    SEARCH_ID_SEQ += 1;
                    ctx.mgr = new SearchManager({
                        id: "splunkgate-ep-" + id + "-" + SEARCH_ID_SEQ,
                        preview: false,
                        cache: false,
                        search: query,
                        earliest_time: state.earliest,
                        latest_time: state.latest
                    });
                } catch (e) {
                    if (ctx.cancelled) { return; }
                    ctx.cancelled = true;
                    if (ctx.timer) { clearTimeout(ctx.timer); }
                    onError("SearchManager construction failed: " + (e && e.message ? e.message : "unknown error"));
                    return;
                }
                ctx.mgr.on("search:error", function (props) {
                    if (ctx.cancelled) { return; }
                    ctx.cancelled = true;
                    if (ctx.timer) { clearTimeout(ctx.timer); }
                    onError(props && props.message ? props.message : "Splunk search returned an error (no message)");
                });
                ctx.mgr.data("results", { count: resultsCount, offset: 0 }).on("data", function (_unused, data) {
                    if (ctx.cancelled) { return; }
                    ctx.cancelled = true;
                    if (ctx.timer) { clearTimeout(ctx.timer); }
                    onResults(data && data.results ? data.results : []);
                });
            },
            function (err) {
                if (ctx.cancelled) { return; }
                ctx.cancelled = true;
                if (ctx.timer) { clearTimeout(ctx.timer); }
                onError(
                    "Splunk Search SDK failed to load: " +
                    (err && err.message ? err.message : (err && err.requireType ? err.requireType : "unknown require error"))
                );
            }
        );
    }

    function refreshAll() {
        renderJurisdictionBanner();
        applyProfileVisibility();

        setLoading("ep-kpis-section", "header_kpis");
        setLoading("ep-nist-body", "nist_rmf");
        setLoading("ep-eu-body", "eu_article_6");

        runSearch("header_kpis", QUERIES.header_kpis, 1, renderHeaderKpis, function (e) { setError("ep-kpis-section", e, "header_kpis"); });
        runSearch("nist_rmf", QUERIES.nist_rmf, 10, renderNist, function (e) { setError("ep-nist-body", e, "nist_rmf"); });
        runSearch("eu_article_6", QUERIES.eu_article_6, 10, renderEu, function (e) { setError("ep-eu-body", e, "eu_article_6"); });

        if (isHipaaActive()) {
            setLoading("ep-hipaa-body", "hipaa");
            runSearch("hipaa", QUERIES.hipaa, 18, renderHipaa, function (e) { setError("ep-hipaa-body", e, "hipaa"); });
        } else {
            state.panelStatus.hipaa = "ok"; // not in scope; treat as resolved.
        }
        if (isPciActive()) {
            setLoading("ep-pci-body", "pci");
            runSearch("pci", QUERIES.pci, 50, renderPci, function (e) { setError("ep-pci-body", e, "pci"); });
        } else {
            state.panelStatus.pci = "ok";
        }
        runSearch("footer", QUERIES.footer, 1, renderFooter, function () { setOk("footer"); });
        updateExportGate();
    }

    function wireControls() {
        var jur = document.getElementById("ep-jur");
        if (jur) {
            jur.addEventListener("change", function (e) {
                state.jurisdictionalTag = e.target.value;
                refreshAll();
            });
        }
        var time = document.getElementById("ep-time");
        if (time) {
            time.addEventListener("change", function (e) {
                state.earliest = e.target.value;
                var coverage = document.getElementById("ep-footer-coverage");
                if (coverage) { coverage.textContent = formatLabel(state.earliest); }
                refreshAll();
            });
        }
        var btn = document.getElementById("ep-export");
        if (btn) {
            btn.addEventListener("click", function () {
                if (btn.disabled) { return; }
                window.print();
            });
        }
    }

    function mount() {
        var root = document.getElementById(MOUNT_ID);
        if (!root) {
            if (typeof console !== "undefined" && console.warn) {
                console.warn("[splunkgate-evidence-pack] mount node #" + MOUNT_ID + " not found");
            }
            return;
        }
        renderShell(root);
        wireControls();
        refreshAll();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", mount);
    } else {
        mount();
    }
}());
