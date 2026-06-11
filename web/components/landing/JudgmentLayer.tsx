import { SectionHead } from "../shared/SectionHead";
import { Src } from "../shared/Src";
import { AG_LINKS } from "@/lib/links";

const JUDGES = [
  {
    role: "role-classifier",
    roleLabel: "The classifier",
    name: "Cisco AI Defense",
    sub: "Inspection API · 11 named rules",
    p: "The binary classifier. Every verdict's label sits here — Prompt Injection, PII, PHI, PCI and seven more, each name verbatim from Cisco's docs.",
    note: "Mock-first in dev; live calls gated on SPLUNKGATE_AI_DEFENSE_API_KEY. 10M queries / app / year.",
    srcHref: AG_LINKS.cisco,
    srcLabel: "cisco.com",
  },
  {
    role: "role-explainer",
    roleLabel: "The explainer",
    name: "Foundation-Sec",
    sub: "fdtn-ai · explainer only",
    p: "Generates the human-readable WHY-string in Verdict.explanation. It never classifies — that boundary is enforced in the type system (ADR-003).",
    note: "v1 ships a deterministic template explainer; the Foundation-Sec | ai SPL swap is a one-file change, pending Splunk Hosted Models access.",
    srcHref: AG_LINKS.foundsec,
    srcLabel: "hugging face",
  },
  {
    role: "role-future",
    roleLabel: "Future judge",
    name: "Galileo Luna-2",
    sub: "Cisco-owned since May 2026",
    p: "A hosted judge designed to plug in as a third evaluator the day Cisco publishes its SDK or HTTP integration.",
    note: "Ships as a documented stub today — no announced Splunk integration date, so it claims nothing it can't do yet.",
    srcHref: null,
    srcLabel: null,
  },
];

export function JudgmentLayer() {
  return (
    <section className="ag-sec-wrap sec" id="judgment">
      <div className="wrap">
        <SectionHead
          kicker="The judgment layer"
          title="Three models, each doing the job it was built for."
          lead="SplunkGate doesn't train a new guardrail model. It orchestrates production-grade primitives — and is precise, in code, about which model is allowed to do what."
        />
        <div className="card-grid cols-3 rv">
          {JUDGES.map((j) => (
            <div className="judge" key={j.name}>
              <span className={"judge-role " + j.role}>{j.roleLabel}</span>
              <h3>{j.name}</h3>
              <div className="judge-sub mono">{j.sub}</div>
              <p>{j.p}</p>
              <div className="judge-note">
                {j.note}
                {j.srcHref && j.srcLabel && (
                  <>
                    {" "}
                    <span style={{ marginLeft: 4 }}>
                      <Src href={j.srcHref}>{j.srcLabel}</Src>
                    </span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
