import { SectionHead } from "../shared/SectionHead";
import { Shield } from "../shared/Shield";
import { Src } from "../shared/Src";
import { AG_LINKS } from "@/lib/links";

const RMF = [
  { f: "GOVERN", c: "Verdict policy + profiles", q: "splunkgate_verdicts | stats by profile" },
  { f: "MAP", c: "Surface + ATLAS technique", q: "lookup atlas_technique rule" },
  { f: "MEASURE", c: "Severity + latency + eval", q: "splunkgate_eval_metrics" },
  { f: "MANAGE", c: "ES risk-based alerting", q: "risk_factors.conf" },
];

export function AuditEvidence() {
  return (
    <section className="ag-sec-wrap sec" id="evidence">
      <div className="wrap">
        <SectionHead
          kicker="The payoff · for the buyer"
          title="Do security right, and the audit trail is already written."
          lead="SplunkGate is bought to stop bad agent actions. But because every verdict is a primary-source-grounded record, the same data answers the examiner — no second system, no retro-fitting evidence."
        />

        <div className="dash-cap rv" style={{ marginBottom: 12 }}>
          <span className="dc-t">Regulator Evidence Pack</span>
          <span className="dc-s mono">jurisdictional profile · hideEdit</span>
          <span className="dc-badge mono">splunkgate v1.0.0</span>
        </div>
        <div className="spl rv">
          <div className="spl-bar">
            <span className="spl-crumb">
              <Shield size={12} fill="#cfc8b6" /> SplunkGate
              <span className="spl-sep">›</span>Regulator Evidence Pack
            </span>
            <button className="spl-export">⤓ Export PDF for OCC examiner</button>
          </div>
          <div className="spl-body">
            <div className="spl-panel">
              <div className="spl-ptitle">
                NIST AI RMF — function alignment <Src href={AG_LINKS.nist}>nist.gov</Src>
              </div>
              <div className="spl-rmf">
                {RMF.map((r) => (
                  <div className="spl-rmf-c" key={r.f}>
                    <div className="rf"><span className="ck">✓</span>{r.f}</div>
                    <div className="rc">{r.c}</div>
                    <div className="rq mono">{r.q}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="spl-quote" style={{ marginTop: 12 }}>
              <div className="q">
                &ldquo;Generative AI and agentic AI models are novel and rapidly evolving. As such, they are not within the scope of this guidance. Nonetheless, a banking organization&apos;s risk management and governance practices should guide the determination of appropriate governance and controls for any tools, processes, or systems not covered in this document.&rdquo;
              </div>
              <div className="qc mono">
                SR 26-2 Attachment · footnote 3 · p.3 — Federal Reserve / OCC / FDIC · April 17 2026
              </div>
            </div>
          </div>
        </div>

        <div className="verbatim rv" style={{ marginTop: 22, borderLeftColor: "var(--med)" }}>
          <div className="verbatim-tag">why it<br />matters</div>
          <div>
            <div className="vframe" style={{ marginTop: 0, fontSize: 17 }}>
              SR 26-2 leaves agentic AI <b>outside</b> named model-risk scope — so examiners fall back on your own governance. <b>EU AI Act Article 6</b> high-risk obligations attach <b>August 2 2026</b>, with record-keeping and penalties up to <b>€35M or 7% of global turnover</b>. The verdicts SplunkGate already writes are the auditable record both regimes expect.
            </div>
            <div className="vcite" style={{ marginTop: 14 }}>
              <span>NIST AI RMF <Src href={AG_LINKS.nist}>↗</Src></span>
              <span className="ag-dot-sep" />
              <span>SR 26-2 fn.3 <Src href={AG_LINKS.sr262}>↗</Src></span>
              <span className="ag-dot-sep" />
              <span>EU AI Act Art. 6 + Art. 99 <Src href={AG_LINKS.euart6}>↗</Src></span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
