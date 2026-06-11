/**
 * SplunkGate — Agent Risk Overview (SUIT view, story-suit-agent-risk-overview).
 *
 * TypeScript source-of-truth for the built bundle at
 * `static/splunkgate-suit/agent_risk_overview.js`.
 *
 * **DRIFT CONTRACT**: when you fix a bug in this file, you MUST fix the
 * same bug in `static/splunkgate-suit/agent_risk_overview.js`. The test
 * `test_ar_drift_invariants_match_between_js_and_tsx` enforces shared
 * invariants (Cisco AI Defense rule names, SPL queries, panel titles,
 * lifecycle markers, BLOCK overlay marker, heatmap-floor constant,
 * verdict-inspector-availability flag, search-key list).
 *
 * Both implementations render the same SVG: area chart with ALLOW/MODIFY/
 * REVIEW stacked + BLOCK painted as a discrete overlay, CSS-grid heatmap
 * with 11 Cisco rules + Other row for unmapped, MSJ scaling line.
 *
 * SPL data sources lift verbatim from
 * `docs/archive/dashboard-studio-v2/agent_risk_overview.xml`.
 */

import * as React from "react";
import { createRoot } from "react-dom/client";
import "../styles/tokens.css";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare const require: any;

const MOUNT_ID = "splunkgate-agent-risk";
const SEARCH_TIMEOUT_MS = 30000;
// Flip to true the moment PR #18 (verdict_inspector SUIT rebuild) lands.
const VERDICT_INSPECTOR_AVAILABLE = true;
// Heatmap intensity bucketing — absolute floor for bucket-5 so a single
// hit on a sparse window doesn't paint vermillion-deep.
const HEATMAP_BUCKET_5_FLOOR = 6.0;

/* 11 Cisco AI Defense rule names — VERBATIM. Heatmap Y-axis order is
 * load-bearing for examiner artifacts; do not re-sort. */
const CISCO_AI_DEFENSE_RULES = [
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
] as const;

const QUERIES = {
    total: "`splunkgate_data` | stats count",
    block: "`splunkgate_data` verdict_label=block | stats count",
    high: "`splunkgate_data` severity=HIGH | stats count",
    agents: "`splunkgate_data` | stats dc(agent_id) as agents",
    tokens_saved: "`splunkgate_data` verdict_label=block | stats sum(tokens_used) as tokens_saved",
    ts: "`splunkgate_data` | timechart span=1h count by verdict_label",
    heatmap: "`splunkgate_data` | mvexpand rule | bin _time span=1h | stats sum(severity_score) as score by _time, rule",
    top_agents: "`splunkgate_data` verdict_label=block | stats count by agent_id | sort -count | head 10",
    msj: '`splunkgate_data` | stats count(eval(severity!="NONE_SEVERITY")) as detections count as total_msgs by agent_id | eval detection_rate=round(detections/total_msgs,4) | sort -total_msgs',
} as const;

type SearchKey = keyof typeof QUERIES;
type Row = Record<string, string>;
type Status = "loading" | "ok" | "error" | "idle";

interface SearchState {
    status: Status;
    rows: Row[];
    error?: string;
}

interface SearchManagerInstance {
    cancel?: () => void;
    on: (event: string, cb: (props?: { message?: string }) => void) => void;
    data: (kind: string, params?: { count: number; offset: number }) => {
        on: (event: string, cb: (_unused: unknown, data: { results: Row[] }) => void) => void;
    };
}

const TIME_PRESETS = [
    { value: "-1h@h", label: "Last 1 hour" },
    { value: "-24h@h", label: "Last 24 hours" },
    { value: "-7d@d", label: "Last 7 days" },
    { value: "-30d@d", label: "Last 30 days" },
] as const;

const REFRESH_PRESETS = [
    { value: 0, label: "Off" },
    { value: 30000, label: "Every 30s" },
    { value: 60000, label: "Every 60s" },
    { value: 300000, label: "Every 5m" },
] as const;

function useSplunkSearch(
    key: SearchKey,
    query: string,
    earliest: string,
    latest: string,
    resultsCount: number,
    tick: number
): SearchState {
    const [s, setS] = React.useState<SearchState>({ status: "idle", rows: [] });

    React.useEffect(() => {
        setS({ status: "loading", rows: [] });
        let cancelled = false;
        let mgr: SearchManagerInstance | null = null;
        const timer = setTimeout(() => {
            if (cancelled) {
                return;
            }
            cancelled = true;
            mgr?.cancel?.();
            setS({
                status: "error",
                rows: [],
                error: `Search timed out after ${SEARCH_TIMEOUT_MS / 1000}s — no response from Splunk Search SDK`,
            });
        }, SEARCH_TIMEOUT_MS);

        if (typeof require !== "function") {
            clearTimeout(timer);
            setS({ status: "error", rows: [], error: "Splunk runtime not detected" });
            return;
        }
        require(
            ["splunkjs/mvc/searchmanager"],
            (SearchManager: new (cfg: object) => SearchManagerInstance) => {
                if (cancelled) {
                    return;
                }
                try {
                    mgr = new SearchManager({
                        id: `splunkgate-ar-${key}-${Date.now()}`,
                        preview: false,
                        cache: false,
                        search: query,
                        earliest_time: earliest,
                        latest_time: latest,
                    });
                } catch (e: unknown) {
                    if (cancelled) {
                        return;
                    }
                    cancelled = true;
                    clearTimeout(timer);
                    setS({
                        status: "error",
                        rows: [],
                        error: `SearchManager construction failed: ${(e as Error).message ?? "unknown error"}`,
                    });
                    return;
                }
                mgr.on("search:error", (props) => {
                    if (cancelled) {
                        return;
                    }
                    cancelled = true;
                    clearTimeout(timer);
                    setS({
                        status: "error",
                        rows: [],
                        error: props?.message ?? "Splunk search returned an error (no message)",
                    });
                });
                mgr.data("results", { count: resultsCount, offset: 0 }).on("data", (_unused, data) => {
                    if (cancelled) {
                        return;
                    }
                    cancelled = true;
                    clearTimeout(timer);
                    setS({ status: "ok", rows: data?.results ?? [] });
                });
            },
            (err: { message?: string; requireType?: string }) => {
                if (cancelled) {
                    return;
                }
                cancelled = true;
                clearTimeout(timer);
                setS({
                    status: "error",
                    rows: [],
                    error: `Splunk Search SDK failed to load: ${err?.message ?? err?.requireType ?? "unknown require error"}`,
                });
            }
        );
        return () => {
            cancelled = true;
            clearTimeout(timer);
            mgr?.cancel?.();
        };
    }, [key, query, earliest, latest, resultsCount, tick]);

    return s;
}

function safeNumber(s: string | undefined): number {
    if (s === undefined || s === null) {
        return 0;
    }
    const v = parseFloat(s);
    return isFinite(v) ? v : 0;
}

function formatNumber(s: string | undefined): string {
    const num = parseInt(s ?? "0", 10);
    if (isNaN(num)) {
        return "0";
    }
    if (num >= 1000000) {
        return `${(num / 1000000).toFixed(1)}M`;
    }
    if (num >= 1000) {
        return `${(num / 1000).toFixed(1)}k`;
    }
    return String(num);
}

interface KpiProps {
    id: string;
    label: string;
    suffix: string;
    state: SearchState;
    field: string;
    extraClass?: string;
    onValue?: (n: number) => void;
}

function Kpi({ id, label, suffix, state, field, extraClass, onValue }: KpiProps): React.ReactElement {
    const value = state.status === "ok" ? formatNumber(state.rows[0]?.[field]) : "—";
    let extraClassFinal = extraClass ?? "";
    let suffixText = suffix;
    let displayValue = value;
    if (state.status === "loading" || state.status === "idle") {
        extraClassFinal += " ar-kpi-loading";
        displayValue = "—";
    } else if (state.status === "error") {
        // Failed must not look live; .ar-kpi-failed CSS overrides the
        // BLOCKED brand accent.
        extraClassFinal += " ar-kpi-failed";
        displayValue = "!";
        suffixText = "load failed — see DevTools";
    }

    React.useEffect(() => {
        if (state.status === "ok" && onValue) {
            onValue(parseInt(state.rows[0]?.[field] ?? "0", 10) || 0);
        }
    }, [state, field, onValue]);

    return (
        <div className={`ar-kpi ${extraClassFinal}`} id={`ar-${id}`}>
            <div className="ar-kpi-label">{label}</div>
            <div className="ar-kpi-value">{displayValue}</div>
            <div className="ar-kpi-suffix">{suffixText}</div>
        </div>
    );
}

interface PanelStateProps {
    state: SearchState;
}

function PanelLoadingOrError({ state }: PanelStateProps): React.ReactElement | null {
    if (state.status === "loading" || state.status === "idle") {
        return <div className="ar-state">Loading…</div>;
    }
    if (state.status === "error") {
        return (
            <div className="ar-state-error-wrap">
                <div className="ar-state-error-head">PANEL FAILED TO LOAD</div>
                <div className="ar-state-error-msg">{state.error}</div>
            </div>
        );
    }
    return null;
}

interface AreaProps {
    rows: Row[];
}

interface AreaPanelProps {
    state: SearchState;
}

/* SVG area chart — ALLOW/MODIFY/REVIEW stacked, BLOCK painted as a
 * discrete overlay on top. Same visual contract as the JS bundle. */
function AreaChart({ rows }: AreaProps): React.ReactElement {
    const n = rows.length;
    if (n < 2) {
        return (
            <div className="ar-state">
                Single-bucket window — increase time range to render a trend.
            </div>
        );
    }
    const width = 1200;
    const height = 220;
    const pad = { top: 8, right: 12, bottom: 24, left: 36 };

    const stackOrder = ["ALLOW", "MODIFY", "REVIEW"];
    const presentKeys = new Set<string>();
    rows.forEach((r) =>
        Object.keys(r).forEach((k) => {
            if (k !== "_time" && k !== "_span") {
                presentKeys.add(k);
            }
        })
    );
    const stackSeries: string[] = [];
    stackOrder.forEach((s) => {
        if (presentKeys.has(s)) {
            stackSeries.push(s);
        }
    });
    presentKeys.forEach((k) => {
        if (k !== "BLOCK" && !stackSeries.includes(k)) {
            stackSeries.push(k);
        }
    });

    const xStep = (width - pad.left - pad.right) / (n - 1);
    const stacks = rows.map((r) => {
        let acc = 0;
        const layers: Record<string, number> = {};
        stackSeries.forEach((s) => {
            const val = safeNumber(r[s]);
            layers[`${s}_bot`] = acc;
            acc += val;
            layers[`${s}_top`] = acc;
        });
        layers._stackTotal = acc;
        layers._blockTotal = safeNumber(r.BLOCK);
        return layers;
    });
    const yMax = Math.max(
        1,
        stacks.reduce((m, s) => Math.max(m, s._stackTotal, s._blockTotal), 0)
    );
    const yScale = (v: number): number =>
        height - pad.bottom - (v / yMax) * (height - pad.top - pad.bottom);
    const xScale = (i: number): number => pad.left + i * xStep;

    const seriesClass: Record<string, string> = {
        ALLOW: "ar-area-allow",
        MODIFY: "ar-area-modify",
        REVIEW: "ar-area-review",
    };

    const blockHasData = stacks.some((s) => s._blockTotal > 0);
    const blockLine = blockHasData
        ? `M ${stacks.map((st, i) => `${xScale(i)},${yScale(st._blockTotal)}`).join(" L ")}`
        : "";

    const xTicks: React.ReactElement[] = [];
    const tickEvery = Math.max(1, Math.floor(n / 6));
    for (let i = 0; i < n; i += tickEvery) {
        const t = rows[i]._time ?? "";
        const hh = t.length >= 13 ? `${t.substring(11, 13)}:00` : String(i);
        xTicks.push(
            <text key={`x-${i}`} x={xScale(i)} y={height - 6} textAnchor="middle">
                {hh}
            </text>
        );
    }
    const yTicks: React.ReactElement[] = [];
    for (let yi = 0; yi <= 4; yi += 1) {
        const v = Math.round((yMax * yi) / 4);
        yTicks.push(
            <text key={`y-${yi}`} x={pad.left - 6} y={yScale(v) + 3} textAnchor="end">
                {formatNumber(String(v))}
            </text>
        );
    }

    return (
        <svg className="ar-area-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            <g>
                {stackSeries.map((s) => {
                    const top = stacks.map((st, i) => `${xScale(i)},${yScale(st[`${s}_top`])}`);
                    const bot = stacks
                        .map((st, i) => `${xScale(i)},${yScale(st[`${s}_bot`])}`)
                        .reverse();
                    return (
                        <polygon
                            key={s}
                            className={seriesClass[s] ?? "ar-area-review"}
                            points={top.concat(bot).join(" ")}
                        />
                    );
                })}
            </g>
            <g>
                {blockHasData && <path className="ar-area-block-line" d={blockLine} />}
                {blockHasData &&
                    stacks.map((st, i) =>
                        st._blockTotal > 0 ? (
                            <circle
                                key={`b-${i}`}
                                className="ar-area-block-dot"
                                cx={xScale(i)}
                                cy={yScale(st._blockTotal)}
                                r={3}
                            />
                        ) : null
                    )}
            </g>
            <g className="ar-area-axis">
                {xTicks}
                {yTicks}
            </g>
        </svg>
    );
}

function AreaPanel({ state }: AreaPanelProps): React.ReactElement {
    const wrap = <PanelLoadingOrError state={state} />;
    if (wrap) {
        return wrap;
    }
    if (state.rows.length === 0) {
        return <div className="ar-state">No verdicts in the selected time range.</div>;
    }
    return <AreaChart rows={state.rows} />;
}

function TopAgentsPanel({ state }: { state: SearchState }): React.ReactElement {
    const wrap = <PanelLoadingOrError state={state} />;
    if (wrap) {
        return wrap;
    }
    if (state.rows.length === 0) {
        return <div className="ar-state">No BLOCKED verdicts in the selected window.</div>;
    }
    return (
        <table className="ar-table">
            <thead>
                <tr>
                    <th>Agent ID</th>
                    <th>BLOCKs</th>
                </tr>
            </thead>
            <tbody>
                {state.rows.map((r, i) => {
                    const aid = r.agent_id ?? "";
                    const c = r.count ?? "0";
                    const aidCell = VERDICT_INSPECTOR_AVAILABLE ? (
                        <a
                            href={`/app/splunkgate_app/verdict_inspector?form.input_agent_id=${encodeURIComponent(aid)}`}
                        >
                            {aid}
                        </a>
                    ) : (
                        <span title="Verdict Inspector lands in v1.1">{aid}</span>
                    );
                    return (
                        <tr key={i}>
                            <td className="ar-mono">{aidCell}</td>
                            <td className="ar-count">{c}</td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}

function HeatmapPanel({ state }: { state: SearchState }): React.ReactElement {
    const wrap = <PanelLoadingOrError state={state} />;
    if (wrap) {
        return wrap;
    }
    if (state.rows.length === 0) {
        return <div className="ar-state">No rule hits in the selected time range.</div>;
    }
    const hourSet: Record<string, true> = {};
    state.rows.forEach((r) => {
        const t = r._time ?? "";
        const hh = t.length >= 13 ? `${t.substring(0, 13)}:00` : t || "—";
        hourSet[hh] = true;
    });
    const hours = Object.keys(hourSet).sort();
    const map: Record<string, number> = {};
    const unmapped: Record<string, number> = {};
    state.rows.forEach((r) => {
        const t = r._time ?? "";
        const hh = t.length >= 13 ? `${t.substring(0, 13)}:00` : t || "—";
        const rule = (r.rule ?? "").trim();
        if (!rule) {
            return;
        }
        const score = safeNumber(r.score);
        const key = `${rule}||${hh}`;
        map[key] = (map[key] ?? 0) + score;
        if (!CISCO_AI_DEFENSE_RULES.includes(rule as (typeof CISCO_AI_DEFENSE_RULES)[number])) {
            unmapped[rule] = (unmapped[rule] ?? 0) + score;
            const otherKey = `__OTHER__||${hh}`;
            map[otherKey] = (map[otherKey] ?? 0) + score;
        }
    });
    const unmappedNames = Object.keys(unmapped);
    if (unmappedNames.length > 0) {
        // eslint-disable-next-line no-console
        console.warn(
            `[splunkgate-agent-risk] heatmap: unmapped rule names (rolled into Other): ${unmappedNames.join(", ")}`
        );
    }
    const allScores = Object.values(map);
    const maxScore = Math.max(HEATMAP_BUCKET_5_FLOOR, ...allScores, 0);
    const bucket = (score: number): number => {
        if (score <= 0) {
            return 0;
        }
        const pct = score / maxScore;
        if (pct < 0.2) {
            return 1;
        }
        if (pct < 0.4) {
            return 2;
        }
        if (pct < 0.6) {
            return 3;
        }
        if (pct < 0.8) {
            return 4;
        }
        return 5;
    };

    const rowsToRender: string[] = [...CISCO_AI_DEFENSE_RULES];
    if (unmappedNames.length > 0) {
        rowsToRender.push("__OTHER__");
    }

    return (
        <div className="ar-heatmap">
            <table className="ar-heatmap-table">
                <thead>
                    <tr>
                        <th className="ar-rule-label">Cisco AI Defense rule</th>
                        {hours.map((hh) => (
                            <th key={hh} className="ar-hour-label">
                                {hh.length >= 13 ? hh.substring(11, 13) : hh}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rowsToRender.map((rule) => {
                        const rowLabel =
                            rule === "__OTHER__" ? `Other (unmapped: ${unmappedNames.length})` : rule;
                        return (
                            <tr key={rule}>
                                <th className="ar-rule-label">{rowLabel}</th>
                                {hours.map((hh) => {
                                    const score = map[`${rule}||${hh}`] ?? 0;
                                    return (
                                        <td
                                            key={hh}
                                            className="ar-heatmap-cell"
                                            data-intensity={bucket(score)}
                                            title={`${rowLabel} @ ${hh} — score=${score.toFixed(1)}`}
                                        />
                                    );
                                })}
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

function MsjPanel({ state }: { state: SearchState }): React.ReactElement {
    const wrap = <PanelLoadingOrError state={state} />;
    if (wrap) {
        return wrap;
    }
    if (state.rows.length === 0) {
        return (
            <div className="ar-state">
                Not enough multi-message agents to render the scaling indicator.
            </div>
        );
    }
    const width = 1200;
    const height = 110;
    const pad = { top: 8, right: 16, bottom: 22, left: 36 };

    const points = state.rows
        .map((r) => ({
            x: parseFloat(r.total_msgs ?? "0") || 0,
            y: parseFloat(r.detection_rate ?? "0") || 0,
        }))
        .filter((p) => p.x > 0 && isFinite(p.x) && isFinite(p.y))
        .sort((a, b) => a.x - b.x);

    if (points.length === 0) {
        return (
            <div className="ar-state">No agent has positive total_msgs in the last 7 days.</div>
        );
    }
    const xMax = Math.max(1, points[points.length - 1].x);
    const xScale = (v: number): number => pad.left + (v / xMax) * (width - pad.left - pad.right);
    const yScale = (v: number): number => height - pad.bottom - v * (height - pad.top - pad.bottom);
    const linePath =
        points.length > 1
            ? `M ${points.map((p) => `${xScale(p.x)},${yScale(p.y)}`).join(" L ")}`
            : "";
    return (
        <svg className="ar-msj-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            {linePath && <path className="ar-msj-line" d={linePath} />}
            {points.map((p, i) => (
                <circle
                    key={i}
                    className="ar-msj-dot"
                    cx={xScale(p.x)}
                    cy={yScale(p.y)}
                />
            ))}
            <g className="ar-area-axis">
                <text x={xScale(0)} y={height - 6} textAnchor="middle">
                    0
                </text>
                <text x={xScale(xMax)} y={height - 6} textAnchor="end">
                    {formatNumber(String(xMax))}
                </text>
                <text x={pad.left - 6} y={yScale(0) + 3} textAnchor="end">
                    0
                </text>
                <text x={pad.left - 6} y={yScale(0.5) + 3} textAnchor="end">
                    0.5
                </text>
                <text x={pad.left - 6} y={yScale(1) + 3} textAnchor="end">
                    1.0
                </text>
            </g>
        </svg>
    );
}

function AgentRiskView(): React.ReactElement {
    const [earliest, setEarliest] = React.useState<string>("-24h@h");
    const [refreshIntervalMs, setRefreshIntervalMs] = React.useState<number>(30000);
    const [tick, setTick] = React.useState<number>(0);
    const lastBlockRef = React.useRef<number | null>(null);
    const seenSuccessfulRef = React.useRef<boolean>(false);
    const [blockTickKey, setBlockTickKey] = React.useState<number>(0);

    React.useEffect(() => {
        if (refreshIntervalMs === 0) {
            return;
        }
        const id = setInterval(() => setTick((t) => t + 1), refreshIntervalMs);
        return () => clearInterval(id);
    }, [refreshIntervalMs]);

    // Window/refresh-interval change resets the live-tick baseline.
    React.useEffect(() => {
        lastBlockRef.current = null;
        seenSuccessfulRef.current = false;
    }, [earliest, refreshIntervalMs]);

    const total = useSplunkSearch("total", QUERIES.total, earliest, "now", 1, tick);
    const block = useSplunkSearch("block", QUERIES.block, earliest, "now", 1, tick);
    const high = useSplunkSearch("high", QUERIES.high, earliest, "now", 1, tick);
    const agents = useSplunkSearch("agents", QUERIES.agents, earliest, "now", 1, tick);
    const tokensSaved = useSplunkSearch("tokens_saved", QUERIES.tokens_saved, earliest, "now", 1, tick);
    const ts = useSplunkSearch("ts", QUERIES.ts, earliest, "now", 200, tick);
    const heatmap = useSplunkSearch("heatmap", QUERIES.heatmap, earliest, "now", 5000, tick);
    const topAgents = useSplunkSearch("top_agents", QUERIES.top_agents, earliest, "now", 10, tick);
    const msj = useSplunkSearch("msj", QUERIES.msj, "-7d", "now", 500, tick);

    const onBlockValue = React.useCallback((n: number) => {
        if (seenSuccessfulRef.current && lastBlockRef.current !== null && n > lastBlockRef.current) {
            setBlockTickKey((k) => k + 1);
        }
        lastBlockRef.current = n;
        seenSuccessfulRef.current = true;
    }, []);

    const allStates: SearchState[] = [total, block, high, agents, tokensSaved, ts, heatmap, topAgents, msj];
    const ok = allStates.filter((s) => s.status === "ok").length;
    const errored = allStates.filter((s) => s.status === "error").length;
    const pending = allStates.length - ok - errored;
    let footerStatus = `Refresh: ${ok}/${allStates.length} OK`;
    if (errored > 0) {
        footerStatus += `, ${errored} errored`;
    }
    if (pending > 0) {
        footerStatus += `, ${pending} in flight`;
    }
    const refreshIndicator =
        errored > 0 && pending === 0
            ? "stale"
            : refreshIntervalMs > 0
                ? "live"
                : "manual";

    return (
        <div className="splunkgate-suit">
            <div className="ar-page">
                <header className="ar-header">
                    <div>
                        <h1 className="ar-header-title">SplunkGate — Agent Risk Overview</h1>
                        <div className="ar-header-subtitle">
                            Real-time CISO/SOC view of AI agent safety verdicts across the estate.
                        </div>
                    </div>
                    <div className="ar-controls">
                        <div className="ar-control">
                            <label htmlFor="ar-time">Time range</label>
                            <select id="ar-time" value={earliest} onChange={(e) => setEarliest(e.target.value)}>
                                {TIME_PRESETS.map((p) => (
                                    <option key={p.value} value={p.value}>
                                        {p.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="ar-control">
                            <label htmlFor="ar-refresh">Auto-refresh</label>
                            <select
                                id="ar-refresh"
                                value={refreshIntervalMs}
                                onChange={(e) => setRefreshIntervalMs(parseInt(e.target.value, 10) || 0)}
                            >
                                {REFRESH_PRESETS.map((p) => (
                                    <option key={p.value} value={p.value}>
                                        {p.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div
                            className={`ar-refresh ${refreshIndicator === "stale" ? "ar-refresh-stale" : ""}`}
                        >
                            {refreshIndicator}
                        </div>
                    </div>
                </header>

                <section className="ar-kpis">
                    <Kpi id="kpi-total" label="Total verdicts" suffix="verdicts in window" state={total} field="count" />
                    <Kpi
                        id={`kpi-block-${blockTickKey}`}
                        label="BLOCKED actions"
                        suffix="intercepted before LLM/tool"
                        state={block}
                        field="count"
                        extraClass="ar-kpi-block ar-tick"
                        onValue={onBlockValue}
                    />
                    <Kpi
                        id="kpi-high"
                        label="HIGH severity"
                        suffix="rule hits"
                        state={high}
                        field="count"
                        extraClass="ar-kpi-high"
                    />
                    <Kpi id="kpi-agents" label="Distinct agents" suffix="active in window" state={agents} field="agents" />
                    <Kpi
                        id="kpi-tokens"
                        label="Tokens saved"
                        suffix="BLOCK × tokens_used"
                        state={tokensSaved}
                        field="tokens_saved"
                    />
                </section>

                <div className="ar-panel">
                    <h2>Verdicts by label, per hour</h2>
                    <p className="ar-panel-desc">
                        Stacked verdict counts per hour over the selected window. ALLOW (paper green) sits at the base;
                        MODIFY (amber) and REVIEW (blue) ride above; BLOCK (vermillion) is painted as a discrete overlay
                        so the brand moment is never muddied by composition with the stack.
                    </p>
                    <AreaPanel state={ts} />
                </div>

                <section className="ar-grid">
                    <div className="ar-panel">
                        <h2>Rules-by-hour heatmap</h2>
                        <p className="ar-panel-desc">
                            Per-hour severity-weighted score for each of the 11 Cisco AI Defense rule names. Row order
                            verbatim from the Cisco Offer Description. Unmapped rules (taxonomy drift) appear in an
                            &quot;Other&quot; row at the bottom.
                        </p>
                        <HeatmapPanel state={heatmap} />
                    </div>
                    <div className="ar-panel">
                        <h2>Top agents by BLOCKED count</h2>
                        <p className="ar-panel-desc">
                            {VERDICT_INSPECTOR_AVAILABLE
                                ? "Click a row to drill into the Verdict Inspector for that agent."
                                : "Drill-down to Verdict Inspector lands in v1.1; rows shown as monospace identifiers for now."}
                        </p>
                        <TopAgentsPanel state={topAgents} />
                    </div>
                </section>

                <div className="ar-panel">
                    <h2>MSJ scaling indicator (last 7 days)</h2>
                    <p className="ar-panel-desc">
                        Detection rate vs. in-context message count per agent — Many-Shot Jailbreaking probabilistic
                        floor (Anthropic 2024). Window is hard-pinned to -7d regardless of the cockpit time range above.
                    </p>
                    <MsjPanel state={msj} />
                </div>

                <footer className="ar-footer">
                    <span>SplunkGate v1.0.0</span>
                    <span>{TIME_PRESETS.find((p) => p.value === earliest)?.label ?? earliest}</span>
                    <span>{footerStatus}</span>
                </footer>
            </div>
        </div>
    );
}

const root = document.getElementById(MOUNT_ID);
if (!root) {
    // eslint-disable-next-line no-console
    console.warn(`[splunkgate-agent-risk] mount node #${MOUNT_ID} not found`);
} else {
    createRoot(root).render(<AgentRiskView />);
}
