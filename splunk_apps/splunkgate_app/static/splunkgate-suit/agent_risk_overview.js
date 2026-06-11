/* SplunkGate — Agent Risk Overview (SUIT bundle).
 *
 * D2 "cockpit": 5 KPI tiles + verdicts-by-label area chart + rules-by-hour
 * heatmap + top-agents-by-BLOCK table + MSJ scaling line. Drill-down to
 * verdict_inspector on chart/heatmap/row click (gated on the
 * VERDICT_INSPECTOR_AVAILABLE flag — flipped when PR #18 ships).
 *
 * Search-lifecycle contract mirrors evidence_pack.js: errback-wired
 * require(), try/catch around new SearchManager(), 30s timeout, per-call
 * cancelled-flag closure, cancelAll() before refresh waves on window
 * change.
 *
 * Live-tick: when the BLOCKED KPI value increases between two SUCCESSFUL
 * consecutive refreshes (the first refresh post-mount is the baseline,
 * never a tick), the tile gets a 220ms pulse — the ONLY motion in the
 * product. Respects prefers-reduced-motion. The tick timer is tracked
 * per-tile so burst refreshes don't truncate one another.
 *
 * SPL queries lifted verbatim from
 * docs/archive/dashboard-studio-v2/agent_risk_overview.xml.
 */
(function () {
    "use strict";

    var MOUNT_ID = "splunkgate-agent-risk";
    var SEARCH_TIMEOUT_MS = 30000;
    var SEARCH_ID_SEQ = 0;
    // Flip to true the moment PR #18 (verdict_inspector SUIT rebuild) lands.
    // Until then, the drill-down would 404 — render as <span>, not <a>.
    var VERDICT_INSPECTOR_AVAILABLE = true;
    // Heatmap intensity bucketing — absolute floor for bucket-5 so a single
    // hit on a sparse window doesn't paint vermillion-deep. Severity scores
    // are 1 (LOW) / 2 (MEDIUM) / 4 (HIGH) per the canonical map, so 6+
    // per-cell means at least two-HIGH or three-MED hits in the hour.
    var HEATMAP_BUCKET_5_FLOOR = 6.0;

    /* 11 Cisco AI Defense rule names — VERBATIM. Heatmap Y-axis order is
     * load-bearing for examiner artifacts; do not re-sort. */
    var CISCO_AI_DEFENSE_RULES = [
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
        "Violence & Public Safety Threats"
    ];

    var QUERIES = {
        total: '`splunkgate_data` | stats count',
        block: '`splunkgate_data` verdict_label=block | stats count',
        high: '`splunkgate_data` severity=HIGH | stats count',
        agents: '`splunkgate_data` | stats dc(agent_id) as agents',
        tokens_saved: '`splunkgate_data` verdict_label=block | stats sum(tokens_used) as tokens_saved',
        ts: '`splunkgate_data` | timechart span=1h count by verdict_label',
        heatmap: '`splunkgate_data` | mvexpand rule | bin _time span=1h | stats sum(severity_score) as score by _time, rule',
        top_agents: '`splunkgate_data` verdict_label=block | stats count by agent_id | sort -count | head 10',
        msj: '`splunkgate_data` | stats count(eval(severity!="NONE_SEVERITY")) as detections count as total_msgs by agent_id | eval detection_rate=round(detections/total_msgs,4) | sort -total_msgs'
    };

    var SEARCH_KEYS = ["total", "block", "high", "agents", "tokens", "ts", "heatmap", "top_agents", "msj"];

    var TIME_PRESETS = [
        { value: "-1h@h", label: "Last 1 hour" },
        { value: "-24h@h", label: "Last 24 hours" },
        { value: "-7d@d", label: "Last 7 days" },
        { value: "-30d@d", label: "Last 30 days" }
    ];

    var REFRESH_PRESETS = [
        { value: 0, label: "Off" },
        { value: 30000, label: "Every 30s" },
        { value: 60000, label: "Every 60s" },
        { value: 300000, label: "Every 5m" }
    ];

    var state = {
        earliest: "-24h@h",
        latest: "now",
        refreshIntervalMs: 30000,
        refreshTimer: null,
        searches: {},
        kpiStatus: {},                    // id -> "loading"|"ok"|"error"|"idle"
        kpiTickTimers: {},                // id -> setTimeout handle for the pulse
        lastBlockValue: null,             // null on first cold load / post-window-change / post-error
        lastBlockSeenSuccessful: false,   // first SUCCESSFUL block refresh sets this; no tick before then
        lastSuccessAt: null,              // Date of the most recent fully-ok refresh wave
        searchOutcome: {}                 // id -> "ok"|"error" for the latest completed call
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

    function formatTime(earliest) {
        var p = TIME_PRESETS.filter(function (x) { return x.value === earliest; })[0];
        return p ? p.label : earliest + " → now";
    }

    function formatNumber(n) {
        var num = parseInt(n, 10);
        if (isNaN(num)) { return String(n || "0"); }
        if (num >= 1000000) { return (num / 1000000).toFixed(1) + "M"; }
        if (num >= 1000) { return (num / 1000).toFixed(1) + "k"; }
        return String(num);
    }

    function renderShell(root) {
        var optsTime = TIME_PRESETS.map(function (p) {
            var sel = p.value === state.earliest ? " selected" : "";
            return '<option value="' + escapeHtml(p.value) + '"' + sel + ">" + escapeHtml(p.label) + "</option>";
        }).join("");
        var optsRefresh = REFRESH_PRESETS.map(function (p) {
            var sel = p.value === state.refreshIntervalMs ? " selected" : "";
            return '<option value="' + p.value + '"' + sel + ">" + escapeHtml(p.label) + "</option>";
        }).join("");

        root.innerHTML = [
            '<div class="splunkgate-suit">',
            '<div class="ar-page">',
            '<header class="ar-header">',
            '<div>',
            '<h1 class="ar-header-title">SplunkGate — Agent Risk Overview</h1>',
            '<div class="ar-header-subtitle">Real-time CISO/SOC view of AI agent safety verdicts across the estate.</div>',
            '</div>',
            '<div class="ar-controls">',
            '<div class="ar-control"><label for="ar-time">Time range</label>',
            '<select id="ar-time">' + optsTime + '</select></div>',
            '<div class="ar-control"><label for="ar-refresh">Auto-refresh</label>',
            '<select id="ar-refresh">' + optsRefresh + '</select></div>',
            '<div class="ar-refresh" id="ar-refresh-indicator">idle</div>',
            '</div>',
            '</header>',
            '<section class="ar-kpis">',
            kpi("kpi-total", "Total verdicts", "verdicts in window", ""),
            kpi("kpi-block", "BLOCKED actions", "intercepted before LLM/tool", "ar-kpi-block"),
            kpi("kpi-high", "HIGH severity", "rule hits", "ar-kpi-high"),
            kpi("kpi-agents", "Distinct agents", "active in window", ""),
            kpi("kpi-tokens", "Tokens saved", "BLOCK × tokens_used", ""),
            '</section>',
            '<div class="ar-panel">',
            '<h2>Verdicts by label, per hour</h2>',
            '<p class="ar-panel-desc">Stacked verdict counts per hour over the selected window. ALLOW (paper green) sits at the base; MODIFY (amber) and REVIEW (blue) ride above; BLOCK (vermillion) is painted as a discrete overlay so the brand moment is never muddied by composition with the stack.</p>',
            '<div id="ar-area-body"></div>',
            '<div class="ar-legend" id="ar-area-legend"></div>',
            '</div>',
            '<section class="ar-grid">',
            '<div class="ar-panel">',
            '<h2>Rules-by-hour heatmap</h2>',
            '<p class="ar-panel-desc">Per-hour severity-weighted score for each of the 11 Cisco AI Defense rule names. Row order verbatim from the Cisco Offer Description. Unmapped rules (taxonomy drift) appear in an "Other" row at the bottom.</p>',
            '<div class="ar-heatmap" id="ar-heatmap-body"></div>',
            '</div>',
            '<div class="ar-panel">',
            '<h2>Top agents by BLOCKED count</h2>',
            '<p class="ar-panel-desc">' +
                (VERDICT_INSPECTOR_AVAILABLE
                    ? "Click a row to drill into the Verdict Inspector for that agent."
                    : "Drill-down to Verdict Inspector lands in v1.1; rows shown as monospace identifiers for now.") +
                '</p>',
            '<div id="ar-top-agents-body"></div>',
            '</div>',
            '</section>',
            '<div class="ar-panel">',
            '<h2>MSJ scaling indicator (last 7 days)</h2>',
            '<p class="ar-panel-desc">Detection rate vs. in-context message count per agent — Many-Shot Jailbreaking probabilistic floor (Anthropic 2024). Window is hard-pinned to -7d regardless of the cockpit time range above (long-horizon research signal, not a tactical-window metric).</p>',
            '<div id="ar-msj-body"></div>',
            '</div>',
            '<footer class="ar-footer" id="ar-footer">',
            '<span>SplunkGate v1.0.0</span>',
            '<span id="ar-footer-coverage">' + escapeHtml(formatTime(state.earliest)) + '</span>',
            '<span id="ar-footer-status">Loading…</span>',
            '<span id="ar-footer-generated">—</span>',
            '</footer>',
            '</div>',
            '</div>'
        ].join("");
    }

    function kpi(id, label, suffix, extraClass) {
        return [
            '<div class="ar-kpi ' + escapeHtml(extraClass || "") + '" id="ar-' + id + '">',
            '<div class="ar-kpi-label">' + escapeHtml(label) + '</div>',
            '<div class="ar-kpi-value" id="ar-' + id + '-value">—</div>',
            '<div class="ar-kpi-suffix" id="ar-' + id + '-suffix">' + escapeHtml(suffix) + '</div>',
            '</div>'
        ].join("");
    }

    function setKpiLoading(id) {
        state.kpiStatus[id] = "loading";
        var tile = document.getElementById("ar-" + id);
        if (tile) {
            tile.classList.remove("ar-kpi-failed");
            tile.classList.add("ar-kpi-loading");
        }
    }

    function setKpiOk(id, value, suffixOverride) {
        state.kpiStatus[id] = "ok";
        var tile = document.getElementById("ar-" + id);
        if (tile) {
            tile.classList.remove("ar-kpi-loading");
            tile.classList.remove("ar-kpi-failed");
        }
        var valEl = document.getElementById("ar-" + id + "-value");
        if (valEl) { valEl.textContent = value; }
        if (suffixOverride !== undefined) {
            var sufEl = document.getElementById("ar-" + id + "-suffix");
            if (sufEl) { sufEl.textContent = suffixOverride; }
        }
    }

    function setKpiError(id, errMsg) {
        state.kpiStatus[id] = "error";
        var tile = document.getElementById("ar-" + id);
        if (tile) {
            tile.classList.remove("ar-kpi-loading");
            tile.classList.add("ar-kpi-failed");
        }
        var valEl = document.getElementById("ar-" + id + "-value");
        if (valEl) { valEl.textContent = "!"; }
        var sufEl = document.getElementById("ar-" + id + "-suffix");
        if (sufEl) { sufEl.textContent = "load failed — see DevTools"; }
        if (id === "kpi-block") {
            // A failed BLOCK refresh must not become a tick baseline.
            state.lastBlockValue = null;
            state.lastBlockSeenSuccessful = false;
        }
        if (typeof console !== "undefined" && console.warn) {
            console.warn("[splunkgate-agent-risk] " + id + " load failed: " + errMsg);
        }
    }

    function tickKpi(id) {
        var el = document.getElementById("ar-" + id);
        if (!el) { return; }
        // Clear any in-flight tick timer so burst refreshes don't truncate
        // one another mid-pulse.
        if (state.kpiTickTimers[id]) {
            clearTimeout(state.kpiTickTimers[id]);
            state.kpiTickTimers[id] = null;
        }
        el.classList.remove("ar-tick");
        // Force a reflow so the next class re-add re-triggers the keyframe.
        void el.offsetWidth;
        el.classList.add("ar-tick");
        state.kpiTickTimers[id] = setTimeout(function () {
            el.classList.remove("ar-tick");
            state.kpiTickTimers[id] = null;
        }, 240);
    }

    function setPanelError(bodyId, errMsg) {
        var el = document.getElementById(bodyId);
        if (!el) { return; }
        el.innerHTML = (
            '<div class="ar-state-error-wrap">' +
            '<div class="ar-state-error-head">PANEL FAILED TO LOAD</div>' +
            '<div class="ar-state-error-msg">' + escapeHtml(errMsg) + '</div>' +
            '</div>'
        );
    }

    function setPanelEmpty(bodyId, msg) {
        var el = document.getElementById(bodyId);
        if (el) { el.innerHTML = '<div class="ar-state">' + escapeHtml(msg) + '</div>'; }
    }

    function renderKpiTotal(rows) {
        var v = (rows && rows[0] && rows[0].count) || "0";
        setKpiOk("kpi-total", formatNumber(v));
    }
    function renderKpiBlock(rows) {
        var v = (rows && rows[0] && rows[0].count) || "0";
        var num = parseInt(v, 10);
        if (isNaN(num)) { num = 0; }
        // Live-tick fires only when (a) we've already seen a SUCCESSFUL prior
        // BLOCK refresh AND (b) the new value strictly exceeds it. The first
        // successful refresh post-mount establishes the baseline silently.
        if (state.lastBlockSeenSuccessful && state.lastBlockValue !== null && num > state.lastBlockValue) {
            tickKpi("kpi-block");
        }
        state.lastBlockValue = num;
        state.lastBlockSeenSuccessful = true;
        setKpiOk("kpi-block", formatNumber(v));
    }
    function renderKpiHigh(rows) {
        var v = (rows && rows[0] && rows[0].count) || "0";
        setKpiOk("kpi-high", formatNumber(v));
    }
    function renderKpiAgents(rows) {
        var v = (rows && rows[0] && rows[0].agents) || "0";
        setKpiOk("kpi-agents", formatNumber(v));
    }
    function renderKpiTokens(rows) {
        var v = (rows && rows[0] && rows[0].tokens_saved) || "0";
        setKpiOk("kpi-tokens", formatNumber(v));
    }

    /* Area chart — ALLOW + MODIFY + REVIEW painted as a stack; BLOCK painted
     * as a discrete overlay (line + dots) on top of the stack so the brand
     * moment is never muddied by series composition. Guards single-bucket
     * and corrupted-value cases. */
    function renderArea(rows) {
        var body = document.getElementById("ar-area-body");
        if (!body) { return; }
        if (!rows || rows.length === 0) {
            setPanelEmpty("ar-area-body", "No verdicts in the selected time range.");
            renderAreaLegend([]);
            return;
        }
        var n = rows.length;
        if (n < 2) {
            // Degenerate: a 1-point polygon renders nothing. Surface explicitly.
            setPanelEmpty("ar-area-body", "Single-bucket window — increase time range to render a trend.");
            renderAreaLegend([]);
            return;
        }
        var width = body.clientWidth || 1200;
        var height = 220;
        var pad = { top: 8, right: 12, bottom: 24, left: 36 };

        // Stack series (NOT BLOCK — BLOCK is a discrete overlay).
        var stackOrder = ["ALLOW", "MODIFY", "REVIEW"];
        var present = {};
        rows.forEach(function (r) {
            Object.keys(r).forEach(function (k) {
                if (k === "_time" || k === "_span") { return; }
                present[k] = true;
            });
        });
        var stackSeries = stackOrder.filter(function (s) { return present[s]; });
        Object.keys(present).forEach(function (k) {
            if (k !== "BLOCK" && stackSeries.indexOf(k) === -1) { stackSeries.push(k); }
        });

        var xStep = (width - pad.left - pad.right) / (n - 1);
        var safe = function (v) {
            var f = parseFloat(v);
            return isFinite(f) ? f : 0;
        };

        // Stacked totals.
        var stacks = rows.map(function (r) {
            var acc = 0;
            var layers = {};
            stackSeries.forEach(function (s) {
                var val = safe(r[s]);
                layers[s + "_bot"] = acc;
                acc += val;
                layers[s + "_top"] = acc;
            });
            layers._stackTotal = acc;
            layers._blockTotal = safe(r.BLOCK);
            return layers;
        });
        var yMax = Math.max(1, stacks.reduce(function (m, s) {
            return Math.max(m, s._stackTotal, s._blockTotal);
        }, 0));
        var yScale = function (v) { return (height - pad.bottom) - ((v / yMax) * (height - pad.top - pad.bottom)); };
        var xScale = function (i) { return pad.left + (i * xStep); };

        var seriesClass = {
            ALLOW: "ar-area-allow",
            MODIFY: "ar-area-modify",
            REVIEW: "ar-area-review"
        };
        var polygons = stackSeries.map(function (s) {
            var top = stacks.map(function (st, i) { return xScale(i) + "," + yScale(st[s + "_top"]); });
            var bot = stacks.map(function (st, i) { return xScale(i) + "," + yScale(st[s + "_bot"]); }).reverse();
            var pts = top.concat(bot).join(" ");
            var cls = seriesClass[s] || "ar-area-review";
            return '<polygon class="' + cls + '" points="' + pts + '" />';
        }).join("");

        // BLOCK overlay: stroked line + filled dots, painted ABOVE the stack.
        var blockHasData = stacks.some(function (s) { return s._blockTotal > 0; });
        var blockSvg = "";
        if (blockHasData) {
            var path = "M " + stacks.map(function (st, i) { return xScale(i) + "," + yScale(st._blockTotal); }).join(" L ");
            var dots = stacks.map(function (st, i) {
                if (st._blockTotal <= 0) { return ""; }
                return '<circle class="ar-area-block-dot" cx="' + xScale(i) + '" cy="' + yScale(st._blockTotal) + '" r="3" />';
            }).join("");
            blockSvg = '<path class="ar-area-block-line" d="' + path + '" />' + dots;
        }

        var xTicks = "";
        var tickEvery = Math.max(1, Math.floor(n / 6));
        for (var i = 0; i < n; i += tickEvery) {
            var t = rows[i]._time || "";
            var hh = t.length >= 13 ? t.substring(11, 13) + ":00" : String(i);
            xTicks += '<text x="' + xScale(i) + '" y="' + (height - 6) + '" text-anchor="middle">' + escapeHtml(hh) + "</text>";
        }
        var yTicks = "";
        for (var yi = 0; yi <= 4; yi += 1) {
            var v = Math.round((yMax * yi) / 4);
            yTicks += '<text x="' + (pad.left - 6) + '" y="' + (yScale(v) + 3) + '" text-anchor="end">' + escapeHtml(formatNumber(v)) + "</text>";
        }

        body.innerHTML = (
            '<svg class="ar-area-svg" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none">' +
            '<g>' + polygons + '</g>' +
            '<g>' + blockSvg + '</g>' +
            '<g class="ar-area-axis">' + xTicks + yTicks + "</g>" +
            "</svg>"
        );
        var legendSeries = stackSeries.filter(function (s) {
            return stacks.some(function (st) { return safe(rows[stacks.indexOf(st)][s]) > 0; });
        });
        if (blockHasData) { legendSeries.push("BLOCK"); }
        renderAreaLegend(legendSeries);
    }

    function renderAreaLegend(series) {
        var leg = document.getElementById("ar-area-legend");
        if (!leg) { return; }
        if (!series || series.length === 0) { leg.innerHTML = ""; return; }
        var swClass = {
            ALLOW: "background: var(--allow);",
            BLOCK: "background: var(--block);",
            MODIFY: "background: var(--med);",
            REVIEW: "background: var(--blue);"
        };
        leg.innerHTML = series.map(function (s) {
            var style = swClass[s] || "background: var(--ink-3);";
            return '<span><span class="ar-legend-sw" style="' + style + '"></span>' + escapeHtml(s) + "</span>";
        }).join("");
    }

    /* Heatmap — 11 fixed rule rows × hour buckets, plus an "Other" row if
     * any rule outside the canonical list appears in the result. Intensity
     * buckets use an absolute floor for bucket 5 so 1 hit on sparse data
     * doesn't paint vermillion-deep. */
    function renderHeatmap(rows) {
        var body = document.getElementById("ar-heatmap-body");
        if (!body) { return; }
        if (!rows || rows.length === 0) {
            setPanelEmpty("ar-heatmap-body", "No rule hits in the selected time range.");
            return;
        }
        var hourSet = {};
        rows.forEach(function (r) {
            var t = r._time || "";
            var hh = t.length >= 13 ? t.substring(0, 13) + ":00" : t || "—";
            hourSet[hh] = true;
        });
        var hours = Object.keys(hourSet).sort();
        if (hours.length === 0) { hours = ["—"]; }

        var map = {};
        var unmappedHits = {};   // ruleName -> total score (for the "Other" row)
        rows.forEach(function (r) {
            var t = r._time || "";
            var hh = t.length >= 13 ? t.substring(0, 13) + ":00" : t || "—";
            var rule = r.rule != null ? String(r.rule).trim() : "";
            if (rule === "") { return; }   // skip blank
            var score = parseFloat(r.score);
            if (!isFinite(score)) { score = 0; }
            var key = rule + "||" + hh;
            map[key] = (map[key] || 0) + score;
            if (CISCO_AI_DEFENSE_RULES.indexOf(rule) === -1) {
                unmappedHits[rule] = (unmappedHits[rule] || 0) + score;
                var otherKey = "__OTHER__||" + hh;
                map[otherKey] = (map[otherKey] || 0) + score;
            }
        });

        var unmappedNames = Object.keys(unmappedHits);
        if (unmappedNames.length > 0 && typeof console !== "undefined" && console.warn) {
            console.warn("[splunkgate-agent-risk] heatmap: unmapped rule names (rolled into Other): " + unmappedNames.join(", "));
        }

        var allScores = Object.keys(map).map(function (k) { return map[k]; });
        var maxScore = Math.max(HEATMAP_BUCKET_5_FLOOR, allScores.reduce(function (m, v) { return Math.max(m, v); }, 0));
        function bucket(score) {
            if (score <= 0) { return 0; }
            var pct = score / maxScore;
            if (pct < 0.2) { return 1; }
            if (pct < 0.4) { return 2; }
            if (pct < 0.6) { return 3; }
            if (pct < 0.8) { return 4; }
            return 5;
        }

        var headerCells = '<th class="ar-rule-label">Cisco AI Defense rule</th>';
        hours.forEach(function (hh) {
            var hourPart = hh.length >= 13 ? hh.substring(11, 13) : hh;
            headerCells += '<th class="ar-hour-label">' + escapeHtml(hourPart) + "</th>";
        });

        var rowsToRender = CISCO_AI_DEFENSE_RULES.slice();
        if (unmappedNames.length > 0) { rowsToRender.push("__OTHER__"); }

        var bodyRows = rowsToRender.map(function (rule) {
            var rowLabel = rule === "__OTHER__"
                ? "Other (unmapped: " + unmappedNames.length + ")"
                : rule;
            var cells = '<th class="ar-rule-label">' + escapeHtml(rowLabel) + "</th>";
            hours.forEach(function (hh) {
                var key = rule + "||" + hh;
                var score = map[key] || 0;
                cells += '<td class="ar-heatmap-cell" data-intensity="' + bucket(score) + '" title="' + escapeHtml(rowLabel + " @ " + hh + " — score=" + score.toFixed(1)) + '"></td>';
            });
            return "<tr>" + cells + "</tr>";
        }).join("");

        body.innerHTML = (
            '<table class="ar-heatmap-table">' +
            "<thead><tr>" + headerCells + "</tr></thead>" +
            "<tbody>" + bodyRows + "</tbody>" +
            "</table>"
        );
    }

    function renderTopAgents(rows) {
        var body = document.getElementById("ar-top-agents-body");
        if (!body) { return; }
        if (!rows || rows.length === 0) {
            setPanelEmpty("ar-top-agents-body", "No BLOCKED verdicts in the selected window.");
            return;
        }
        var trs = rows.map(function (r) {
            var aid = r.agent_id || "";
            var c = r.count || "0";
            var aidCell;
            if (VERDICT_INSPECTOR_AVAILABLE) {
                var url = "/app/splunkgate_app/verdict_inspector?form.input_agent_id=" + encodeURIComponent(aid);
                aidCell = '<a href="' + escapeHtml(url) + '">' + escapeHtml(aid) + "</a>";
            } else {
                aidCell = '<span title="Verdict Inspector lands in v1.1">' + escapeHtml(aid) + "</span>";
            }
            return (
                "<tr>" +
                '<td class="ar-mono">' + aidCell + "</td>" +
                '<td class="ar-count">' + escapeHtml(c) + "</td>" +
                "</tr>"
            );
        }).join("");
        body.innerHTML = (
            '<table class="ar-table">' +
            "<thead><tr><th>Agent ID</th><th>BLOCKs</th></tr></thead>" +
            "<tbody>" + trs + "</tbody>" +
            "</table>"
        );
    }

    function renderMsj(rows) {
        var body = document.getElementById("ar-msj-body");
        if (!body) { return; }
        if (!rows || rows.length === 0) {
            setPanelEmpty("ar-msj-body", "Not enough multi-message agents to render the scaling indicator.");
            return;
        }
        var width = body.clientWidth || 1200;
        var height = 110;
        var pad = { top: 8, right: 16, bottom: 22, left: 36 };

        var points = rows.map(function (r) {
            return {
                x: parseFloat(r.total_msgs) || 0,
                y: parseFloat(r.detection_rate) || 0
            };
        }).filter(function (p) { return p.x > 0 && isFinite(p.x) && isFinite(p.y); });

        if (points.length === 0) {
            setPanelEmpty("ar-msj-body", "No agent has positive total_msgs in the last 7 days.");
            return;
        }
        points.sort(function (a, b) { return a.x - b.x; });

        var xMax = Math.max(1, points[points.length - 1].x);
        var xScale = function (v) { return pad.left + (v / xMax) * (width - pad.left - pad.right); };
        var yScale = function (v) { return (height - pad.bottom) - (v * (height - pad.top - pad.bottom)); };

        var line = points.length > 1
            ? "M " + points.map(function (p) { return xScale(p.x) + "," + yScale(p.y); }).join(" L ")
            : "";
        var dots = points.map(function (p) {
            return '<circle class="ar-msj-dot" cx="' + xScale(p.x) + '" cy="' + yScale(p.y) + '" />';
        }).join("");
        var yTicks = (
            '<text x="' + (pad.left - 6) + '" y="' + (yScale(0) + 3) + '" text-anchor="end">0</text>' +
            '<text x="' + (pad.left - 6) + '" y="' + (yScale(0.5) + 3) + '" text-anchor="end">0.5</text>' +
            '<text x="' + (pad.left - 6) + '" y="' + (yScale(1) + 3) + '" text-anchor="end">1.0</text>'
        );
        var xTicks = (
            '<text x="' + xScale(0) + '" y="' + (height - 6) + '" text-anchor="middle">0</text>' +
            '<text x="' + xScale(xMax) + '" y="' + (height - 6) + '" text-anchor="end">' + escapeHtml(formatNumber(xMax)) + "</text>"
        );

        body.innerHTML = (
            '<svg class="ar-msj-svg" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none">' +
            (line ? '<path class="ar-msj-line" d="' + line + '" />' : "") +
            dots +
            '<g class="ar-area-axis">' + xTicks + yTicks + "</g>" +
            "</svg>"
        );
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
            state.searchOutcome[id] = "error";
            onError("Splunk runtime not detected (require is undefined)");
            return;
        }

        ctx.timer = setTimeout(function () {
            if (ctx.cancelled) { return; }
            ctx.cancelled = true;
            if (ctx.mgr && typeof ctx.mgr.cancel === "function") { ctx.mgr.cancel(); }
            state.searchOutcome[id] = "error";
            onError("Search timed out after " + (SEARCH_TIMEOUT_MS / 1000) + "s — no response from Splunk Search SDK");
        }, SEARCH_TIMEOUT_MS);

        require(
            ["splunkjs/mvc/searchmanager"],
            function (SearchManager) {
                if (ctx.cancelled) { return; }
                try {
                    SEARCH_ID_SEQ += 1;
                    ctx.mgr = new SearchManager({
                        id: "splunkgate-ar-" + id + "-" + SEARCH_ID_SEQ,
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
                    state.searchOutcome[id] = "error";
                    onError("SearchManager construction failed: " + (e && e.message ? e.message : "unknown error"));
                    return;
                }
                ctx.mgr.on("search:error", function (props) {
                    if (ctx.cancelled) { return; }
                    ctx.cancelled = true;
                    if (ctx.timer) { clearTimeout(ctx.timer); }
                    state.searchOutcome[id] = "error";
                    onError(props && props.message ? props.message : "Splunk search returned an error (no message)");
                });
                ctx.mgr.data("results", { count: resultsCount, offset: 0 }).on("data", function (_unused, data) {
                    if (ctx.cancelled) { return; }
                    ctx.cancelled = true;
                    if (ctx.timer) { clearTimeout(ctx.timer); }
                    state.searchOutcome[id] = "ok";
                    onResults(data && data.results ? data.results : []);
                    updateFooterStatus();
                });
            },
            function (err) {
                if (ctx.cancelled) { return; }
                ctx.cancelled = true;
                if (ctx.timer) { clearTimeout(ctx.timer); }
                state.searchOutcome[id] = "error";
                onError(
                    "Splunk Search SDK failed to load: " +
                    (err && err.message ? err.message : (err && err.requireType ? err.requireType : "unknown require error"))
                );
                updateFooterStatus();
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

    function updateFooterStatus() {
        var st = document.getElementById("ar-footer-status");
        var ind = document.getElementById("ar-refresh-indicator");
        if (!st) { return; }
        var ok = 0;
        var errored = 0;
        var pending = 0;
        SEARCH_KEYS.forEach(function (id) {
            var o = state.searchOutcome[id];
            if (o === "ok") { ok += 1; }
            else if (o === "error") { errored += 1; }
            else { pending += 1; }
        });
        var line = "Refresh: " + ok + "/" + SEARCH_KEYS.length + " OK";
        if (errored > 0) { line += ", " + errored + " errored"; }
        if (pending > 0) { line += ", " + pending + " in flight"; }
        st.textContent = line;

        if (ind) {
            if (errored > 0 && pending === 0) {
                ind.textContent = "stale";
                ind.className = "ar-refresh ar-refresh-stale";
            } else if (state.refreshIntervalMs > 0) {
                ind.textContent = "live";
                ind.className = "ar-refresh";
            } else {
                ind.textContent = "manual";
                ind.className = "ar-refresh";
            }
        }
        // "Last refresh" updates only when the wave is fully complete AND ok.
        if (pending === 0) {
            var gen = document.getElementById("ar-footer-generated");
            if (errored === 0) {
                state.lastSuccessAt = new Date();
                if (gen) { gen.textContent = "Last refresh: " + state.lastSuccessAt.toLocaleTimeString(); }
            } else if (gen && state.lastSuccessAt) {
                gen.textContent = "Last success: " + state.lastSuccessAt.toLocaleTimeString() + " (stale)";
            }
        }
    }

    function refreshAll() {
        // Mark every search as pending so the footer status reads honestly
        // during the in-flight period.
        SEARCH_KEYS.forEach(function (id) { state.searchOutcome[id] = "pending"; });
        updateFooterStatus();

        ["kpi-total", "kpi-block", "kpi-high", "kpi-agents", "kpi-tokens"].forEach(setKpiLoading);

        var e = state.earliest;
        var l = state.latest;
        runSearch("total", QUERIES.total, 1, e, l, renderKpiTotal, function (m) { setKpiError("kpi-total", m); });
        runSearch("block", QUERIES.block, 1, e, l, renderKpiBlock, function (m) { setKpiError("kpi-block", m); });
        runSearch("high", QUERIES.high, 1, e, l, renderKpiHigh, function (m) { setKpiError("kpi-high", m); });
        runSearch("agents", QUERIES.agents, 1, e, l, renderKpiAgents, function (m) { setKpiError("kpi-agents", m); });
        runSearch("tokens", QUERIES.tokens_saved, 1, e, l, renderKpiTokens, function (m) { setKpiError("kpi-tokens", m); });
        runSearch("ts", QUERIES.ts, 200, e, l, renderArea, function (m) { setPanelError("ar-area-body", m); });
        runSearch("heatmap", QUERIES.heatmap, 5000, e, l, renderHeatmap, function (m) { setPanelError("ar-heatmap-body", m); });
        runSearch("top_agents", QUERIES.top_agents, 10, e, l, renderTopAgents, function (m) { setPanelError("ar-top-agents-body", m); });
        runSearch("msj", QUERIES.msj, 500, "-7d", "now", renderMsj, function (m) { setPanelError("ar-msj-body", m); });
    }

    function scheduleAutoRefresh() {
        if (state.refreshTimer) {
            clearInterval(state.refreshTimer);
            state.refreshTimer = null;
        }
        if (state.refreshIntervalMs > 0) {
            state.refreshTimer = setInterval(refreshAll, state.refreshIntervalMs);
        }
    }

    function resetTickBaselines() {
        state.lastBlockValue = null;
        state.lastBlockSeenSuccessful = false;
    }

    function wireControls() {
        var t = document.getElementById("ar-time");
        if (t) {
            t.addEventListener("change", function (e) {
                state.earliest = e.target.value;
                var cov = document.getElementById("ar-footer-coverage");
                if (cov) { cov.textContent = formatTime(state.earliest); }
                // Cancel ALL in-flight searches before a fresh wave —
                // prevents orphan SearchManager piles + stale callbacks.
                cancelAll();
                resetTickBaselines();
                refreshAll();
                scheduleAutoRefresh();
            });
        }
        var r = document.getElementById("ar-refresh");
        if (r) {
            r.addEventListener("change", function (e) {
                state.refreshIntervalMs = parseInt(e.target.value, 10) || 0;
                // Auto-refresh cadence change ALSO resets the live-tick
                // baseline. Otherwise switching Off → 30s would pulse for a
                // delta accumulated while polling was off.
                resetTickBaselines();
                scheduleAutoRefresh();
                updateFooterStatus();
            });
        }
    }

    function mount() {
        var root = document.getElementById(MOUNT_ID);
        if (!root) {
            if (typeof console !== "undefined" && console.warn) {
                console.warn("[splunkgate-agent-risk] mount node #" + MOUNT_ID + " not found");
            }
            return;
        }
        renderShell(root);
        wireControls();
        refreshAll();
        scheduleAutoRefresh();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", mount);
    } else {
        mount();
    }
}());
