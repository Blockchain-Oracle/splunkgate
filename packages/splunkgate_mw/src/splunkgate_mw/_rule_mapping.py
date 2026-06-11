"""Map profile rule-name tuples → AI Defense `enabled_rules` list.

A `Profile` carries `rules_pre_inference`, `rules_post_inference`, and
`rules_tool_call` as `tuple[str, ...]`. Some entries (e.g. "Sensitive
Data") are supplied by the DefenseClaw rule pack and have no
counterpart in the 11-name canonical AI Defense Inspection rule list;
sending them to AI Defense would produce a 400 response.

`profile_rules_to_enabled_rules` filters down to the canonical set and
returns an `EnabledRule` list ready to drop into `InspectConfig`.
Non-canonical rule names are logged once per resolution at debug level
so operators can see which DefenseClaw-only rules a profile is asking
for that AI Defense won't enforce. The filtered list is what regulated-
industry deployments actually buy when they pick a profile.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from splunkgate_judges.ai_defense_types import AIDefenseRule, EnabledRule

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["profile_rules_to_enabled_rules"]

_logger = structlog.get_logger(__name__)
_CANONICAL: frozenset[str] = frozenset(r.value for r in AIDefenseRule)


def profile_rules_to_enabled_rules(
    rule_names: Iterable[str],
    *,
    profile_name: str,
    surface: str,
) -> list[EnabledRule]:
    """Convert a profile's rule-name tuple to AI Defense `EnabledRule` entries."""
    canonical: list[EnabledRule] = []
    dropped: list[str] = []
    for name in rule_names:
        if name in _CANONICAL:
            canonical.append(EnabledRule(rule_name=AIDefenseRule(name)))
        else:
            dropped.append(name)
    if dropped:
        _logger.debug(
            "profile_rules.non_canonical_dropped",
            profile=profile_name,
            surface=surface,
            dropped=dropped,
        )
    return canonical
