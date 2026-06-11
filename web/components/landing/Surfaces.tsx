"use client";

import { useState, type ReactNode } from "react";
import { SectionHead } from "../shared/SectionHead";
import { CodeBlock } from "../shared/CodeBlock";

interface SurfaceMeta {
  s: string;
  t: string;
  w: string;
  h: string;
  p: string;
  meta: Array<[string, ReactNode]>;
  code: { name: string; html: string; plain: string };
}

const SURFACES: SurfaceMeta[] = [
  {
    s: "S1",
    t: "splunkgate-mw",
    w: "Agent developer · Python",
    h: "Middleware for splunklib.ai agents",
    p: "Drop a safety middleware into a splunklib.ai agent's middleware list. Pre-inference scan catches prompt injection; post-inference scan catches data leaks. A BLOCK raises ModelInputBlockedBySplunkGate, so the tool call never runs.",
    meta: [
      ["Package", <span key="p">pip install <b>splunkgate-mw</b> · v0.1.0</span>],
      ["Classes", <span key="c"><b>SafetyModelMiddleware</b>, SafetyToolMiddleware, SafetySubagentMiddleware</span>],
      ["Built on", <span key="b">splunklib.ai 3.0.0 · LangChain v1</span>],
    ],
    code: {
      name: "support_agent.py",
      html: `<span class="tok-kw">from</span> splunklib.ai <span class="tok-kw">import</span> Agent
<span class="tok-kw">from</span> splunkgate_mw <span class="tok-kw">import</span> SafetyModelMiddleware, Config

agent = <span class="tok-cls">Agent</span>(
    model=<span class="tok-str">"claude-sonnet-4.5"</span>,
    tools=[send_email, lookup_customer],
    middleware=[
        <span class="tok-fn">SafetyModelMiddleware</span>(Config(profile=<span class="tok-str">"banking"</span>)),
    ],
)
<span class="tok-com"># prompt-injection input -> raises ModelInputBlockedBySplunkGate</span>
<span class="tok-com"># the handler is never called; the tool never fires</span>`,
      plain: `from splunklib.ai import Agent
from splunkgate_mw import SafetyModelMiddleware, Config

agent = Agent(
    model="claude-sonnet-4.5",
    tools=[send_email, lookup_customer],
    middleware=[
        SafetyModelMiddleware(Config(profile="banking")),
    ],
)`,
    },
  },
  {
    s: "S2",
    t: "splunkgate-mcp",
    w: "Any MCP client",
    h: "An MCP server, parallel to Splunk's",
    p: "Any MCP client — Claude Desktop, Cursor, LangGraph, custom — can call the splunkgate_judge_prompt tool to score a prompt before using it. It runs alongside Splunk's own MCP server via a standard multi-server config; we coexist, we don't register into theirs.",
    meta: [
      ["Hero tool", <span key="h"><b>splunkgate_judge_prompt</b> · outputSchema = Verdict</span>],
      ["Spec", <span key="s">MCP 2025-11-25</span>],
      ["Coexists", <span key="c">Splunk MCP Server (app 7931) · SAIA (7245)</span>],
    ],
    code: {
      name: "claude_desktop_config.json",
      html: `{
  <span class="tok-blue">"mcpServers"</span>: {
    <span class="tok-blue">"splunk"</span>: { <span class="tok-blue">"command"</span>: <span class="tok-str">"splunk-mcp"</span> },
    <span class="tok-blue">"splunkgate"</span>: {
      <span class="tok-blue">"command"</span>: <span class="tok-str">"splunkgate-mcp"</span>,
      <span class="tok-blue">"env"</span>: { <span class="tok-blue">"SPLUNKGATE_PROFILE"</span>: <span class="tok-str">"banking"</span> }
    }
  }
}
<span class="tok-com">// tool: splunkgate_judge_prompt(text) -> Verdict</span>`,
      plain: `{
  "mcpServers": {
    "splunk": { "command": "splunk-mcp" },
    "splunkgate": {
      "command": "splunkgate-mcp",
      "env": { "SPLUNKGATE_PROFILE": "banking" }
    }
  }
}`,
    },
  },
  {
    s: "S3",
    t: "DefenseClaw",
    w: "Non-splunklib.ai agents",
    h: "An HTTP-intercept gateway",
    p: "For agents that aren't built on splunklib.ai, the DefenseClaw OSS gateway (Apache-2.0) intercepts at the HTTP layer. SplunkGate ships a config delta that points its audit sink at the same Splunk HEC endpoint — depend, don't rebuild.",
    meta: [
      ["Approach", <span key="a">config delta over OSS gateway</span>],
      ["Sink", <span key="s">splunk_hec.go → same sourcetype</span>],
      ["Licence", <span key="l">Apache-2.0 upstream</span>],
    ],
    code: {
      name: "defenseclaw.delta.yaml",
      html: `<span class="tok-blue">audit</span>:
  <span class="tok-blue">sinks</span>:
    - <span class="tok-blue">type</span>: <span class="tok-str">splunk_hec</span>
      <span class="tok-blue">endpoint</span>: <span class="tok-str">https://hec.splunk:8088</span>
      <span class="tok-blue">sourcetype</span>: <span class="tok-str">cisco_ai_defense:splunkgate_verdict</span>
<span class="tok-blue">inspect</span>:
  <span class="tok-blue">evaluator</span>: <span class="tok-str">splunkgate</span>   <span class="tok-com"># same verdict shape</span>
  <span class="tok-blue">on_block</span>: <span class="tok-str">reject_4xx</span>`,
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
    s: "S4",
    t: "splunkgate_app",
    w: "CISO · SOC · compliance",
    h: "A Splunk app",
    p: "The consumer surface. Three Dashboard Studio v2 dashboards, SPL + MLTK macros, a KV-store of verdict history, and Enterprise Security risk-based alerting — installed straight from a tarball, AppInspect-clean.",
    meta: [
      ["Install", <span key="i">Manage Apps → Install from file → <b>splunkgate_app-1.0.0.tgz</b></span>],
      ["Dashboards", <span key="d">Agent Risk Overview · Verdict Inspector · Regulator Evidence Pack</span>],
      ["ES", <span key="e">risk_factors.conf → risk-based alerting</span>],
    ],
    code: {
      name: "install.sh",
      html: `<span class="tok-com"># build the byte-deterministic app package</span>
<span class="tok-fn">tar</span> -czf splunkgate_app-1.0.0.tgz splunk_apps/splunkgate_app

<span class="tok-com"># Splunk Web -> Manage Apps -> Install app from file</span>
<span class="tok-com"># verdicts arrive on sourcetype:</span>
<span class="tok-blue">cisco_ai_defense:splunkgate_verdict</span>

<span class="tok-com"># they sit next to Cisco Security Cloud (app 7404)</span>
<span class="tok-com"># events -> one unified SOC search</span>`,
      plain: `tar -czf splunkgate_app-1.0.0.tgz splunk_apps/splunkgate_app
# Splunk Web -> Manage Apps -> Install app from file`,
    },
  },
];

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
              key={sf.s}
              onClick={() => setActive(i)}
            >
              <span className="surf-s">{sf.s}</span>
              <span>
                <span className="surf-t mono">{sf.t}</span>
                <span className="surf-w">{sf.w}</span>
              </span>
            </button>
          ))}
        </div>
        <div className="surf-panel rv">
          <div className="surf-desc">
            <h3>{a.h}</h3>
            <p>{a.p}</p>
            <div className="surf-meta">
              {a.meta.map((m, i) => (
                <div className="surf-meta-row" key={i}>
                  <span className="mk">{m[0]}</span>
                  <span className="mv mono">{m[1]}</span>
                </div>
              ))}
            </div>
          </div>
          <CodeBlock name={a.code.name} html={a.code.html} plain={a.code.plain} />
        </div>
      </div>
    </section>
  );
}
