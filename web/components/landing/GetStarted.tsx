import { SectionHead } from "../shared/SectionHead";
import { CodeBlock } from "../shared/CodeBlock";
import { trust } from "@/lib/highlight";

const BUILTON: Array<[string, string]> = [
  ["Cisco AI Defense", "Inspection API"],
  ["Foundation-Sec", "fdtn-ai"],
  ["splunklib.ai", "3.0.0"],
  ["DefenseClaw", "Apache-2.0"],
  ["Cisco Security Cloud", "app 7404"],
  ["MCP Watch", "app 8765"],
  ["DNS Guard AI", "app 7922"],
];

const TERMINAL_HTML = trust(`<span class="tok-com"># install the middleware</span>
pip install <span class="tok-str">splunkgate-mw</span>

<span class="tok-com"># then add SafetyModelMiddleware to your agent</span>
<span class="tok-com"># middleware=[...] — that's the whole change</span>`);

const SPLUNK_HTML = trust(`<span class="tok-com"># Manage Apps -> Install app from file</span>
splunkgate_app-1.0.0.tgz

<span class="tok-com"># dashboards live, sourcetype:</span>
<span class="tok-blue">cisco_ai_defense:splunkgate_verdict</span>`);

export function GetStarted() {
  return (
    <section className="ag-sec-wrap sec" id="start">
      <div className="wrap">
        <SectionHead kicker="Get started" title="Two ways in. Both take minutes." />
        <div className="start-grid rv">
          <div className="start-card">
            <h3>For the platform engineer</h3>
            <p>Add the middleware to a splunklib.ai agent and you&apos;re gated in three lines.</p>
            <CodeBlock name="terminal" html={TERMINAL_HTML} plain="pip install splunkgate-mw" />
          </div>
          <div className="start-card">
            <h3>For the CISO &amp; SOC</h3>
            <p>Install the Splunk app from a tarball. Verdicts appear next to your Cisco AI Defense events.</p>
            <CodeBlock name="splunk web" html={SPLUNK_HTML} plain="splunkgate_app-1.0.0.tgz" />
          </div>
        </div>

        <div style={{ marginTop: 46 }} className="rv">
          <div className="kicker" style={{ marginBottom: 18 }}>Built on, not instead of</div>
          <div className="builton">
            {BUILTON.map((b) => (
              <div className="bo-chip" key={b[0]}>
                <span className="bo-n">{b[0]}</span>
                <span className="bo-r mono">{b[1]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
