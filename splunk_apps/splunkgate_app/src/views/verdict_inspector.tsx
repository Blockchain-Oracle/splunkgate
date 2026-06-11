/**
 * SplunkGate — Verdict Inspector (SUIT view, story-suit-verdict-inspector).
 *
 * TypeScript source-of-truth for the built bundle at
 * `static/splunkgate-suit/verdict_inspector.js`.
 *
 * **DRIFT CONTRACT**: when you fix a bug in this file, you MUST fix the
 * same bug in `static/splunkgate-suit/verdict_inspector.js`. The test
 * `test_vi_drift_invariants_match_between_js_and_tsx` enforces shared
 * invariants.
 *
 * SPL data sources lift verbatim from
 * `docs/archive/dashboard-studio-v2/verdict_inspector.xml`.
 */

import * as React from "react";
import { createRoot } from "react-dom/client";
import "../styles/tokens.css";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare const require: any;

const MOUNT_ID = "splunkgate-verdict-inspector";
const SEARCH_TIMEOUT_MS = 30000;

const QUERIES = {
    agents_list:
        "`splunkgate_data` | stats values(agent_id) as agent_id | mvexpand agent_id | rename agent_id as label | eval value=label",
    rules_list:
        "`splunkgate_data` | mvexpand rule | stats values(rule) as rule | mvexpand rule | rename rule as label | eval value=label",
    table:
        '`splunkgate_data` agent_id="{AGENT}" severity="{SEVERITY}" verdict_label="{VERDICT_LABEL}" rule="{RULE}" | eval explanation_short = if(len(explanation)>120, substr(explanation,1,120)."…", explanation) | table _time agent_id surface verdict_label severity rule explanation_short latency_ms trace_id | sort -_time | head 200',
    detail:
        '`splunkgate_data` trace_id="{TRACE_ID}" | head 1 | table _time agent_id surface verdict_label severity rule explanation latency_ms trace_id atlas_technique_id atlas_technique_name atlas_tactic_id',
    related: '`splunkgate_data` trace_id="{TRACE_ID}" | table _time surface verdict_label severity rule | sort _time',
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

const SEVERITY_OPTIONS = [
    { value: "*", label: "Any" },
    { value: "HIGH", label: "HIGH" },
    { value: "MEDIUM", label: "MEDIUM" },
    { value: "LOW", label: "LOW" },
    { value: "NONE_SEVERITY", label: "NONE_SEVERITY" },
] as const;

const VERDICT_LABEL_OPTIONS = [
    { value: "*", label: "Any" },
    { value: "block", label: "block" },
    { value: "modify", label: "modify" },
    { value: "review", label: "review" },
    { value: "allow", label: "allow" },
] as const;

const TIME_PRESETS = [
    { value: "-1h@h", label: "Last 1 hour" },
    { value: "-24h@h", label: "Last 24 hours" },
    { value: "-7d@d", label: "Last 7 days" },
    { value: "-30d@d", label: "Last 30 days" },
] as const;

interface SanitizedSpl {
    value: string;
    mutated: boolean;
}

// SPL injection guard. Returns { value, mutated }; the caller MUST surface
// an error if mutated, otherwise the filter UI/SPL diverge silently.
const SPL_SAFE_RE = /^[A-Za-z0-9@._\-:/]*$/;
function sanitizeSplValue(v: string): SanitizedSpl {
    if (!v || v === "*") {
        return { value: "*", mutated: false };
    }
    return { value: v, mutated: !SPL_SAFE_RE.test(v) };
}

// Monotonic SearchManager ID counter — same-ms collisions are possible
// with Date.now() (especially when 5 useSplunkSearch hooks fire on mount).
// Seeded with a random offset so a second mount in the same Splunk Web
// SUI session (view switch + re-mount) cannot collide with the prior
// mount's still-cancelling SearchManager IDs in mvc.Components. F-POST-1.
let SEARCH_ID_SEQ = Math.floor(Math.random() * 1000000);

function formatSplunkTime(raw: string | undefined, kind?: "hms"): string {
    if (raw === undefined || raw === null) {
        return "";
    }
    if (raw === "") {
        return "(empty)";
    }
    if (raw.length >= 19 && raw.indexOf("T") === 10) {
        if (kind === "hms") {
            return raw.substring(11, 19);
        }
        return raw.substring(0, 19).replace("T", " ");
    }
    const epoch = parseFloat(raw);
    // Require > 1e9 (~ year 2001) so truncated fragments like "2026"
    // can't pass and render a 1970 fake date. F-POST-3.
    if (isFinite(epoch) && epoch > 1e9) {
        const d = new Date(epoch * 1000);
        if (!isNaN(d.getTime())) {
            if (kind === "hms") {
                return d.toISOString().substring(11, 19);
            }
            return d.toISOString().substring(0, 19).replace("T", " ");
        }
    }
    return `unparseable: ${raw}`;
}

function useSplunkSearch(
    key: SearchKey | string,
    query: string,
    earliest: string,
    latest: string,
    resultsCount: number,
    enabled: boolean
): SearchState {
    const [s, setS] = React.useState<SearchState>({ status: "idle", rows: [] });

    React.useEffect(() => {
        if (!enabled) {
            setS({ status: "idle", rows: [] });
            return;
        }
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
                    SEARCH_ID_SEQ += 1;
                    mgr = new SearchManager({
                        id: `splunkgate-vi-${key}-${SEARCH_ID_SEQ}`,
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
    }, [key, query, earliest, latest, resultsCount, enabled]);

    return s;
}

function copyToClipboard(text: string): Promise<void> {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    }
    return new Promise<void>((resolve, reject) => {
        try {
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.style.position = "fixed";
            ta.style.top = "-1000px";
            ta.style.left = "-1000px";
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            const ok = document.execCommand("copy");
            document.body.removeChild(ta);
            if (ok) {
                resolve();
            } else {
                reject(new Error("execCommand returned false"));
            }
        } catch (e) {
            reject(e as Error);
        }
    });
}

interface ChipProps {
    label: string;
}

function SeverityChip({ label }: ChipProps): React.ReactElement {
    const sev = label || "NONE_SEVERITY";
    return <span className={`vi-chip vi-sev-${sev}`}>{sev}</span>;
}

function ResultChip({ label }: ChipProps): React.ReactElement | null {
    const v = (label || "").toLowerCase();
    if (!v) {
        return null;
    }
    return <span className={`vi-result vi-result-${v}`}>{v}</span>;
}

interface PanelStateProps {
    state: SearchState;
    emptyMessage?: string;
}

function PanelStateBlock({ state, emptyMessage }: PanelStateProps): React.ReactElement | null {
    if (state.status === "loading" || state.status === "idle") {
        return <div className="vi-state">Loading…</div>;
    }
    if (state.status === "error") {
        return (
            <div className="vi-state-error-wrap">
                <div className="vi-state-error-head">PANEL FAILED TO LOAD</div>
                <div className="vi-state-error-msg">{state.error}</div>
            </div>
        );
    }
    if (state.rows.length === 0) {
        return <div className="vi-state">{emptyMessage ?? "No data."}</div>;
    }
    return null;
}

interface TraceChipProps {
    traceId: string;
}

function TraceChip({ traceId }: TraceChipProps): React.ReactElement {
    const [status, setStatus] = React.useState<"idle" | "copied" | "failed">("idle");
    const onClick = React.useCallback(() => {
        copyToClipboard(traceId)
            .then(() => {
                setStatus("copied");
                setTimeout(() => setStatus("idle"), 800);
            })
            .catch((err: unknown) => {
                // VISIBLE failure feedback so the analyst never pastes a
                // stale clipboard into the wrong ticket.
                setStatus("failed");
                setTimeout(() => setStatus("idle"), 1500);
                // eslint-disable-next-line no-console
                console.warn("[splunkgate-verdict-inspector] copy-to-clipboard failed", err);
            });
    }, [traceId]);
    const cls = status === "copied" ? "vi-copied" : status === "failed" ? "vi-copy-failed" : "";
    const label = status === "copied"
        ? "copied!"
        : status === "failed"
            ? "copy failed — select manually"
            : traceId;
    return (
        <button
            type="button"
            className={`vi-trace-chip ${cls}`}
            onClick={onClick}
            data-trace-id={traceId}
        >
            <svg className="vi-trace-chip-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
                <rect x={3} y={3} width={9} height={11} rx={1} />
                <path d="M5 1h7a2 2 0 0 1 2 2v8" />
            </svg>
            <span>{label}</span>
        </button>
    );
}

interface DetailProps {
    state: SearchState;
    selectedTraceId: string | null;
}

function DetailPanel({ state, selectedTraceId }: DetailProps): React.ReactElement {
    if (!selectedTraceId) {
        return (
            <div className="vi-detail-empty">
                No verdict selected — click a row in the table on the left.
            </div>
        );
    }
    const safe = sanitizeSplValue(selectedTraceId);
    if (safe.mutated) {
        return (
            <div className="vi-state-error-wrap">
                <div className="vi-state-error-head">REFUSING TO QUERY MUTATED TRACE_ID</div>
                <div className="vi-state-error-msg">
                    {`trace_id '${selectedTraceId}' contains characters that cannot be safely passed to SPL. Refusing to query — escape upstream.`}
                </div>
            </div>
        );
    }
    const block = <PanelStateBlock state={state} emptyMessage={`No verdict found for trace_id ${selectedTraceId}.`} />;
    if (block) {
        return block;
    }
    const r = state.rows[0];
    const traceId = r.trace_id ?? selectedTraceId;
    const esUrl = `/app/SplunkEnterpriseSecuritySuite/investigation_workbench?form.search=trace_id%3D%22${encodeURIComponent(traceId)}%22`;
    return (
        <>
            <div className="vi-detail-field">
                <div className="vi-detail-label">Time</div>
                <div className="vi-detail-value vi-mono">{formatSplunkTime(r._time)}</div>
            </div>
            <div className="vi-detail-field">
                <div className="vi-detail-label">Trace ID</div>
                <div className="vi-detail-value">
                    <TraceChip traceId={traceId} />
                </div>
            </div>
            <div className="vi-detail-field">
                <div className="vi-detail-label">Agent</div>
                <div className="vi-detail-value vi-mono">{r.agent_id ?? ""}</div>
            </div>
            <div className="vi-detail-field">
                <div className="vi-detail-label">Surface</div>
                <div className="vi-detail-value vi-mono">{r.surface ?? ""}</div>
            </div>
            <div className="vi-detail-field">
                <div className="vi-detail-label">Verdict</div>
                <div className="vi-detail-value">
                    <ResultChip label={r.verdict_label ?? ""} /> &nbsp; <SeverityChip label={r.severity ?? ""} />
                </div>
            </div>
            <div className="vi-detail-field">
                <div className="vi-detail-label">Rule</div>
                <div className="vi-detail-value">{r.rule ?? ""}</div>
            </div>
            <div className="vi-detail-field">
                <div className="vi-detail-label">Latency</div>
                <div className="vi-detail-value vi-mono">{r.latency_ms ?? ""} ms</div>
            </div>
            {(r.atlas_technique_id || r.atlas_technique_name) && (
                <div className="vi-detail-field">
                    <div className="vi-detail-label">MITRE ATLAS</div>
                    <div className="vi-detail-value vi-mono">
                        {r.atlas_technique_id ?? ""} · {r.atlas_technique_name ?? ""}
                        {r.atlas_tactic_id ? ` · tactic ${r.atlas_tactic_id}` : ""}
                    </div>
                </div>
            )}
            <div className="vi-detail-field">
                <div className="vi-detail-label">Explanation</div>
                <div className="vi-detail-value">
                    {r.explanation ? (
                        <div className="vi-explanation-block">{r.explanation}</div>
                    ) : (
                        <span className="vi-state">No explanation attached to this verdict.</span>
                    )}
                </div>
            </div>
            <a className="vi-es-drill-btn" href={esUrl} target="_blank" rel="noopener noreferrer">
                Open in ES Investigation Workbench →
            </a>
        </>
    );
}

function RelatedPanel({ state, selectedTraceId }: { state: SearchState; selectedTraceId: string | null }): React.ReactElement {
    if (!selectedTraceId) {
        return <div className="vi-detail-empty">No trace_id selected.</div>;
    }
    const block = <PanelStateBlock state={state} emptyMessage="No related events under this trace_id." />;
    if (block) {
        return block;
    }
    return (
        <>
            {state.rows.map((r, i) => {
                const t = formatSplunkTime(r._time, "hms");
                return (
                    <div className="vi-related-row" key={i}>
                        <span className="vi-related-time">{t}</span>
                        <span className="vi-related-rule">{r.rule ?? ""}</span>
                        <span className="vi-related-surface">{r.surface ?? ""}</span>
                        <ResultChip label={r.verdict_label ?? ""} />
                    </div>
                );
            })}
        </>
    );
}

// 150ms debounce so keyboard-driven dropdown spam coalesces into one
// SearchManager construction (parity with the JS bundle's
// debouncedRefreshList F-POST-medium fix).
function useDebouncedValue<T>(value: T, delayMs: number): T {
    const [debounced, setDebounced] = React.useState<T>(value);
    React.useEffect(() => {
        const id = setTimeout(() => setDebounced(value), delayMs);
        return () => clearTimeout(id);
    }, [value, delayMs]);
    return debounced;
}

function VerdictInspectorView(): React.ReactElement {
    const [earliest, setEarliest] = React.useState<string>("-24h@h");
    const latest = "now";
    const [agent, setAgent] = React.useState<string>("*");
    const [ruleSel, setRuleSel] = React.useState<string>("*");
    const [severity, setSeverity] = React.useState<string>("*");
    const [verdictLabel, setVerdictLabel] = React.useState<string>("*");
    const [selectedTraceId, setSelectedTraceId] = React.useState<string | null>(null);

    // Debounce filter state changes through to the SPL query so
    // rapid-fire dropdown changes don't issue 5+ SearchManagers in 200ms.
    const debouncedAgent = useDebouncedValue(agent, 150);
    const debouncedRule = useDebouncedValue(ruleSel, 150);
    const debouncedSeverity = useDebouncedValue(severity, 150);
    const debouncedVerdictLabel = useDebouncedValue(verdictLabel, 150);

    const agentsListState = useSplunkSearch("agents_list", QUERIES.agents_list, earliest, latest, 500, true);
    const rulesListState = useSplunkSearch("rules_list", QUERIES.rules_list, earliest, latest, 200, true);

    const safeAgent = sanitizeSplValue(debouncedAgent);
    const safeSeverity = sanitizeSplValue(debouncedSeverity);
    const safeVerdictLabel = sanitizeSplValue(debouncedVerdictLabel);
    const safeRule = sanitizeSplValue(debouncedRule);
    const mutatedFilters: string[] = [];
    if (safeAgent.mutated) { mutatedFilters.push(`agent='${debouncedAgent}'`); }
    if (safeSeverity.mutated) { mutatedFilters.push(`severity='${debouncedSeverity}'`); }
    if (safeVerdictLabel.mutated) { mutatedFilters.push(`verdict='${debouncedVerdictLabel}'`); }
    if (safeRule.mutated) { mutatedFilters.push(`rule='${debouncedRule}'`); }
    const tableQuery = QUERIES.table
        .replace("{AGENT}", safeAgent.value)
        .replace("{SEVERITY}", safeSeverity.value)
        .replace("{VERDICT_LABEL}", safeVerdictLabel.value)
        .replace("{RULE}", safeRule.value);
    // Only run the table search if no filter values were mutated. The
    // useSplunkSearch hook handles the disabled state via the `enabled`
    // flag; the panel surfaces the error message inline.
    const tableState = useSplunkSearch("table", tableQuery, earliest, latest, 200, mutatedFilters.length === 0);

    const safeTraceId = selectedTraceId ? sanitizeSplValue(selectedTraceId) : { value: "", mutated: false };
    const detailQuery = QUERIES.detail.replace("{TRACE_ID}", safeTraceId.value);
    const relatedQuery = QUERIES.related.replace("{TRACE_ID}", safeTraceId.value);
    const detailEnabled = selectedTraceId !== null && !safeTraceId.mutated;
    const relatedEnabled = selectedTraceId !== null && !safeTraceId.mutated;
    const detailState = useSplunkSearch("detail", detailQuery, earliest, latest, 1, detailEnabled);
    const relatedState = useSplunkSearch("related", relatedQuery, earliest, latest, 200, relatedEnabled);

    const agentsOptions: { value: string; label: string }[] = React.useMemo(() => {
        const out = [{ value: "*", label: "Any" }];
        if (agentsListState.status === "ok") {
            agentsListState.rows.forEach((r) => {
                if (r.value) {
                    out.push({ value: r.value, label: r.label ?? r.value });
                }
            });
        }
        return out;
    }, [agentsListState]);

    const rulesOptions = React.useMemo(() => {
        const out = [{ value: "*", label: "Any" }];
        if (rulesListState.status === "ok") {
            rulesListState.rows.forEach((r) => {
                if (r.value) {
                    out.push({ value: r.value, label: r.label ?? r.value });
                }
            });
        }
        return out;
    }, [rulesListState]);

    const onClearFilters = (): void => {
        setAgent("*");
        setRuleSel("*");
        setSeverity("*");
        setVerdictLabel("*");
        // Reset the row selection so an orphaned detail/related panel
        // doesn't sit there pretending the data is still current after
        // the list refreshes against different filters. F-POST-2.
        setSelectedTraceId(null);
    };

    return (
        <div className="splunkgate-suit">
            <div className="vi-page">
                <header className="vi-header">
                    <div>
                        <h1 className="vi-header-title">SplunkGate — Verdict Inspector</h1>
                        <div className="vi-header-subtitle">
                            Filter by time / agent / rule / severity / verdict label. Click a row to see full provenance + every other
                            verdict from the same trace_id across all four SplunkGate surfaces.
                        </div>
                    </div>
                </header>

                <section className="vi-filter-bar">
                    <div className="vi-control">
                        <label htmlFor="vi-time">Time range</label>
                        <select id="vi-time" value={earliest} onChange={(e) => setEarliest(e.target.value)}>
                            {TIME_PRESETS.map((p) => (
                                <option key={p.value} value={p.value}>
                                    {p.label}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="vi-control">
                        <label htmlFor="vi-agent">Agent</label>
                        <select id="vi-agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
                            {agentsOptions.map((o) => (
                                <option key={o.value} value={o.value}>
                                    {o.label}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="vi-control">
                        <label htmlFor="vi-rule">Rule</label>
                        <select id="vi-rule" value={ruleSel} onChange={(e) => setRuleSel(e.target.value)}>
                            {rulesOptions.map((o) => (
                                <option key={o.value} value={o.value}>
                                    {o.label}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="vi-control">
                        <label htmlFor="vi-severity">Severity</label>
                        <select id="vi-severity" value={severity} onChange={(e) => setSeverity(e.target.value)}>
                            {SEVERITY_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>
                                    {o.label}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="vi-control">
                        <label htmlFor="vi-verdict">Verdict label</label>
                        <select id="vi-verdict" value={verdictLabel} onChange={(e) => setVerdictLabel(e.target.value)}>
                            {VERDICT_LABEL_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>
                                    {o.label}
                                </option>
                            ))}
                        </select>
                    </div>
                    <button type="button" className="vi-clear-btn" onClick={onClearFilters} title="Reset all filters">
                        Clear
                    </button>
                </section>

                <section className="vi-body">
                    <div className="vi-panel">
                        <h2>Verdicts (latest 200)</h2>
                        <p className="vi-panel-desc">
                            Click a row to inspect that verdict. Highlight + detail panel update in &lt;200ms.
                        </p>
                        <div className="vi-list-wrap">
                            {mutatedFilters.length > 0 ? (
                                <div className="vi-state-error-wrap">
                                    <div className="vi-state-error-head">REFUSING TO QUERY MUTATED FILTERS</div>
                                    <div className="vi-state-error-msg">
                                        {`Mutated filter values: ${mutatedFilters.join(", ")}. Pick a different value or escape upstream.`}
                                    </div>
                                </div>
                            ) : tableState.status === "ok" && tableState.rows.length > 0 ? (
                                <table className="vi-table">
                                    <thead>
                                        <tr>
                                            <th>Time</th>
                                            <th>Agent</th>
                                            <th>Surface</th>
                                            <th>Verdict</th>
                                            <th>Severity</th>
                                            <th>Rule</th>
                                            <th>Explanation</th>
                                            <th>Latency</th>
                                            <th>Trace</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {tableState.rows.map((r, i) => {
                                            const traceId = r.trace_id ?? "";
                                            const time = formatSplunkTime(r._time);
                                            const selected = traceId === selectedTraceId ? " vi-row-selected" : "";
                                            return (
                                                <tr
                                                    key={i}
                                                    className={`vi-row${selected}`}
                                                    onClick={() => setSelectedTraceId(traceId || null)}
                                                >
                                                    <td className="vi-mono">{time}</td>
                                                    <td className="vi-mono">{r.agent_id ?? ""}</td>
                                                    <td className="vi-mono">{r.surface ?? ""}</td>
                                                    <td>
                                                        <ResultChip label={r.verdict_label ?? ""} />
                                                    </td>
                                                    <td>
                                                        <SeverityChip label={r.severity ?? ""} />
                                                    </td>
                                                    <td>{r.rule ?? ""}</td>
                                                    <td className="vi-explanation">{r.explanation_short ?? ""}</td>
                                                    <td className="vi-mono">{r.latency_ms ?? ""}ms</td>
                                                    <td className="vi-mono">{traceId.substring(0, 8)}…</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            ) : (
                                <PanelStateBlock
                                    state={tableState}
                                    emptyMessage="No verdicts match the current filters in the selected time range."
                                />
                            )}
                        </div>
                    </div>

                    <div>
                        <div className="vi-panel">
                            <h2>Verdict detail</h2>
                            <p className="vi-panel-desc">
                                Full provenance for the selected trace_id including MITRE ATLAS technique mapping. Drill into ES
                                Investigation Workbench from the button below.
                            </p>
                            <DetailPanel state={detailState} selectedTraceId={selectedTraceId} />
                        </div>
                        <div className="vi-panel">
                            <h2>Related events for this trace_id</h2>
                            <p className="vi-panel-desc">
                                Every other SplunkGate verdict emitted under the same trace_id, across all four surfaces
                                (mw_model / mw_tool / mw_subagent / mcp_*).
                            </p>
                            <RelatedPanel state={relatedState} selectedTraceId={selectedTraceId} />
                        </div>
                    </div>
                </section>

                <footer className="vi-footer">
                    <span>SplunkGate v1.0.0</span>
                    <span>
                        {tableState.status === "ok"
                            ? `${tableState.rows.length} row${tableState.rows.length === 1 ? "" : "s"}`
                            : "—"}
                    </span>
                    <span>Filter changes apply immediately.</span>
                </footer>
            </div>
        </div>
    );
}

const root = document.getElementById(MOUNT_ID);
if (!root) {
    // eslint-disable-next-line no-console
    console.warn(`[splunkgate-verdict-inspector] mount node #${MOUNT_ID} not found`);
} else {
    createRoot(root).render(<VerdictInspectorView />);
}
