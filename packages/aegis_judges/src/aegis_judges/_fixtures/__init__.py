"""Loader for the AI Defense fixture matrix (11 rules x 4 severities)."""

import json
from importlib import resources
from typing import Final

from aegis_judges.ai_defense_types import InspectResponse

_MATRIX_JSON: Final[str] = "ai_defense_matrix.json"


def load_fixture_matrix() -> list[InspectResponse]:
    """Load the 44-row fixture matrix as a list of InspectResponse objects."""
    raw = (resources.files(__package__) / _MATRIX_JSON).read_text(encoding="utf-8")
    rows: list[dict[str, object]] = json.loads(raw)
    return [InspectResponse.model_validate(row) for row in rows]


def load_trigger_table() -> dict[str, int]:
    """Load the deterministic trigger-string → matrix-index table.

    Embedded in the JSON top-level under `_triggers`; falls back to {} if absent.
    """
    raw = (resources.files(__package__) / _MATRIX_JSON).read_text(encoding="utf-8")
    rows: list[dict[str, object]] = json.loads(raw)
    triggers: dict[str, int] = {}
    for idx, row in enumerate(rows):
        trigger = row.get("__trigger__")
        if isinstance(trigger, str):
            triggers[trigger] = idx
    return triggers
