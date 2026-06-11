import { SectionHead } from "../shared/SectionHead";
import { CodeBlock } from "../shared/CodeBlock";
import { Shield } from "../shared/Shield";
import { AG_LINKS } from "@/lib/links";
import { EXAMPLE_VERDICT } from "@/lib/verdict-data";
import { jsonHighlight } from "@/lib/highlight";

interface DetailRow {
  field: string;
  value: string;
  // Optional CSS class — paired with `value` so a label cell cannot lose its
  // colour cue when fields move around.
  valueClass?: string;
}

const ROWS: ReadonlyArray<DetailRow> = [
  { field: "_time", value: "2026-06-08 14:03:21.118" },
  { field: "agent_id", value: "support-agent-7f3a" },
  { field: "surface", value: "mw_model" },
  { field: "verdict_label", value: "block", valueClass: "l-block" },
  { field: "severity", value: "HIGH", valueClass: "s-high" },
  { field: "rule", value: "Prompt Injection" },
  { field: "source", value: "splunklib_security · ai_defense" },
  { field: "latency_ms", value: "213.4" },
  { field: "atlas", value: "AML.T0051" },
];

export function RealVerdict() {
  return (
    <section className="ag-sec-wrap sec sec-alt" id="verdict">
      <div className="wrap">
        <SectionHead
          kicker="One type, end to end"
          title="A real verdict — and the row it creates."
          lead="One Pydantic type flows through all four surfaces. Every field maps 1:1 to packages/splunkgate_core/verdict.py, so the verdict you block on is the verdict the SOC reads."
          right={
            <a className="ag-btn ag-btn-ghost ag-btn-sm" href={AG_LINKS.github} target="_blank" rel="noreferrer">
              verdict.py ↗
            </a>
          }
        />
        <div className="verdict-grid rv">
          <div>
            <div className="vp-label">
              Verdict{" "}
              <span className="atlas-chip">
                <span style={{ width: 6, height: 6, borderRadius: 2, background: "var(--accent)" }} />
                MITRE ATLAS AML.T0051
              </span>
            </div>
            <CodeBlock
              name="splunkgate_core.Verdict — emitted by every surface"
              html={jsonHighlight(EXAMPLE_VERDICT)}
              plain={JSON.stringify(EXAMPLE_VERDICT, null, 2)}
            />
          </div>
          <div>
            <div className="vp-label">Verdict Inspector · provenance for this trace_id</div>
            <div className="spl">
              <div className="spl-bar">
                <span className="spl-crumb">
                  <Shield size={12} fill="#cfc8b6" /> SplunkGate
                  <span className="spl-sep">›</span>
                  Verdict detail
                </span>
              </div>
              <div className="spl-body" style={{ padding: 0 }}>
                <table className="spl-table">
                  <tbody>
                    {ROWS.map((r) => (
                      <tr key={r.field}>
                        <td style={{ color: "#6f8499", width: 130 }}>{r.field}</td>
                        <td
                          className={r.valueClass ?? ""}
                          style={{ color: r.valueClass ? undefined : "#cfc8b6", whiteSpace: "normal" }}
                        >
                          {r.value}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div
              className="mono"
              style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 12, lineHeight: 1.5 }}
            >
              Click-through in Splunk surfaces every related event sharing this trace_id across all four surfaces — full chain of custody, no joins.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
