# SplunkGate demo — 30-line support agent

`support_agent.py` is the headline integration pitch: instantiate four
SplunkGate middleware classes with one profile string and hand them to
`splunklib.ai.Agent`.

## Requirements

- **Python 3.13.** `splunklib.ai` 3.0.0 hard-requires CPython 3.13 — earlier interpreters fail at import time.
- **Splunk Cloud Explorer Edition** (or any Splunk instance with agentic-AI flags enabled).
- An `OPENAI_API_KEY` for `gpt-4o` — replace with `AnthropicModel`/`GoogleModel` if you prefer.

## Environment

```bash
export SPLUNKGATE_SPLUNK_HOST=splunk.example.com
export SPLUNKGATE_SPLUNK_PORT=8089
export SPLUNKGATE_SPLUNK_TOKEN=eyJraWQ...   # Splunk session token
export OPENAI_API_KEY=sk-...
# Optional — Cisco AI Defense free-tier key for live escalation.
# If unset, the middleware silently uses the AI Defense mock client.
export SPLUNKGATE_AI_DEFENSE_API_KEY=ai-def-...
```

## Run

```bash
uv run python examples/support_agent.py
```

The demo asks the agent to summarise a fabricated customer record that
includes the last four PAN digits. With `profile="financial_services"`
the post-inference scan emits a BLOCK verdict on the PCI rule and the
`agent.invoke_with_data(...)` call raises
`ModelOutputBlockedBySplunkGate` — exactly the "show me the verdict in
Splunk" moment the README walks through.

## The wedge — three lines

```python
from splunkgate_mw import SafetyAgentMiddleware
agent = Agent(model=model, system_prompt=..., service=service,
              middleware=[SafetyAgentMiddleware(profile="financial_services")])
```

Add the model / tool / subagent layers when you want them; one profile
string flows through all four.

## Switching profiles

```python
profile = "healthcare"      # PHI emphasis (HIPAA Safe-Harbor)
profile = "public_sector"   # PII + Code Detection + content-class
profile = "default"         # balanced
```

`resolve_profile("nonsense")` raises `splunkgate_core.errors.UnknownProfile`
so typos surface at construction time, not at runtime.
