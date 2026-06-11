r"""Parse the vendored DefenseClaw `rules.go` into Python regex patterns.

Reads `inspiration/defenseclaw/internal/gateway/rules.go`, extracts each
PatternRule struct literal via a Go-source-aware regex, and compiles
every pattern with Python `re`. Patterns that fail to compile under
Python `re` (Go's RE2 has a few syntax-only incompatibilities — e.g.
`\\x{...}` escapes) are skipped with a debug log so the loader is total.

Cached at module load — first import takes ~50 ms; downstream loaders
hit a zero-cost lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

import structlog
from splunkgate_core.errors import DefenseclawRulesMissingError

__all__ = ["DEFAULT_RULES_PATH", "DefenseClawRule", "load_defenseclaw_rules"]

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]
DEFAULT_RULES_PATH: Final[Path] = (
    _REPO_ROOT / "inspiration" / "defenseclaw" / "internal" / "gateway" / "rules.go"
)

_logger = structlog.get_logger(__name__)

# Capture: { ID: "<id>", Pattern: regexp.MustCompile(`<pattern>`),
#            Title: "<title>", Severity: "<sev>", Confidence: <num>, Tags: [...] }
_RULE_RE = re.compile(
    r'\{\s*ID:\s*"(?P<id>[^"]+)",\s*'
    r"Pattern:\s*regexp\.MustCompile\(`(?P<pattern>[^`]+)`\),\s*"
    r'Title:\s*"(?P<title>[^"]+)",\s*'
    r'Severity:\s*"(?P<severity>[A-Z_]+)",\s*'
    r"Confidence:\s*(?P<confidence>[0-9.]+),\s*"
    r"Tags:\s*\[\]string\{(?P<tags>[^}]*)\}",
    re.DOTALL,
)


@dataclass(frozen=True)
class DefenseClawRule:
    """One DefenseClaw rule with its compiled Python regex."""

    rule_id: str
    title: str
    severity: str
    confidence: float
    tags: tuple[str, ...]
    pattern: re.Pattern[str]


def _parse_tags(raw: str) -> tuple[str, ...]:
    """Parse Go-source `"tag1", "tag2"` into a Python tuple."""
    return tuple(re.findall(r'"([^"]+)"', raw))


@lru_cache(maxsize=1)
def load_defenseclaw_rules(*, rules_path: Path | None = None) -> tuple[DefenseClawRule, ...]:
    """Parse rules.go into a tuple of compiled DefenseClawRule entries (cached)."""
    path = rules_path if rules_path is not None else DEFAULT_RULES_PATH
    if not path.exists():
        raise DefenseclawRulesMissingError(str(path))

    text = path.read_text(encoding="utf-8")
    rules: list[DefenseClawRule] = []
    for match in _RULE_RE.finditer(text):
        pattern_src = match["pattern"]
        try:
            compiled = re.compile(pattern_src)
        except re.error as exc:
            _logger.debug(
                "defenseclaw.regex_skip",
                rule_id=match["id"],
                error=str(exc),
                pattern_prefix=pattern_src[:60],
            )
            continue
        rules.append(
            DefenseClawRule(
                rule_id=match["id"],
                title=match["title"],
                severity=match["severity"],
                confidence=float(match["confidence"]),
                tags=_parse_tags(match["tags"]),
                pattern=compiled,
            )
        )
    return tuple(rules)
