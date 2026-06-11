/* SplunkGate — Verdict Inspector (SUIT bundle).
 *
 * D3 "microscope": filter bar (5 controls) → verdict list (left, 60%) →
 * detail panel + related events (right, 40%). Row click drives the detail
 * panel + the related-events sub-panel (other verdicts under the same
 * trace_id, across all four surfaces). Drill-down to ES investigation
 * workbench from the detail panel.
 *
 * trace_id copy-to-clipboard is the hero micro-interaction: 1-click copy,
 * 800ms green "copied" confirmation. Uses navigator.clipboard when
 * available, falls back to document.execCommand("copy") for Splunk Web
 * deployments that don't serve over HTTPS.
 *
 * SPL queries lifted verbatim from
 * docs/archive/dashboard-studio-v2/verdict_inspector.xml. The
 * $input_*$ token substitution that Dashboard Studio v2 did server-side
 * now runs client-side via template substitution.
 *
 * Search-lifecycle contract mirrors evidence_pack.js + agent_risk_overview.js:
 * errback-wired require(), try/catch around new SearchManager(), 30s
 * timeout, per-call cancelled-flag closure, cancelAll() before refresh
 * waves.
 */
(function () {
    "use strict";

    var MOUNT_ID = "splunkgate-verdict-inspector";
    var SEARCH_TIMEOUT_MS = 30000;
    var SEARCH_ID_SEQ = 0;

    var QUERIES = {
        agents_list: '`splunkgate_data` | stats values(agent_id) as agent_id | mvexpand agent_id | rename agent_id as label | eval value=label',
        rules_list: '`splunkgate_data` | mvexpand rule | stats values(rule) as rule | mvexpand rule | rename rule as label | eval value=label',
        // {AGENT} {SEVERITY} {VERDICT_LABEL} {RULE} substituted client-side
        // before launching the search. The wildcard `*` lifts verbatim
        // from the Dashboard Studio v2 contract.
        table: '`splunkgate_data` agent_id="{AGENT}" severity="{SEVERITY}" verdict_label="{VERDICT_LABEL}" rule="{RULE}" | eval explanation_short = if(len(explanation)>120, substr(explanation,1,120)."…", explanation) | table _time agent_id surface verdict_label severity rule explanation_short latency_ms trace_id | sort -_time | head 200',
        detail: '`splunkgate_data` trace_id="{TRACE_ID}" | head 1 | table _time agent_id surface verdict_label severity rule explanation latency_ms trace_id atlas_technique_id atlas_technique_name atlas_tactic_id',
        related: '`splunkgate_data` trace_id="{TRACE_ID}" | table _time surface verdict_label severity rule | sort _time'
    };

    var SEVERITY_OPTIONS = [
        { value: "*", label: "Any" },
        { value: "HIGH", label: "HIGH" },
        { value: "MEDIUM", label: "MEDIUM" },
        { value: "LOW", label: "LOW" },
        { value: "NONE_SEVERITY", label: "NONE_SEVERITY" }
    ];

    var VERDICT_LABEL_OPTIONS = [
        { value: "*", label: "Any" },
        { value: "block", label: "block" },
        { value: "modify", label: "modify" },
        { value: "review", label: "review" },
        { value: "allow", label: "allow" }
    ];

    var TIME_PRESETS = [
        { value: "-1h@h", label: "Last 1 hour" },
        { value: "-24h@h", label: "Last 24 hours" },
        { value: "-7d@d", label: "Last 7 days" },
        { value: "-30d@d", label: "Last 30 days" }
    ];

    var state = {
        earliest: "-24h@h",
        latest: "now",
        agent: "*",
        rule: "*",
        severity: "*",
        verdictLabel: "*",
        agentsOptions: [{ value: "*", label: "Any" }],
        rulesOptions: [{ value: "*", label: "Any" }],
        searches: {},
        listRows: [],
        selectedTraceId: null
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

    // Splunk SPL values flowing into the search string via template subst.
    // Wildcard `*` is allowed (verbatim contract); anything else is
    // sanitized to alnum+@.-_ to prevent SPL injection from a hostile
    // agent_id or trace_id stored upstream.
    function sanitizeSplValue(v) {
        if (!v) { return "*"; }
        if (v === "*") { return "*"; }
        return String(v).replace(/[^A-Za-z0-9@._\-:]/g, "");
    }

    function renderShell(root) {
        var optsTime = TIME_PRESETS.map(function (p) {
            var sel = p.value === state.earliest ? " selected" : "";
            return '<option value="' + escapeHtml(p.value) + '"' + sel + ">" + escapeHtml(p.label) + "</option>";
        }).join("");
        var optsSev = SEVERITY_OPTIONS.map(function (p) {
            var sel = p.value === state.severity ? " selected" : "";
            return '<option value="' + escapeHtml(p.value) + '"' + sel + ">" + escapeHtml(p.label) + "</option>";
        }).join("");
        var optsLabel = VERDICT_LABEL_OPTIONS.map(function (p) {
            var sel = p.value === state.verdictLabel ? " selected" : "";
            return '<option value="' + escapeHtml(p.value) + '"' + sel + ">" + escapeHtml(p.label) + "</option>";
        }).join("");

        root.innerHTML = [
            '<div class="splunkgate-suit">',
            '<div class="vi-page">',
            '<header class="vi-header">',
            '<div>',
            '<h1 class="vi-header-title">SplunkGate — Verdict Inspector</h1>',
            '<div class="vi-header-subtitle">Filter by time / agent / rule / severity / verdict label. Click a row to see full provenance + every other verdict from the same trace_id across all four SplunkGate surfaces.</div>',
            '</div>',
            '</header>',
            '<section class="vi-filter-bar">',
            '<div class="vi-control"><label for="vi-time">Time range</label>',
            '<select id="vi-time">' + optsTime + '</select></div>',
            '<div class="vi-control"><label for="vi-agent">Agent</label>',
            '<select id="vi-agent"><option value="*">Any</option></select></div>',
            '<div class="vi-control"><label for="vi-rule">Rule</label>',
            '<select id="vi-rule"><option value="*">Any</option></select></div>',
            '<div class="vi-control"><label for="vi-severity">Severity</label>',
            '<select id="vi-severity">' + optsSev + '</select></div>',
            '<div class="vi-control"><label for="vi-verdict">Verdict label</label>',
            '<select id="vi-verdict">' + optsLabel + '</select></div>',
            '<button type="button" class="vi-clear-btn" id="vi-clear" title="Reset all filters">Clear</button>',
            '</section>',
            '<section class="vi-body">',
            '<div class="vi-panel" id="vi-list-panel">',
            '<h2>Verdicts (latest 200)</h2>',
            '<p class="vi-panel-desc">Click a row to inspect that verdict. Highlight + detail panel update in &lt;200ms.</p>',
            '<div class="vi-list-wrap" id="vi-list-body"></div>',
            '</div>',
            '<div>',
            '<div class="vi-panel" id="vi-detail-panel">',
            '<h2>Verdict detail</h2>',
            '<p class="vi-panel-desc">Full provenance for the selected trace_id including MITRE ATLAS technique mapping. Drill into ES Investigation Workbench from the button below.</p>',
            '<div id="vi-detail-body"><div class="vi-detail-empty">No verdict selected — click a row in the table on the left.</div></div>',
            '</div>',
            '<div class="vi-panel" id="vi-related-panel">',
            '<h2>Related events for this trace_id</h2>',
            '<p class="vi-panel-desc">Every other SplunkGate verdict emitted under the same trace_id, across all four surfaces (mw_model / mw_tool / mw_subagent / mcp_*).</p>',
            '<div id="vi-related-body"><div class="vi-detail-empty">No trace_id selected.</div></div>',
            '</div>',
            '</div>',
            '</section>',
            '<footer class="vi-footer" id="vi-footer">',
            '<span>SplunkGate v1.0.0</span>',
            '<span id="vi-footer-count">—</span>',
            '<span id="vi-footer-status">Loading…</span>',
            '</footer>',
            '</div>',
            '</div>'
        ].join("");
    }

    function fillDropdown(id, options, currentValue) {
        var el = document.getElementById(id);
        if (!el) { return; }
        el.innerHTML = options.map(function (o) {
            var sel = o.value === currentValue ? " selected" : "";
            return '<option value="' + escapeHtml(o.value) + '"' + sel + ">" + escapeHtml(o.label) + "</option>";
        }).join("");
    }

    function setPanelError(bodyId, errMsg) {
        var el = document.getElementById(bodyId);
        if (!el) { return; }
        el.innerHTML = (
            '<div class="vi-state-error-wrap">' +
            '<div class="vi-state-error-head">PANEL FAILED TO LOAD</div>' +
            '<div class="vi-state-error-msg">' + escapeHtml(errMsg) + '</div>' +
            '</div>'
        );
    }

    function setPanelEmpty(bodyId, msg) {
        var el = document.getElementById(bodyId);
        if (el) { el.innerHTML = '<div class="vi-state">' + escapeHtml(msg) + '</div>'; }
    }

    function setPanelLoading(bodyId) {
        setPanelEmpty(bodyId, "Loading…");
    }

    function severityChip(sev) {
        var s = sev || "NONE_SEVERITY";
        return '<span class="vi-chip vi-sev-' + escapeHtml(s) + '">' + escapeHtml(s) + "</span>";
    }

    function resultChip(label) {
        var v = (label || "").toLowerCase();
        if (!v) { return ""; }
        return '<span class="vi-result vi-result-' + escapeHtml(v) + '">' + escapeHtml(v) + "</span>";
    }

    function renderAgentsList(rows) {
        var opts = [{ value: "*", label: "Any" }];
        if (rows && rows.length > 0) {
            rows.forEach(function (r) {
                if (r.value) { opts.push({ value: r.value, label: r.label || r.value }); }
            });
        }
        state.agentsOptions = opts;
        fillDropdown("vi-agent", opts, state.agent);
    }

    function renderRulesList(rows) {
        var opts = [{ value: "*", label: "Any" }];
        if (rows && rows.length > 0) {
            rows.forEach(function (r) {
                if (r.value) { opts.push({ value: r.value, label: r.label || r.value }); }
            });
        }
        state.rulesOptions = opts;
        fillDropdown("vi-rule", opts, state.rule);
    }

    function renderList(rows) {
        var body = document.getElementById("vi-list-body");
        if (!body) { return; }
        state.listRows = rows || [];
        if (!rows || rows.length === 0) {
            setPanelEmpty("vi-list-body", "No verdicts match the current filters in the selected time range.");
            updateFooterCount(0);
            return;
        }
        var headerCells = '<tr>' +
            '<th>Time</th>' +
            '<th>Agent</th>' +
            '<th>Surface</th>' +
            '<th>Verdict</th>' +
            '<th>Severity</th>' +
            '<th>Rule</th>' +
            '<th>Explanation</th>' +
            '<th>Latency</th>' +
            '<th>Trace</th>' +
            '</tr>';
        var bodyRows = rows.map(function (r, i) {
            var traceId = r.trace_id || "";
            var time = r._time ? r._time.substring(0, 19).replace("T", " ") : "";
            var selectedClass = traceId === state.selectedTraceId ? " vi-row-selected" : "";
            return (
                '<tr class="vi-row' + selectedClass + '" data-trace-id="' + escapeHtml(traceId) + '" data-row-index="' + i + '">' +
                '<td class="vi-mono">' + escapeHtml(time) + '</td>' +
                '<td class="vi-mono">' + escapeHtml(r.agent_id || "") + '</td>' +
                '<td class="vi-mono">' + escapeHtml(r.surface || "") + '</td>' +
                '<td>' + resultChip(r.verdict_label) + '</td>' +
                '<td>' + severityChip(r.severity) + '</td>' +
                '<td>' + escapeHtml(r.rule || "") + '</td>' +
                '<td class="vi-explanation">' + escapeHtml(r.explanation_short || "") + '</td>' +
                '<td class="vi-mono">' + escapeHtml(r.latency_ms || "") + 'ms</td>' +
                '<td class="vi-mono">' + escapeHtml(traceId.substring(0, 8)) + '…</td>' +
                '</tr>'
            );
        }).join("");
        body.innerHTML = '<table class="vi-table"><thead>' + headerCells + '</thead><tbody>' + bodyRows + '</tbody></table>';
        updateFooterCount(rows.length);
        // Wire row clicks via delegation.
        var tbody = body.querySelector("tbody");
        if (tbody) {
            tbody.addEventListener("click", function (e) {
                var row = e.target.closest && e.target.closest("tr.vi-row");
                if (!row) { return; }
                var traceId = row.getAttribute("data-trace-id");
                if (!traceId) { return; }
                selectRow(traceId);
            });
        }
    }

    function selectRow(traceId) {
        state.selectedTraceId = traceId;
        // Update row highlight.
        var rows = document.querySelectorAll("#vi-list-body tr.vi-row");
        rows.forEach(function (r) {
            r.classList.toggle("vi-row-selected", r.getAttribute("data-trace-id") === traceId);
        });
        // Refresh detail + related searches.
        setPanelLoading("vi-detail-body");
        setPanelLoading("vi-related-body");
        var safeTid = sanitizeSplValue(traceId);
        runSearch(
            "detail",
            QUERIES.detail.replace("{TRACE_ID}", safeTid),
            1,
            state.earliest, state.latest,
            renderDetail,
            function (m) { setPanelError("vi-detail-body", m); }
        );
        runSearch(
            "related",
            QUERIES.related.replace("{TRACE_ID}", safeTid),
            200,
            state.earliest, state.latest,
            renderRelated,
            function (m) { setPanelError("vi-related-body", m); }
        );
    }

    function renderDetail(rows) {
        var body = document.getElementById("vi-detail-body");
        if (!body) { return; }
        if (!rows || rows.length === 0) {
            body.innerHTML = '<div class="vi-detail-empty">No verdict found for trace_id ' +
                escapeHtml(state.selectedTraceId || "") + '.</div>';
            return;
        }
        var r = rows[0];
        var traceId = r.trace_id || state.selectedTraceId || "";
        var explanationHtml = r.explanation
            ? '<div class="vi-explanation-block">' + escapeHtml(r.explanation) + '</div>'
            : '<span class="vi-state">No explanation attached to this verdict.</span>';
        var esUrl = "/app/SplunkEnterpriseSecuritySuite/investigation_workbench?form.search=trace_id%3D%22" + encodeURIComponent(traceId) + "%22";
        var atlas = "";
        if (r.atlas_technique_id || r.atlas_technique_name) {
            atlas = (
                '<div class="vi-detail-field">' +
                '<div class="vi-detail-label">MITRE ATLAS</div>' +
                '<div class="vi-detail-value vi-mono">' +
                escapeHtml(r.atlas_technique_id || "") + ' · ' +
                escapeHtml(r.atlas_technique_name || "") +
                (r.atlas_tactic_id ? ' · tactic ' + escapeHtml(r.atlas_tactic_id) : "") +
                '</div></div>'
            );
        }
        body.innerHTML = [
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Time</div>',
            '<div class="vi-detail-value vi-mono">' + escapeHtml((r._time || "").substring(0, 19).replace("T", " ")) + '</div>',
            '</div>',
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Trace ID</div>',
            '<div class="vi-detail-value"><button type="button" class="vi-trace-chip" id="vi-trace-copy" data-trace-id="' + escapeHtml(traceId) + '">' +
            '<svg class="vi-trace-chip-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="9" height="11" rx="1"/><path d="M5 1h7a2 2 0 0 1 2 2v8"/></svg>' +
            '<span id="vi-trace-text">' + escapeHtml(traceId) + '</span></button></div>',
            '</div>',
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Agent</div>',
            '<div class="vi-detail-value vi-mono">' + escapeHtml(r.agent_id || "") + '</div>',
            '</div>',
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Surface</div>',
            '<div class="vi-detail-value vi-mono">' + escapeHtml(r.surface || "") + '</div>',
            '</div>',
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Verdict</div>',
            '<div class="vi-detail-value">' + resultChip(r.verdict_label) + ' &nbsp; ' + severityChip(r.severity) + '</div>',
            '</div>',
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Rule</div>',
            '<div class="vi-detail-value">' + escapeHtml(r.rule || "") + '</div>',
            '</div>',
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Latency</div>',
            '<div class="vi-detail-value vi-mono">' + escapeHtml(r.latency_ms || "") + ' ms</div>',
            '</div>',
            atlas,
            '<div class="vi-detail-field">',
            '<div class="vi-detail-label">Explanation</div>',
            '<div class="vi-detail-value">' + explanationHtml + '</div>',
            '</div>',
            '<a class="vi-es-drill-btn" href="' + escapeHtml(esUrl) + '" target="_blank" rel="noopener noreferrer">Open in ES Investigation Workbench →</a>'
        ].join("");

        wireTraceChip();
    }

    function wireTraceChip() {
        var btn = document.getElementById("vi-trace-copy");
        if (!btn) { return; }
        btn.addEventListener("click", function () {
            var tid = btn.getAttribute("data-trace-id") || "";
            copyToClipboard(tid).then(function () {
                btn.classList.add("vi-copied");
                var txt = document.getElementById("vi-trace-text");
                if (txt) {
                    var orig = txt.textContent;
                    txt.textContent = "copied!";
                    setTimeout(function () {
                        btn.classList.remove("vi-copied");
                        txt.textContent = orig;
                    }, 800);
                }
            }).catch(function () {
                // Best-effort: the chip stays as the trace_id; user can
                // long-press / right-click to copy manually.
                if (typeof console !== "undefined" && console.warn) {
                    console.warn("[splunkgate-verdict-inspector] copy-to-clipboard failed");
                }
            });
        });
    }

    function copyToClipboard(text) {
        // navigator.clipboard requires HTTPS + recent browser. Splunk Web
        // is often served over HTTP in air-gapped deployments, so fall
        // back to the document.execCommand("copy") pattern.
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
            try {
                var ta = document.createElement("textarea");
                ta.value = text;
                ta.style.position = "fixed";
                ta.style.top = "-1000px";
                ta.style.left = "-1000px";
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                var ok = document.execCommand("copy");
                document.body.removeChild(ta);
                if (ok) { resolve(); } else { reject(new Error("execCommand returned false")); }
            } catch (e) {
                reject(e);
            }
        });
    }

    function renderRelated(rows) {
        var body = document.getElementById("vi-related-body");
        if (!body) { return; }
        if (!rows || rows.length === 0) {
            body.innerHTML = '<div class="vi-detail-empty">No related events under this trace_id.</div>';
            return;
        }
        body.innerHTML = rows.map(function (r) {
            var t = r._time ? r._time.substring(11, 19) : "";
            return (
                '<div class="vi-related-row">' +
                '<span class="vi-related-time">' + escapeHtml(t) + '</span>' +
                '<span class="vi-related-rule">' + escapeHtml(r.rule || "") + '</span>' +
                '<span class="vi-related-surface">' + escapeHtml(r.surface || "") + '</span>' +
                resultChip(r.verdict_label) +
                '</div>'
            );
        }).join("");
    }

    function updateFooterCount(n) {
        var el = document.getElementById("vi-footer-count");
        if (el) { el.textContent = n + " row" + (n === 1 ? "" : "s"); }
    }

    function setFooterStatus(msg) {
        var el = document.getElementById("vi-footer-status");
        if (el) { el.textContent = msg; }
    }

    /* runSearch — cancellable, errback-wired, timeout-bounded. */
    function runSearch(id, query, resultsCount, earliest, latest, onResults, onError) {
        var prev = state.searches[id];
        if (prev) {
            prev.cancelled = true;
            if (prev.mgr && typeof prev.mgr.cancel === "function") { prev.mgr.cancel(); }
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
                        id: "splunkgate-vi-" + id + "-" + SEARCH_ID_SEQ,
                        preview: false,
                        cache: false,
                        search: query,
                        earliest_time: earliest,
                        latest_time: latest
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

    function cancelAll() {
        Object.keys(state.searches).forEach(function (id) {
            var s = state.searches[id];
            if (!s) { return; }
            s.cancelled = true;
            if (s.mgr && typeof s.mgr.cancel === "function") { s.mgr.cancel(); }
            if (s.timer) { clearTimeout(s.timer); }
        });
        state.searches = {};
    }

    function refreshList() {
        var e = state.earliest;
        var l = state.latest;
        var query = QUERIES.table
            .replace("{AGENT}", sanitizeSplValue(state.agent))
            .replace("{SEVERITY}", sanitizeSplValue(state.severity))
            .replace("{VERDICT_LABEL}", sanitizeSplValue(state.verdictLabel))
            .replace("{RULE}", sanitizeSplValue(state.rule));
        setPanelLoading("vi-list-body");
        setFooterStatus("Loading verdict list…");
        runSearch("table", query, 200, e, l, function (rows) {
            renderList(rows);
            setFooterStatus("Filter changes apply immediately.");
        }, function (m) {
            setPanelError("vi-list-body", m);
            setFooterStatus("List failed to load.");
        });
    }

    function refreshFacets() {
        runSearch("agents_list", QUERIES.agents_list, 500, state.earliest, state.latest, renderAgentsList, function () {});
        runSearch("rules_list", QUERIES.rules_list, 200, state.earliest, state.latest, renderRulesList, function () {});
    }

    function wireControls() {
        var t = document.getElementById("vi-time");
        if (t) {
            t.addEventListener("change", function (e) {
                state.earliest = e.target.value;
                cancelAll();
                refreshFacets();
                refreshList();
            });
        }
        var a = document.getElementById("vi-agent");
        if (a) { a.addEventListener("change", function (e) { state.agent = e.target.value; refreshList(); }); }
        var r = document.getElementById("vi-rule");
        if (r) { r.addEventListener("change", function (e) { state.rule = e.target.value; refreshList(); }); }
        var s = document.getElementById("vi-severity");
        if (s) { s.addEventListener("change", function (e) { state.severity = e.target.value; refreshList(); }); }
        var v = document.getElementById("vi-verdict");
        if (v) { v.addEventListener("change", function (e) { state.verdictLabel = e.target.value; refreshList(); }); }
        var c = document.getElementById("vi-clear");
        if (c) {
            c.addEventListener("click", function () {
                state.agent = "*"; state.rule = "*"; state.severity = "*"; state.verdictLabel = "*";
                fillDropdown("vi-agent", state.agentsOptions, "*");
                fillDropdown("vi-rule", state.rulesOptions, "*");
                document.getElementById("vi-severity").value = "*";
                document.getElementById("vi-verdict").value = "*";
                refreshList();
            });
        }
    }

    function mount() {
        var root = document.getElementById(MOUNT_ID);
        if (!root) {
            if (typeof console !== "undefined" && console.warn) {
                console.warn("[splunkgate-verdict-inspector] mount node #" + MOUNT_ID + " not found");
            }
            return;
        }
        renderShell(root);
        wireControls();
        refreshFacets();
        refreshList();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", mount);
    } else {
        mount();
    }
}());
