"""Cisco AI Defense Inspection API regional endpoint table.

Per ../../../context/07-cisco-stack/01-ai-defense-deep.md § 3:
- US, EU, AP are publicly documented
- FED (FedRAMP variant) is NOT in the public docs as of the 2026-06-02 audit;
  included here as opt-in following the documented hostname pattern.
- India region was NOT documented in the publicly-readable getting-started
  page; the gated SecurityDocs page may add it later.
"""

from typing import Final, Literal

Region = Literal["us", "eu", "ap", "fed"]

REGION_BASE_URLS: Final[dict[Region, str]] = {
    "us": "https://us.api.inspect.aidefense.security.cisco.com",
    "eu": "https://eu.api.inspect.aidefense.security.cisco.com",
    "ap": "https://ap.api.inspect.aidefense.security.cisco.com",
    "fed": "https://fed.api.inspect.aidefense.security.cisco.com",
}

INSPECT_CHAT_PATH: Final[str] = "/api/v1/inspect/chat"
