"use client";

import { useTicker } from "../hooks/useTicker";
import { SectionHead } from "../shared/SectionHead";
import { Src } from "../shared/Src";
import { AG_LINKS } from "@/lib/links";

const NODES = [
  { k: "Agent", s: "support_agent.py", i: "agent" },
  { k: "splunkgate-mw", s: "model_middleware · pre-inference", i: "mw" },
  { k: "Cisco AI Defense", s: "classify → Prompt Injection", i: "cls", flag: true },
  { k: "Explainer", s: "WHY-string · template v1", i: "exp" },
  { k: "OpenTelemetry", s: "gen_ai.evaluation.result", i: "otel" },
  { k: "Splunk HEC", s: "cisco_ai_defense:splunkgate_verdict", i: "splunk", tick: true },
];

export function VerdictPath() {
  const emitted = useTicker(48217, { every: 2600, spread: 2 });
  return (
    <section className="ag-sec-wrap sec" id="path">
      <div className="wrap">
        <SectionHead
          kicker="The verdict path"
          title="One verdict. Six hops. Every one auditable."
          lead="A malicious prompt is caught at the model boundary, classified by Cisco AI Defense, explained, wrapped as an OpenTelemetry event, and written to Splunk — each step a primary-source-grounded record, not a black box."
        />
        <ol className="vpath rv">
          <span className="vpath-scan" aria-hidden="true" />
          {NODES.map((n, i) => (
            <li
              className={"vstep" + (n.flag ? " vstep-flag" : "")}
              style={{ ["--i" as string]: i } as React.CSSProperties}
              key={n.i}
            >
              <span className="vstep-rail"><span className="vstep-dot" /></span>
              <div className="vstep-body">
                <div className="vstep-head">
                  <span className="vstep-n mono">{String(i + 1).padStart(2, "0")}</span>
                  <span className="vstep-k">{n.k}</span>
                  {n.flag && <span className="vstep-chip v-block mono">BLOCK · HIGH</span>}
                  {n.tick && <span className="vstep-chip mono">{emitted.toLocaleString()} verdicts</span>}
                </div>
                <div className="vstep-s mono">{n.s}</div>
              </div>
            </li>
          ))}
        </ol>
        <div className="hf-foot-l mono" style={{ marginTop: 34 }}>
          <span className="hf-stat"><b>11</b> Cisco AI Defense rules <Src href={AG_LINKS.cisco}>quota</Src></span>
          <span className="ag-dot-sep" />
          <span className="hf-stat">first-pass <b>splunklib.security</b> 9-regex</span>
          <span className="ag-dot-sep" />
          <span className="hf-stat">OTel GenAI semconv <Src href={AG_LINKS.otel}>spec</Src></span>
        </div>
      </div>
    </section>
  );
}
