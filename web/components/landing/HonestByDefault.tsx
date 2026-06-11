import type { ReactNode } from "react";
import { SectionHead } from "../shared/SectionHead";

interface TrustItem {
  ic: string;
  h: string;
  p: ReactNode;
}

const ITEMS: TrustItem[] = [
  {
    ic: "🟡",
    h: "AI Defense runs mock-first",
    p: (
      <>
        Dev and CI use a recorded mock of the Inspection API; live calls switch on with{" "}
        <span className="mono">SPLUNKGATE_AI_DEFENSE_API_KEY</span>. No hidden network dependency in the demo.
      </>
    ),
  },
  {
    ic: "🟡",
    h: "The explainer is a template in v1",
    p: (
      <>
        v1 ships a deterministic ~30-LOC template explainer. The Foundation-Sec{" "}
        <span className="mono">| ai</span> SPL swap is the designed path, deferred until Splunk Hosted Models access is confirmed — a one-file change.
      </>
    ),
  },
  {
    ic: "❓",
    h: "Luna-2 is a documented stub",
    p: (
      <>
        Cisco&apos;s Galileo Luna-2 has no announced Splunk integration date, so it ships as a stub that raises{" "}
        <span className="mono">NotImplementedError</span> — designed-for, not claimed.
      </>
    ),
  },
  {
    ic: "✅",
    h: "Every claim is source-flagged",
    p: (
      <>
        The repo carries a hallucination audit grading each fact ✅/🟡/❓/❌. The rule counts, quotas, install numbers and quotes on this page trace back to primary sources.
      </>
    ),
  },
];

export function HonestByDefault() {
  return (
    <section className="ag-sec-wrap sec sec-alt" id="honest">
      <div className="wrap">
        <SectionHead
          kicker="Honest by default"
          title="What's real, what's mocked, what's deferred."
          lead="A safety tool that overstates itself is a liability. SplunkGate is explicit about its own seams — the same discipline it applies to your agents, applied to its own claims."
        />
        <div className="trust-grid rv">
          {ITEMS.map((it) => (
            <div className="trust-item" key={it.h}>
              <div className="ti-ic" style={{ fontSize: 15 }}>{it.ic}</div>
              <div>
                <h4>{it.h}</h4>
                <p>{it.p}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="eval rv">
          <table>
            <thead>
              <tr>
                <th>Evaluation harness</th>
                <th>Corpus</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>F1</th>
                <th>p99</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Prompt-injection detection</td>
                <td>JailbreakBench</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
              </tr>
              <tr>
                <td>Sensitive-data leak</td>
                <td>AdvBench</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
              </tr>
              <tr>
                <td>Tool-arg safety</td>
                <td>Imprompter</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
                <td className="pending">pending</td>
              </tr>
            </tbody>
          </table>
          <div className="eval-note">
            Results populate from the eval harness —{" "}
            <span style={{ color: "var(--blue-ink)" }}>uv run pytest · eval-spec.md</span>. We publish the table shape now and the numbers when they&apos;re real, never before.
          </div>
        </div>
      </div>
    </section>
  );
}
