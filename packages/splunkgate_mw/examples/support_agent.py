"""SplunkGate 30-line demo agent — see examples/README.md."""

from __future__ import annotations

import asyncio
import os

from splunkgate_mw import (
    SafetyAgentMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
)
from splunklib.ai import Agent, OpenAIModel
from splunklib.client import connect

PROFILE = "financial_services"

# fmt: off
# Hand-formatted to keep the demo body ≤ 30 lines per the story-mw-07
# BDD body-grep cap. ruff format expands the multi-arg calls below —
# `# fmt: off` keeps the headline wedge readable on one screen.


def build_agent() -> Agent[None]:
    """Construct the Agent with all 4 SplunkGate middleware applied."""
    service = connect(
        host=os.environ["SPLUNKGATE_SPLUNK_HOST"],
        port=int(os.environ.get("SPLUNKGATE_SPLUNK_PORT", "8089")),
        token=os.environ["SPLUNKGATE_SPLUNK_TOKEN"],
    )
    model = OpenAIModel(model="gpt-4o", api_key=os.environ["OPENAI_API_KEY"], base_url="https://api.openai.com/v1")
    return Agent(model=model, system_prompt="You are a Splunk support agent.", service=service, middleware=[
        SafetyAgentMiddleware(profile=PROFILE),
        SafetyModelMiddleware(profile=PROFILE),
        SafetySubagentMiddleware(profile=PROFILE),
        SafetyToolMiddleware(profile=PROFILE),
    ])


async def main() -> None:
    """Run a single demo invocation."""
    async with build_agent() as agent:
        response = await agent.invoke_with_data("Summarize this customer record.", {"name": "Jane Doe", "card_last4": "1234"})
        print(response)  # noqa: T201 — demo prints to stdout


if __name__ == "__main__":
    asyncio.run(main())
# fmt: on
