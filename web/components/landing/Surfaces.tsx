"use client";

import { useState, type ReactNode } from "react";
import { SectionHead } from "../shared/SectionHead";
import { CodeBlock } from "../shared/CodeBlock";
import { trust, type TrustedHtml } from "@/lib/highlight";

interface SurfaceCode {
  name: string;
  html: TrustedHtml;
  plain: string;
}

interface SurfaceMetaRow {
  label: string;
  value: ReactNode;
}

interface Surface {
  code: string; // "S1", "S2", "S3", "S4"
  pkg: string; // package or surface name (splunkgate-mw, splunkgate-mcp, …)
  audience: string; // who this surface is for
  headline: string; // serif h3
  description: string; // prose
  meta: ReadonlyArray<SurfaceMetaRow>;
  example: SurfaceCode;
}

const SURFACES: ReadonlyArray<Surface> = [
  {
    code: "S1",
    pkg: "splunkgate-mw",
    audience: "Agent developer · Python",
    headline: "Middleware for splunklib.ai agents",
    description:
      "Drop a safety middleware into a splunklib.ai agent's middleware list. Pre-inference scan catches prompt injection; post-inference scan catches data leaks. A BLOCK raises ModelInputBlockedBySplunkGate, so the tool call never runs.",
    meta: [
      { label: "Package", value: <span>pip install <b>splunkgate-mw</b> · v0.1.0</span> },
      { label: "Classes", value: <span><b>SafetyModelMiddleware</b>, SafetyToolMiddleware, SafetySubagentMiddleware, SafetyAgentMiddleware</span> },
      { label: "Built on", value: <span>splunklib.ai 3.0.0 · LangChain v1</span> },
    ],
    example: {
      name: "support_agent.py",
      html: trust(`<span class="tok-kw">from</span> splunklib.ai <span class="tok-kw">import</span> Agent
<span class="tok-kw">from</span> splunkgate_mw <span class="tok-kw">import</span> SafetyModelMiddleware, Config

agent = <span class="tok-cls">Agent</span>(
    model=<span class="tok-str">"claude-sonnet-4.5"</span>,
    tools=[send_email, lookup_customer],
    middleware=[
        <span class="tok-fn">SafetyModelMiddleware</span>(Config()),
    ],
)
<span class="tok-com"># prompt-injection input -> raises ModelInputBlockedBySplunkGate</span>
<span class="tok-com"># the handler is never called; the tool never fires</span>`),
      plain: `from splunklib.ai import Agent
from splunkgate_mw import SafetyModelMiddleware, Config

agent = Agent(
    model="claude-sonnet-4.5",
    tools=[send_email, lookup_customer],
    middleware=[
        SafetyModelMiddleware(Config()),
    ],
)`,
    },
  },
  {
    code: "S2",
    pkg: "splunkgate-mcp",
    audience: "Any MCP client",
    headline: "An MCP server, parallel to Splunk's",
    description:
      "Any MCP client — Claude Desktop, Cursor, LangGraph, custom — can call the four SplunkGate tools to score a prompt, judge a tool call, check an output for leaks, or audit a trace. It runs alongside Splunk's own MCP server via a standard multi-server config; we coexist, we don't register into theirs.",
    meta: [
      { label: "Tools", value: <span>4 tools · all return <b>Verdict</b> (or <b>AuditReport</b>)</span> },
      { label: "Spec", value: <span>MCP 2025-11-25</span> },
      { label: "Coexists", value: <span>Splunk MCP Server (app 7931) · SAIA (7245)</span> },
    ],
    example: {
      name: "claude_desktop_config.json",
      html: trust(`{
  <span class="tok-blue">"mcpServers"</span>: {
    <span class="tok-blue">"splunk"</span>: { <span class="tok-blue">"command"</span>: <span class="tok-str">"splunk-mcp"</span> },
    <span class="tok-blue">"splunkgate-mcp-server"</span>: {
      <span class="tok-blue">"command"</span>: <span class="tok-str">"python"</span>,
      <span class="tok-blue">"args"</span>: [<span class="tok-str">"-m"</span>, <span class="tok-str">"splunkgate_mcp"</span>],
      <span class="tok-blue">"env"</span>: { <span class="tok-blue">"SPLUNKGATE_AI_DEFENSE_API_KEY"</span>: <span class="tok-str">"&lt;your-key&gt;"</span> }
    }
  }
}
<span class="tok-com">// tools: splunkgate_score_prompt_injection, splunkgate_judge_tool_call,</span>
<span class="tok-com">//        splunkgate_check_output_leak, splunkgate_audit_trace</span>`),
      plain: `{
  "mcpServers": {
    "splunk": { "command": "splunk-mcp" },
    "splunkgate-mcp-server": {
      "command": "python",
      "args": ["-m", "splunkgate_mcp"],
      "env": { "SPLUNKGATE_AI_DEFENSE_API_KEY": "<your-key>" }
    }
  }
}`,
    },
  },
  {
    code: "S3",
    pkg: "DefenseClaw",
    audience: "Non-splunklib.ai agents",
    headline: "An HTTP-intercept gateway",
    description:
      "For agents that aren't built on splunklib.ai, the DefenseClaw OSS gateway (Apache-2.0) intercepts at the HTTP layer. SplunkGate ships a config delta that points its audit sink at the same Splunk HEC endpoint — depend, don't rebuild.",
    meta: [
      { label: "Approach", value: <span>config delta over OSS gateway</span> },
      { label: "Sink", value: <span>splunk_hec.go → same sourcetype</span> },
      { label: "Licence", value: <span>Apache-2.0 upstream</span> },
    ],
    example: {
      name: "defenseclaw.delta.yaml",
      html: trust(`<span class="tok-blue">audit</span>:
  <span class="tok-blue">sinks</span>:
    - <span class="tok-blue">type</span>: <span class="tok-str">splunk_hec</span>
      <span class="tok-blue">endpoint</span>: <span class="tok-str">https://hec.splunk:8088</span>
      <span class="tok-blue">sourcetype</span>: <span class="tok-str">cisco_ai_defense:splunkgate_verdict</span>
<span class="tok-blue">inspect</span>:
  <span class="tok-blue">evaluator</span>: <span class="tok-str">splunkgate</span>   <span class="tok-com"># same verdict shape</span>
  <span class="tok-blue">on_block</span>: <span class="tok-str">reject_4xx</span>`),
      plain: `audit:
  sinks:
    - type: splunk_hec
      endpoint: https://hec.splunk:8088
      sourcetype: cisco_ai_defense:splunkgate_verdict
inspect:
  evaluator: splunkgate
  on_block: reject_4xx`,
    },
  },
  {
    code: "S4",
    pkg: "splunkgate_app",
    audience: "CISO · SOC · compliance",
    headline: "A Splunk app",
    description:
      "The consumer surface. Three Dashboard Studio v2 dashboards, SPL + MLTK macros, a KV-store of verdict history, and Enterprise Security risk-based alerting — installed straight from a tarball, AppInspect-clean.",
    meta: [
      { label: "Install", value: <span>Manage Apps → Install from file → <b>splunkgate_app-1.0.0.tgz</b></span> },
      { label: "Dashboards", value: <span>Agent Risk Overview · Verdict Inspector · Regulator Evidence Pack</span> },
      { label: "ES", value: <span>risk_factors.conf → risk-based alerting</span> },
    ],
    example: {
      name: "install.sh",
      html: trust(`<span class="tok-com"># build the byte-deterministic app package</span>
<span class="tok-fn">tar</span> -czf splunkgate_app-1.0.0.tgz splunk_apps/splunkgate_app

<span class="tok-com"># Splunk Web -> Manage Apps -> Install app from file</span>
<span class="tok-com"># verdicts arrive on sourcetype:</span>
<span class="tok-blue">cisco_ai_defense:splunkgate_verdict</span>

<span class="tok-com"># they sit next to Cisco Security Cloud (app 7404)</span>
<span class="tok-com"># events -> one unified SOC search</span>`),
      plain: `tar -czf splunkgate_app-1.0.0.tgz splunk_apps/splunkgate_app
# Splunk Web -> Manage Apps -> Install app from file`,
    },
  },
] as const;

export function Surfaces() {
  const [active, setActive] = useState(0);
  const a = SURFACES[active];
  return (
    <section className="ag-sec-wrap sec sec-alt" id="surfaces">
      <div className="wrap">
        <SectionHead
          kicker="Four surfaces · one verdict"
          title="However your agents are built, SplunkGate gets in front of them."
          lead="Four integration paths cover the whole estate — from a Python import to an HTTP gateway — and every one emits the exact same Verdict into Splunk."
        />
        <div className="surf-tabs rv">
          {SURFACES.map((sf, i) => (
            <button
              className={"surf-tab" + (i === active ? " on" : "")}
              key={sf.code}
              onClick={() => setActive(i)}
            >
              <span className="surf-s">{sf.code}</span>
              <span>
                <span className="surf-t mono">{sf.pkg}</span>
                <span className="surf-w">{sf.audience}</span>
              </span>
            </button>
          ))}
        </div>
        <div className="surf-panel rv">
          <div className="surf-desc">
            <h3>{a.headline}</h3>
            <p>{a.description}</p>
            <div className="surf-meta">
              {a.meta.map((m) => (
                <div className="surf-meta-row" key={m.label}>
                  <span className="mk">{m.label}</span>
                  <span className="mv mono">{m.value}</span>
                </div>
              ))}
            </div>
          </div>
          <CodeBlock name={a.example.name} html={a.example.html} plain={a.example.plain} />
        </div>
      </div>
    </section>
  );
}
