# SplunkGate — Architecture Diagram

> **Title:** How a verdict travels
> **Subtitle:** agent → judgment → verdict → OpenTelemetry → Splunk
>
> This file lives at the repo root to satisfy the Devpost submission
> requirement (`architecture_diagram.(md|pdf|png)` at repository root).
> The canonical visual reference is the Brand Kit's `id="art-arch"`
> SVG; this Markdown version is rendered for GitHub + the Devpost form.
> The accompanying SVG export will land at `docs/assets/architecture.svg`
> (see `docs/design/architecture-diagram-brief.md`).

## How SplunkGate interacts with Splunk

```mermaid
flowchart LR
    subgraph S1["SURFACES · ANY AGENT"]
        direction TB
        A1["<b>S1 · splunkgate-mw</b><br/><i>splunklib.ai middleware</i>"]
        A2["<b>S2 · splunkgate-mcp</b><br/><i>MCP server (4 tools)</i>"]
        A3["<b>S3 · DefenseClaw</b><br/><i>HTTP gateway delta</i>"]
    end

    subgraph CORE["SPLUNKGATE JUDGMENT CORE<br/>classify → explain → decide"]
        direction TB
        C1["<b>Cisco AI Defense</b><br/><i>binary classifier · 11 rules</i>"]
        C2["<b>Foundation-Sec / gpt-oss</b><br/><i>Hosted Model explainer · WHY string</i>"]
        C3["<b>Verdict</b><br/><i>BLOCK / MODIFY / REVIEW / ALLOW · severity</i>"]
        C1 --> C2 --> C3
    end

    subgraph SPLUNK["LAND & CONSUME · S4"]
        direction TB
        SP1["<b>OpenTelemetry</b><br/><i>gen_ai.evaluation.result</i>"]
        SP2["<b>Splunk HEC</b><br/><i>cisco_ai_defense:splunkgate_verdict</i>"]
        SP3["<b>3 SUIT dashboards</b><br/><i>Agent Risk · Verdict Inspector · Evidence Pack</i>"]
        SP1 --> SP2 --> SP3
    end

    A1 --> CORE
    A2 --> CORE
    A3 --> CORE
    CORE --> SPLUNK

    classDef accent fill:#BC3A26,stroke:#93291A,color:#F1ECE1
    classDef paper fill:#F1ECE1,stroke:#1D1A13,color:#1D1A13
    classDef dark fill:#17140E,stroke:#3A352B,color:#F0EADD

    class C3 accent
    class A1,A2,A3,SP1,SP2,SP3 paper
    class C1,C2 dark
```

## Where AI integrates

```mermaid
flowchart TB
    subgraph AGENT["agent (any framework)"]
        UI[user input] --> AGENT_LLM[LLM call]
        AGENT_LLM --> AGENT_TOOL[tool call]
    end

    UI -.intercept.-> MW_MODEL[SafetyModelMiddleware<br/>pre-inference]
    MW_MODEL -->|"<b>Cisco AI Defense</b><br/>(score_prompt_injection)"| AID1[AI Defense API]
    AID1 --> MW_MODEL

    AGENT_LLM -.intercept.-> MW_POST[SafetyModelMiddleware<br/>post-inference]
    MW_POST -->|"<b>Cisco AI Defense</b><br/>(check_output_leak)"| AID2[AI Defense API]
    AID2 --> MW_POST
    MW_POST -->|"<b>Splunk Hosted Model</b><br/>(explain_via_hosted_model)"| OLLAMA["Ollama: gpt-oss:20b<br/>(or foundation-sec:8b)"]
    OLLAMA --> MW_POST

    AGENT_TOOL -.intercept.-> MW_TOOL[SafetyToolMiddleware<br/>pre-tool]
    MW_TOOL -->|"<b>Cisco AI Defense</b><br/>(judge_tool_call)"| AID3[AI Defense API]
    AID3 --> MW_TOOL

    MW_MODEL --> V[<b>Verdict</b>]
    MW_POST --> V
    MW_TOOL --> V

    V -->|"<b>OpenTelemetry</b><br/>gen_ai.evaluation.result"| HEC[Splunk HEC]
    HEC --> IDX[index=cisco_ai_defense]
    IDX --> ES[ES Risk-Based Alerting]
    IDX --> DASH[3 SUIT dashboards]

    classDef ai fill:#FAE9E5,stroke:#BC3A26,color:#1D1A13
    classDef splunk fill:#E7F0FF,stroke:#1A6FE0,color:#1D1A13
    classDef verdict fill:#BC3A26,stroke:#93291A,color:#F1ECE1

    class AID1,AID2,AID3,OLLAMA ai
    class HEC,IDX,ES,DASH splunk
    class V verdict
```

## Data flow between services

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant A as Agent
    participant MW as splunkgate-mw
    participant AID as Cisco AI Defense
    participant OL as Ollama (Hosted Model)
    participant LLM as Agent's LLM
    participant HEC as Splunk HEC
    participant SOC as SOC analyst (SUIT dashboards)

    U->>A: prompt
    A->>MW: ModelRequest
    MW->>AID: score_prompt_injection(text)
    AID-->>MW: rules + severity
    alt BLOCK
        MW->>HEC: Verdict (BLOCK)
        MW-->>A: raise ModelInputBlockedBySplunkGate
        Note over A: handler never runs
    else ALLOW
        MW->>LLM: forward
        LLM-->>MW: response
        MW->>AID: check_output_leak(response)
        AID-->>MW: rules + severity
        opt explainer_backend=ollama AND verdict != ALLOW
            MW->>OL: explain_via_hosted_model(verdict, ctx)
            OL-->>MW: natural-language WHY string
        end
        MW->>HEC: Verdict (+ explanation)
        MW-->>A: ModelResponse
        A-->>U: reply
    end

    HEC->>SOC: dashboards tick + RBA fires on HIGH
```

## Splunk capabilities this project leverages

| # | Capability | How SplunkGate uses it |
|---|---|---|
| 1 | **Splunk Python SDK / AI for Splunk Apps** | Surface 1 wraps `splunklib.ai` agents at all 4 middleware boundaries (tool / subagent / model / agent). |
| 2 | **Splunk MCP Server** | Coexistence with Splunkbase app 7931 — SplunkGate ships its own MCP server (4 safety tools) alongside Splunk's data-query server in one Claude Desktop config (`examples/mcp-clients/claude-desktop-config.json`). |
| 3 | **Splunk Hosted Models** | Real LLM verdict explanations via Ollama-served Hosted Models (default `gpt-oss:20b`, Apache-2.0; `foundation-sec:8b` is a one-config-flag swap once a Modelfile is built). See `scripts/setup_hosted_models.sh` and ADR-003a Transport B-Ollama. |
| 4 | **Splunk Developer Tools (AppInspect)** | The Splunk app passes AppInspect cleanly on every CI run. Build artifact is byte-deterministic across machines. |

## Cross-references

- Full architecture rationale + every ADR: `docs/architecture.md`
- Designer brief for the SVG render: `docs/design/architecture-diagram-brief.md`
- Hosted Models integration walkthrough: `docs/integrations/hosted-models.md`
- MCP coexistence example: `examples/mcp-clients/`
- Hackathon-resource cross-reference audit: `docs/audits/2026-06-11-hackathon-resource-audit.md`

---

*Apache-2.0 · Splunk Agentic Ops Hackathon 2026 · https://github.com/Blockchain-Oracle/splunkgate*
