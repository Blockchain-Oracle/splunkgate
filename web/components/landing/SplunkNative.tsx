"use client";

import { useTicker } from "../hooks/useTicker";
import { SectionHead } from "../shared/SectionHead";
import { Shield } from "../shared/Shield";
import { AreaChart } from "./AreaChart";
import { AG_LINKS } from "@/lib/links";

// One row of the Verdict Inspector mockup. The Splunk dashboard table pairs
// each colour-coded label with a CSS class — the type pins the pairing so a
// future edit cannot land a red "block" cell on an "allow" CSS class.
interface ColouredCell {
  label: string;
  className: string;
}

interface InspectorRow {
  time: string;
  agentId: string;
  surface: string;
  verdict: ColouredCell;
  severity: ColouredCell;
  rule: string;
  latencyMs: string;
}

const ROWS: ReadonlyArray<InspectorRow> = [
  {
    time: "14:03:21",
    agentId: "support-agent-7f3a",
    surface: "mw_model",
    verdict: { label: "block", className: "l-block" },
    severity: { label: "HIGH", className: "s-high" },
    rule: "Prompt Injection",
    latencyMs: "213",
  },
  {
    time: "14:02:54",
    agentId: "sales-copilot-2c",
    surface: "mw_tool",
    verdict: { label: "modify", className: "l-modify" },
    severity: { label: "MEDIUM", className: "s-medium" },
    rule: "PII",
    latencyMs: "188",
  },
  {
    time: "14:02:09",
    agentId: "kb-indexer-91",
    surface: "mcp_judge_tool",
    verdict: { label: "allow", className: "l-allow" },
    severity: { label: "NONE", className: "" },
    rule: "—",
    latencyMs: "96",
  },
  {
    time: "14:01:37",
    agentId: "support-agent-7f3a",
    surface: "mw_model",
    verdict: { label: "block", className: "l-block" },
    severity: { label: "HIGH", className: "s-high" },
    rule: "PHI",
    latencyMs: "204",
  },
  {
    time: "14:00:58",
    agentId: "ticket-triage-5",
    surface: "mw_subagent",
    verdict: { label: "review", className: "l-modify" },
    severity: { label: "MEDIUM", className: "s-medium" },
    rule: "Code Detection",
    latencyMs: "231",
  },
];

export function SplunkNative() {
  const verdicts = useTicker(48217, { every: 2600, spread: 2 });
  const blocked = useTicker(1294, { every: 4400, spread: 1 });
  const high = useTicker(417, { every: 5200, spread: 1 });

  return (
    <section className="ag-sec-wrap sec sec-alt" id="splunk">
      <div className="wrap">
        <SectionHead
          kicker="Splunk-native · zero new console"
          title="It shows up where your SOC already looks."
          lead="Verdicts land on the same cisco_ai_defense:* sourcetype family the Cisco Security Cloud app already populates across 55,544 installs — so analysts get one unified search, not a tenth pane of glass."
          right={
            <a className="ag-btn ag-btn-ghost ag-btn-sm" href={AG_LINKS.splunk7404} target="_blank" rel="noreferrer">
              app 7404 ↗
            </a>
          }
        />

        <div className="dash-wrap">
          <div className="rv">
            <div className="dash-cap">
              <span className="dc-t">Agent Risk Overview</span>
              <span className="dc-s mono">Dashboard Studio v2</span>
              <span className="dc-badge mono">splunkgate_app / S4</span>
            </div>
            <div className="spl">
              <div className="spl-bar">
                <span className="spl-crumb">
                  <Shield size={12} fill="#cfc8b6" /> SplunkGate
                  <span className="spl-sep">›</span>Agent Risk Overview
                </span>
                <span className="spl-time mono">Last 24 hours · mock data</span>
              </div>
              <div className="spl-body">
                <div className="spl-kpis">
                  <div className="spl-kpi"><div className="k-t">Total verdicts</div><div className="k-v">{verdicts.toLocaleString()}</div></div>
                  <div className="spl-kpi"><div className="k-t">BLOCK verdicts</div><div className="k-v red">{blocked.toLocaleString()}</div></div>
                  <div className="spl-kpi"><div className="k-t">HIGH severity</div><div className="k-v orange">{high.toLocaleString()}</div></div>
                  <div className="spl-kpi"><div className="k-t">Distinct agents</div><div className="k-v">38</div></div>
                </div>
                <div className="spl-panel" style={{ marginTop: 12 }}>
                  <div className="spl-ptitle">Verdicts by label · per hour</div>
                  <div className="spl-area"><AreaChart /></div>
                  <div className="spl-legend">
                    <span><i style={{ background: "#5CB85C" }} />allow</span>
                    <span><i style={{ background: "#F0AD4E" }} />modify</span>
                    <span><i style={{ background: "#D9534F" }} />block</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="rv">
            <div className="dash-cap">
              <span className="dc-t">Verdict Inspector</span>
              <span className="dc-s mono">latest 200 · drill-down to provenance</span>
              <span className="dc-badge mono">verdict_label lowercase</span>
            </div>
            <div className="spl">
              <div className="spl-bar">
                <span className="spl-crumb">
                  <Shield size={12} fill="#cfc8b6" /> SplunkGate
                  <span className="spl-sep">›</span>Verdict Inspector
                </span>
                <span className="spl-time mono">time · agent · rule · severity · verdict</span>
              </div>
              <div className="spl-body" style={{ padding: 0 }}>
                <table className="spl-table">
                  <thead>
                    <tr>
                      <th>_time</th><th>agent_id</th><th>surface</th><th>verdict</th>
                      <th>severity</th><th>rule</th><th>ms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ROWS.map((r, i) => (
                      <tr key={`${r.time}-${r.agentId}`} className={i === 0 ? "spl-newrow" : ""}>
                        <td>{r.time}</td>
                        <td style={{ color: "#cfc8b6" }}>{r.agentId}</td>
                        <td>{r.surface}</td>
                        <td className={r.verdict.className}>{r.verdict.label}</td>
                        <td className={r.severity.className}>{r.severity.label}</td>
                        <td style={{ color: "#cfc8b6" }}>{r.rule}</td>
                        <td>{r.latencyMs}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
