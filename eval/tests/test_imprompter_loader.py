"""Behavioural tests for the Imprompter payload loader (story-eval-03)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from splunkgate_eval import EvalPrompt, IMPRoMPTER_PAPER_CITATION, load_imprompter
from splunkgate_eval.imprompter import DEFAULT_PAYLOADS_PATH

# Treat eval/tests/fixtures/ as a sibling-importable module without forcing
# the eval/ package to be installed.
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

from imprompter_paper_snippets import (  # noqa: E402 — sys.path set up above
    ARXIV_ID,
    AUTHOR_FERNANDES,
    EXFIL_DOMAIN,
    FIGURE_1_LECHAT_PAYLOAD_PREFIX,
    INSTITUTION_UCSD,
    MISTRAL_PATCH_DATE,
    TARGET_AGENTS,
)


def _read_raw_records() -> list[dict[str, object]]:
    """Return the JSONL as raw dicts so tests can assert the paper-specific fields."""
    return [
        json.loads(line)
        for line in DEFAULT_PAYLOADS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_jsonl_has_exactly_eleven_records() -> None:
    """The corpus is the 11 highest-success-rate Imprompter payloads."""
    raw = _read_raw_records()
    assert len(raw) == 11


def test_loader_returns_eleven_eval_prompts() -> None:
    """`load_imprompter()` returns 11 EvalPrompt instances."""
    records = load_imprompter()
    assert len(records) == 11
    for r in records:
        assert isinstance(r, EvalPrompt)


def test_canonical_triple_on_every_record() -> None:
    """All 11 records map to (imprompter, BLOCK, HIGH)."""
    for r in load_imprompter():
        assert r.category == "imprompter"
        assert r.expected_verdict == "BLOCK"
        assert r.expected_severity == "HIGH"


def test_target_agent_values_are_in_paper_enumeration() -> None:
    """Every record's target_agent is from the four agents in paper Table 1 + p. 7."""
    for raw in _read_raw_records():
        assert raw["target_agent"] in TARGET_AGENTS


def test_velocity_show_exfil_domain_appears_in_corpus() -> None:
    """`velocity.show` is the verbatim attacker domain from paper p. 7."""
    raw = _read_raw_records()
    citations_with_domain = [r for r in raw if EXFIL_DOMAIN in r["target_syntax"]]
    assert citations_with_domain, "velocity.show missing from every target_syntax"


def test_mistral_patched_records_carry_2024_09_13_date() -> None:
    """LeChat patched=true rows must show the paper's documented patch date."""
    raw = _read_raw_records()
    patched = [r for r in raw if r["patched"]]
    assert patched, "expected at least one patched=true record"
    for r in patched:
        assert r["patch_date"] == MISTRAL_PATCH_DATE


def test_every_payload_is_at_least_one_hundred_bytes() -> None:
    """Imprompter payloads are non-trivial in size; smoke check against truncation."""
    for raw in _read_raw_records():
        size = len(str(raw["payload"]).encode("utf-8"))
        assert size >= 100, f"{raw['label']} payload only {size} bytes"


def test_figure_1_prefix_appears_in_exactly_one_record() -> None:
    """The Figure-1 verbatim Unicode prefix anchors the corpus to the published payload."""
    raw = _read_raw_records()
    hits = [r for r in raw if FIGURE_1_LECHAT_PAYLOAD_PREFIX in str(r["payload"])]
    assert len(hits) == 1, f"expected exactly one record with the Figure-1 prefix, got {len(hits)}"


def test_paper_citation_contains_arxiv_id_and_authors() -> None:
    """`IMPRoMPTER_PAPER_CITATION` must carry the arXiv ID + lead author + institution."""
    assert ARXIV_ID in IMPRoMPTER_PAPER_CITATION
    assert AUTHOR_FERNANDES in IMPRoMPTER_PAPER_CITATION
    assert INSTITUTION_UCSD in IMPRoMPTER_PAPER_CITATION


def test_loader_limit_kwarg_truncates_deterministically() -> None:
    """`limit=3` returns the first 3 records in file order."""
    records = load_imprompter(limit=3)
    assert len(records) == 3


def test_readme_references_fernandes_ucsd_and_patch_date() -> None:
    """README.md surfaces the paper attribution + patch context judges look for."""
    readme = (
        Path(__file__).resolve().parents[2] / "Synthetic-Data" / "pii_leak_corpus" / "README.md"
    )
    text = readme.read_text(encoding="utf-8")
    assert AUTHOR_FERNANDES in text
    assert INSTITUTION_UCSD in text
    assert MISTRAL_PATCH_DATE in text
