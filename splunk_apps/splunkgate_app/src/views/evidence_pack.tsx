/**
 * SplunkGate — Regulator Evidence Pack (SUIT view, story-suit-evidence-pack).
 *
 * TypeScript source-of-truth for the built bundle at
 * `static/splunkgate-suit/evidence_pack.js`. Per the PR-15 contract, the
 * vanilla-JS bundle ships hand-written so the tarball packer needs no Node
 * toolchain at pack time. This TSX file is what the Phase-2 webpack build
 * will emit once the CI workflow gains a Node lane.
 *
 * **DRIFT CONTRACT**: when you fix a bug in this file, you MUST fix the
 * same bug in `static/splunkgate-suit/evidence_pack.js`. The test
 * `test_drift_invariants_match` enforces shared invariants (SR 26-2 quote,
 * panel titles, SPL queries, jurisdictional banner copy, error/empty
 * state markers) but cannot enforce semantic equivalence in full.
 *
 * SPL data sources lift verbatim from
 * `docs/archive/dashboard-studio-v2/regulator_evidence_pack.xml`.
 */

import * as React from "react";
import { createRoot } from "react-dom/client";
import "../styles/tokens.css";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare const require: any;

const MOUNT_ID = "splunkgate-evidence-pack";
const SEARCH_TIMEOUT_MS = 30000;

interface JurisdictionalProfile {
    value: "ALL" | "FSI" | "HIPAA" | "PCI" | "PUBSEC";
    label: string;
}

interface TimePreset {
    value: string;
    label: string;
}

const JURISDICTIONAL_PROFILES: ReadonlyArray<JurisdictionalProfile> = [
    { value: "ALL", label: "All profiles" },
    { value: "FSI", label: "FSI (FFIEC-AIML / SR 26-2)" },
    { value: "HIPAA", label: "HIPAA (Safe Harbor 18)" },
    { value: "PCI", label: "PCI (PCI-DSS 11.x)" },
    { value: "PUBSEC", label: "PUBSEC (NIST AI RMF)" },
];

const TIME_PRESETS: ReadonlyArray<TimePreset> = [
    { value: "-24h@h", label: "Last 24 hours" },
    { value: "-7d@d", label: "Last 7 days" },
    { value: "-30d@d", label: "Last 30 days" },
    { value: "-90d@d", label: "Last 90 days" },
    { value: "-365d@d", label: "Last 365 days" },
];

/* SR 26-2 footnote 3 — verbatim from joint Federal Reserve / OCC / FDIC
 * SR 26-2 Attachment, p. 3, April 17, 2026. Do not paraphrase. */
const SR_26_2_QUOTE =
    "Generative AI and agentic AI models are novel and rapidly evolving. " +
    "As such, they are not within the scope of this guidance. Nonetheless, " +
    "a banking organization's risk management and governance practices " +
    "should guide the determination of appropriate governance and " +
    "controls for any tools, processes, or systems not covered in this " +
    "document. However, the principles described in this guidance apply " +
    "to traditional statistical and quantitative models and non-generative, " +
    "non-agentic AI models.";

const SR_26_2_ATTRIBUTION =
    "SR 26-2 Attachment, footnote 3, p. 3 — joint Federal Reserve / OCC / FDIC, April 17, 2026.";

const QUERIES = {
    header_kpis:
        '`splunkgate_data` | stats count as total_decisions, dc(trace_id) as unique_traces, count(eval(explanation!="")) as attested_decisions',
    nist_rmf:
        '| makeresults count=4 | eval _time=now() | streamstats count as row | eval function = case(row=1,"GOVERN", row=2,"MAP", row=3,"MEASURE", row=4,"MANAGE"), splunkgate_components = case(row=1,"S1 middleware policy enforcement; S4 dashboards expose accountability roles", row=2,"S2 MCP server enumerates agent boundaries; splunkgate_verdict_history KV-store maps decision context", row=3,"S4 eval harness produces precision/recall/F1/ECE; OTel gen_ai.evaluation.result events emit per-decision scores", row=4,"S1 model_middleware blocks/redacts; story-mw-08 audit chain threads pre+post trace_ids; story-app-08 RBA closes the loop in ES"), evidence_query = case(row=1,"`splunkgate_data` surface=mw_model | stats count", row=2,"`splunkgate_data` | stats dc(agent_id) as agents dc(surface) as surfaces", row=3,"index=cisco_ai_defense sourcetype=cisco_ai_defense:splunkgate_verdict | stats count", row=4,"`splunkgate_data` verdict_label=block | stats count by agent_id") | table function splunkgate_components evidence_query',
    eu_article_6:
        '| makeresults count=5 | eval _time=now() | streamstats count as row | eval annex_iii_use_case = case(row=1,"Critical infrastructure (Annex III §2)", row=2,"Employment, worker management (Annex III §4)", row=3,"Essential private/public services (Annex III §5)", row=4,"Law enforcement (Annex III §6)", row=5,"Administration of justice + democratic processes (Annex III §8)"), article_6_trigger = case(row=1,"Article 6(2) — Annex III listed", row=2,"Article 6(2) — Annex III + profiling clause (paragraph 3 last subparagraph)", row=3,"Article 6(2) — Annex III", row=4,"Article 6(2) — Annex III", row=5,"Article 6(2) — Annex III + profiling clause"), splunkgate_response = case(row=1,"S1 model_middleware blocks injection attempts; verdicts logged with trace_id for Article 9 risk-management evidence", row=2,"S1 PII/PHI redaction; story-app-07 HIPAA panel renders detection counts by Safe Harbor 18 identifier", row=3,"All 4 surfaces emit OTel events; story-app-08 RBA escalates HIGH-severity to ES analyst", row=4,"Foundation-Sec explainer (or template v1) attaches WHY-string for due-process review", row=5,"PCI panel + audit-chain trace_ids satisfy decision-traceability obligations") | table annex_iii_use_case article_6_trigger splunkgate_response',
    hipaa:
        "`splunkgate_data` rule=PHI | stats count by surface, agent_id | sort -count | head 18",
    pci:
        "`splunkgate_data` rule=PCI | stats count by surface, agent_id, severity | sort -count",
    footer:
        '| makeresults | eval _time=now() | eval generated = strftime(now(),"%Y-%m-%d %H:%M:%S %Z") | eval app_version = "SplunkGate v1.0.0" | table app_version generated',
} as const;

type SearchKey = keyof typeof QUERIES;
type Row = Record<string, string>;
type Status = "loading" | "ok" | "error" | "idle";

interface SearchState<TRow = Row> {
    status: Status;
    rows: TRow[];
    error?: string;
}

interface SearchManagerInstance {
    cancel?: () => void;
    on: (event: string, cb: (props?: { message?: string }) => void) => void;
    data: (kind: string, params?: { count: number; offset: number }) => {
        on: (event: string, cb: (_unused: unknown, data: { results: Row[] }) => void) => void;
    };
}

/* useSplunkSearch — cancellable, errback-wired, timeout-bounded.
 * Mirrors the runSearch() contract in evidence_pack.js. */
function useSplunkSearch(
    key: SearchKey,
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
                    mgr = new SearchManager({
                        id: `splunkgate-ep-${key}-${Date.now()}`,
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

function timeLabel(earliest: string): string {
    return TIME_PRESETS.find((p) => p.value === earliest)?.label ?? `${earliest} → now`;
}

function profileLabel(tag: JurisdictionalProfile["value"]): string {
    return JURISDICTIONAL_PROFILES.find((p) => p.value === tag)?.label ?? tag;
}

function scopeStatement(tag: JurisdictionalProfile["value"]): string {
    switch (tag) {
        case "ALL":
            return "All in-scope profiles are included in this artifact (FSI / HIPAA / PCI / PUBSEC). Both the HIPAA Safe Harbor 18 and PCI DSS 11.x panels are populated below.";
        case "HIPAA":
            return "Scope: HIPAA Safe Harbor 18. The HIPAA panel below is populated; the PCI panel is excluded from this profile and is omitted from the artifact.";
        case "PCI":
            return "Scope: PCI DSS 11.x. The PCI panel below is populated; the HIPAA panel is excluded from this profile and is omitted from the artifact.";
        case "FSI":
            return "Scope: FSI (FFIEC-AIML / SR 26-2). Neither HIPAA nor PCI panels are in scope for this profile; both are omitted from the artifact.";
        case "PUBSEC":
            return "Scope: PUBSEC (NIST AI RMF). Neither HIPAA nor PCI panels are in scope for this profile; both are omitted from the artifact.";
    }
}

interface TableColumn {
    field: string;
    label: string;
    mono?: boolean;
    functionCol?: boolean;
}

interface TableProps {
    columns: ReadonlyArray<TableColumn>;
    state: SearchState;
    emptyMessage: string;
}

function Table({ columns, state, emptyMessage }: TableProps): React.ReactElement {
    if (state.status === "loading") {
        return <div className="ep-state">Loading…</div>;
    }
    if (state.status === "error") {
        return (
            <div className="ep-state-error-wrap">
                <div className="ep-state-error-head">PANEL FAILED TO LOAD</div>
                <div className="ep-state-error-msg">{state.error}</div>
            </div>
        );
    }
    if (!state.rows.length) {
        return <div className="ep-state ep-state-empty">{emptyMessage}</div>;
    }
    return (
        <table className="ep-table">
            <thead>
                <tr>
                    {columns.map((c) => (
                        <th key={c.field}>{c.label}</th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {state.rows.map((row, i) => (
                    <tr key={i}>
                        {columns.map((c) => {
                            const cls = c.functionCol ? "ep-function" : c.mono ? "ep-mono" : undefined;
                            return (
                                <td key={c.field} className={cls}>
                                    {row[c.field] ?? ""}
                                </td>
                            );
                        })}
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

interface KpiProps {
    label: string;
    value: string;
    suffix: string;
}

function Kpi({ label, value, suffix }: KpiProps): React.ReactElement {
    return (
        <div className="ep-kpi">
            <div className="ep-kpi-label">{label}</div>
            <div className="ep-kpi-value">{value}</div>
            <div className="ep-kpi-suffix">{suffix}</div>
        </div>
    );
}

function HeaderKpis({ state, earliest }: { state: SearchState; earliest: string }): React.ReactElement {
    if (state.status === "loading") {
        return <section className="ep-kpis"><div className="ep-state">Loading…</div></section>;
    }
    if (state.status === "error") {
        return (
            <section className="ep-kpis">
                <div className="ep-state-error-wrap">
                    <div className="ep-state-error-head">PANEL FAILED TO LOAD</div>
                    <div className="ep-state-error-msg">{state.error}</div>
                </div>
            </section>
        );
    }
    const r = state.rows[0] ?? {};
    const total = r.total_decisions ?? "0";
    const traces = r.unique_traces ?? "0";
    const attested = r.attested_decisions ?? "0";
    const totalN = parseInt(total, 10) || 0;
    const attestedN = parseInt(attested, 10) || 0;
    const pct = totalN > 0 ? `${Math.round((attestedN / totalN) * 100)}%` : "0%";
    return (
        <section className="ep-kpis">
            <Kpi label="Coverage period" value={timeLabel(earliest)} suffix="earliest → now" />
            <Kpi label="Total decisions" value={total} suffix="verdicts in window" />
            <Kpi label="Unique trace IDs" value={traces} suffix="agent sessions" />
            <Kpi label="Attested decisions" value={attested} suffix={`${pct} with explanation`} />
        </section>
    );
}

function EvidencePackView(): React.ReactElement {
    const [jurisdictionalTag, setJur] = React.useState<JurisdictionalProfile["value"]>("ALL");
    const [earliest, setEarliest] = React.useState<string>("-30d@d");
    const latest = "now";

    const headerKpis = useSplunkSearch("header_kpis", QUERIES.header_kpis, earliest, latest, 1, true);
    const nistRmf = useSplunkSearch("nist_rmf", QUERIES.nist_rmf, earliest, latest, 10, true);
    const eu = useSplunkSearch("eu_article_6", QUERIES.eu_article_6, earliest, latest, 10, true);
    const hipaaEnabled = jurisdictionalTag === "HIPAA" || jurisdictionalTag === "ALL";
    const pciEnabled = jurisdictionalTag === "PCI" || jurisdictionalTag === "ALL";
    const hipaa = useSplunkSearch("hipaa", QUERIES.hipaa, earliest, latest, 18, hipaaEnabled);
    const pci = useSplunkSearch("pci", QUERIES.pci, earliest, latest, 50, pciEnabled);
    const footer = useSplunkSearch("footer", QUERIES.footer, earliest, latest, 1, true);

    // Export PDF is gated on every active panel reaching ok / error terminal
    // state. Hidden panels (out-of-scope HIPAA/PCI) don't block the gate.
    const activeStates = [headerKpis, nistRmf, eu, footer];
    if (hipaaEnabled) {
        activeStates.push(hipaa);
    }
    if (pciEnabled) {
        activeStates.push(pci);
    }
    const loading = activeStates.filter((s) => s.status === "loading" || s.status === "idle").length;
    const errored = activeStates.filter((s) => s.status === "error").length;
    const ok = activeStates.filter((s) => s.status === "ok").length;
    const exportDisabled = loading > 0 || errored > 0;
    let exportLabel = "Export PDF for examiner record";
    if (loading > 0) {
        exportLabel = `Waiting for ${loading} panel${loading === 1 ? "" : "s"}…`;
    } else if (errored > 0) {
        exportLabel = `${errored} panel${errored === 1 ? "" : "s"} failed — fix before export`;
    }
    let statusLine = `Panel status: ${ok} OK`;
    if (errored > 0) {
        statusLine = `Panel status: ${ok} OK / ${errored} errored`;
    }
    if (loading > 0) {
        statusLine = `Panel status: ${ok} OK / ${errored} errored / ${loading} loading`;
    }

    return (
        <div className="splunkgate-suit">
            <div className="ep-page">
                <header className="ep-header">
                    <div>
                        <h1 className="ep-header-title">SplunkGate — Regulator Evidence Pack</h1>
                        <div className="ep-header-subtitle">
                            Single-shot examiner artifact. Choose your jurisdictional profile and time window;
                            export to PDF for the record.
                        </div>
                    </div>
                    <div className="ep-controls">
                        <div className="ep-control">
                            <label htmlFor="ep-jur">Jurisdictional profile</label>
                            <select
                                id="ep-jur"
                                value={jurisdictionalTag}
                                onChange={(e) => setJur(e.target.value as JurisdictionalProfile["value"])}
                            >
                                {JURISDICTIONAL_PROFILES.map((p) => (
                                    <option key={p.value} value={p.value}>
                                        {p.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="ep-control">
                            <label htmlFor="ep-time">Coverage period</label>
                            <select id="ep-time" value={earliest} onChange={(e) => setEarliest(e.target.value)}>
                                {TIME_PRESETS.map((p) => (
                                    <option key={p.value} value={p.value}>
                                        {p.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <button
                            type="button"
                            className="ep-export-btn"
                            onClick={() => {
                                if (!exportDisabled) {
                                    window.print();
                                }
                            }}
                            disabled={exportDisabled}
                        >
                            {exportLabel}
                        </button>
                    </div>
                </header>

                <div className="ep-jurisdiction-banner">
                    <div className="ep-banner-label">Coverage profile</div>
                    <div className="ep-banner-value">{profileLabel(jurisdictionalTag)}</div>
                    <div className="ep-banner-scope">{scopeStatement(jurisdictionalTag)}</div>
                </div>

                <HeaderKpis state={headerKpis} earliest={earliest} />

                <section className="ep-grid">
                    <div className="ep-panel">
                        <h2>NIST AI RMF function mapping</h2>
                        <p className="ep-panel-desc">
                            4 functions per NIST AI RMF 1.0 Section 5: GOVERN, MAP, MEASURE, MANAGE. Each row pairs the
                            function with the SplunkGate components that produce evidence and the SPL the examiner can
                            run to verify the claim.
                        </p>
                        <Table
                            columns={[
                                { field: "function", label: "Function", functionCol: true },
                                { field: "splunkgate_components", label: "SplunkGate components" },
                                { field: "evidence_query", label: "Evidence SPL", mono: true },
                            ]}
                            state={nistRmf}
                            emptyMessage="No NIST RMF rows returned."
                        />
                    </div>
                    <div className="ep-quote-panel ep-panel">
                        <h2>SR 26-2 footnote 3 (April 2026) — out of named MRM scope</h2>
                        <p className="ep-quote">{SR_26_2_QUOTE}</p>
                        <div className="ep-quote-attribution">{SR_26_2_ATTRIBUTION}</div>
                        <p className="ep-quote-framing">
                            <strong>SplunkGate framing:</strong> SR 26-2 explicitly leaves GenAI / agentic AI out of named
                            MRM scope. Examiners therefore rely on the bank&apos;s general risk management and governance
                            practices to evaluate SplunkGate-instrumented agents. Every SplunkGate verdict carries a
                            trace_id, an evaluator chain, and an OTel event — together these constitute the auditable
                            evidence chain the footnote anticipates.
                        </p>
                    </div>
                </section>

                <div className="ep-panel">
                    <h2>EU AI Act Article 6 — high-risk classification mapping</h2>
                    <p className="ep-panel-desc">
                        Article 6 high-risk classification triggers (Article 6(1) product-safety integration + Article
                        6(2) Annex III enumeration). High-risk Annex III obligations under Article 6(2) apply from 2
                        August 2026. SplunkGate decisions can satisfy Article 9 (risk management) evidence obligations.
                    </p>
                    <Table
                        columns={[
                            { field: "annex_iii_use_case", label: "Annex III use case" },
                            { field: "article_6_trigger", label: "Article 6 trigger" },
                            { field: "splunkgate_response", label: "SplunkGate response" },
                        ]}
                        state={eu}
                        emptyMessage="No EU AI Act rows returned."
                    />
                </div>

                {hipaaEnabled && (
                    <div className="ep-panel ep-gated">
                        <h2>HIPAA Safe Harbor 18 — PHI detection counts</h2>
                        <p className="ep-panel-desc">
                            PHI detection counts grouped by surface and agent for the coverage window.
                        </p>
                        <Table
                            columns={[
                                { field: "count", label: "PHI hits" },
                                { field: "surface", label: "Surface", mono: true },
                                { field: "agent_id", label: "Agent ID", mono: true },
                            ]}
                            state={hipaa}
                            emptyMessage="No PHI verdicts in the selected coverage period."
                        />
                    </div>
                )}

                {pciEnabled && (
                    <div className="ep-panel ep-gated">
                        <h2>PCI DSS 11.x — PCI detection counts</h2>
                        <p className="ep-panel-desc">
                            PCI detection counts grouped by surface, agent, and severity. Supports PCI-DSS 4.0 11.x
                            sub-requirements via the persisted KV-store retention of PCI-tagged trace_ids.
                        </p>
                        <Table
                            columns={[
                                { field: "count", label: "PCI hits" },
                                { field: "surface", label: "Surface", mono: true },
                                { field: "agent_id", label: "Agent ID", mono: true },
                                { field: "severity", label: "Severity" },
                            ]}
                            state={pci}
                            emptyMessage="No PCI verdicts in the selected coverage period."
                        />
                    </div>
                )}

                <footer className="ep-footer">
                    <span>SplunkGate v1.0.0</span>
                    <span>{timeLabel(earliest)}</span>
                    <span>{statusLine}</span>
                    <span>Generated {footer.rows[0]?.generated ?? ""}</span>
                </footer>
            </div>
        </div>
    );
}

const root = document.getElementById(MOUNT_ID);
if (!root) {
    // eslint-disable-next-line no-console
    console.warn(`[splunkgate-evidence-pack] mount node #${MOUNT_ID} not found`);
} else {
    createRoot(root).render(<EvidencePackView />);
}
