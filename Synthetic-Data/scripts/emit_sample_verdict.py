r"""Synthetic Verdict emitter for SplunkGate dashboards + vision loop.

# §14 CARVE-OUT: synthetic fixture generator for demo + vision-loop.
# Not a production telemetry path. The production path is
# splunkgate_mw → splunkgate_core/otel.py → splunklib HEC export.

Produces N realistic `Verdict` events shaped as Splunk HEC payloads under
sourcetype `cisco_ai_defense:splunkgate_verdict`. The 3 Dashboard Studio v2
dashboards render with non-empty data after this script runs. story-app-10's
vision-loop also consumes the resulting event stream as anchor data.

CLI:
    python Synthetic-Data/scripts/emit_sample_verdict.py \
        --count 500 \
        --hec-url $SPLUNKGATE_SPLUNK_HEC_URL \
        --hec-token $SPLUNKGATE_SPLUNK_HEC_TOKEN

`--dry-run` writes events to stdout as JSON (one per line). Determinism:
same `--seed` + `--count` produces byte-identical stdout (load-bearing for
the vision-loop anchor capture).

Per docs/architecture.md Hard Rule 6, no real Splunk credentials are baked
into this script — tokens come from CLI flags or env vars.

Exit codes:
    0 — success
    1 — invalid argument or live mode without HEC creds
    2 — HEC POST failed after 3 retries
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

# Verbatim Cisco AI Defense rule names per
# ../../context/07-cisco-stack/01-ai-defense-deep.md §7. ADR-001 — do not
# alter casing / ampersands / spacing.
RULES = (
    "Code Detection",
    "Harassment",
    "Hate Speech",
    "PCI",
    "PHI",
    "PII",
    "Profanity",
    "Prompt Injection",
    "Sexual Content & Exploitation",
    "Social Division & Polarization",
    "Violence & Public Safety Threats",
)

SURFACES = (
    "mw_model",
    "mw_tool",
    "mw_subagent",
    "mcp_score",
    "mcp_judge_tool",
    "mcp_check_output",
    "mcp_audit",
    "defenseclaw",
)

VERDICT_LABELS = ("ALLOW", "BLOCK", "MODIFY", "REVIEW")
SEVERITIES = ("NONE_SEVERITY", "LOW", "MEDIUM", "HIGH")

# Target distribution per BDD spec: ~70% ALLOW, ~15% BLOCK, ~10% MODIFY, ~5% REVIEW.
_LABEL_WEIGHTS = (0.70, 0.15, 0.10, 0.05)

# Severity correlates with label — ALLOW skews NONE_SEVERITY/LOW, BLOCK skews HIGH.
_SEVERITY_BY_LABEL: dict[str, tuple[float, float, float, float]] = {
    "ALLOW": (0.85, 0.10, 0.04, 0.01),
    "BLOCK": (0.0, 0.05, 0.20, 0.75),
    "MODIFY": (0.0, 0.10, 0.55, 0.35),
    "REVIEW": (0.0, 0.30, 0.50, 0.20),
}

_SOURCETYPE = "cisco_ai_defense:splunkgate_verdict"
_SOURCE = "splunkgate-synthetic"
_DEFAULT_SEED = 20260603
_HEC_TIMEOUT_S = 10.0
_HEC_MAX_RETRIES = 3


@dataclass(frozen=True)
class Args:
    """Parsed CLI args, frozen for clarity."""

    count: int
    hec_url: str | None
    hec_token: str | None
    index: str
    seed: int
    dry_run: bool


def parse_args(argv: list[str] | None = None) -> Args:
    """Parse CLI args; env vars override-fallback for HEC creds."""
    p = argparse.ArgumentParser(
        prog="emit_sample_verdict",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--count", type=int, default=500, help="Number of events to emit.")
    p.add_argument(
        "--hec-url",
        default=os.environ.get("SPLUNKGATE_SPLUNK_HEC_URL"),
        help="Splunk HEC base URL (e.g. https://host:8088). Env: SPLUNKGATE_SPLUNK_HEC_URL.",
    )
    p.add_argument(
        "--hec-token",
        default=os.environ.get("SPLUNKGATE_SPLUNK_HEC_TOKEN"),
        help="Splunk HEC token. Env: SPLUNKGATE_SPLUNK_HEC_TOKEN.",
    )
    p.add_argument("--index", default="main", help="Splunk index to write to.")
    p.add_argument(
        "--seed",
        type=int,
        default=_DEFAULT_SEED,
        help="RNG seed; load-bearing for the vision loop.",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Print JSON events to stdout instead of POSTing."
    )
    ns = p.parse_args(argv)
    if ns.count < 1:
        p.error("--count must be >= 1")
    return Args(
        count=ns.count,
        hec_url=ns.hec_url,
        hec_token=ns.hec_token,
        index=ns.index,
        seed=ns.seed,
        dry_run=ns.dry_run,
    )


def _weighted_choice(
    rng: random.Random, values: tuple[str, ...], weights: tuple[float, ...]
) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


def _pick_rules(rng: random.Random, label: str) -> list[dict[str, Any]]:
    """Pick rules consistent with the verdict label.

    ALLOW events fire 0-1 rule (mostly 0 — clean inputs); BLOCK/MODIFY/REVIEW
    fire 1-3. Confidence skews high for BLOCK, moderate for MODIFY/REVIEW.
    """
    if label == "ALLOW":
        count = 0 if rng.random() < 0.75 else 1
    elif label == "BLOCK":
        count = rng.choices([1, 2, 3], weights=[0.55, 0.30, 0.15])[0]
    else:
        count = rng.choices([1, 2], weights=[0.70, 0.30])[0]
    if count == 0:
        return []
    rule_names = rng.sample(RULES, k=min(count, len(RULES)))
    base_conf = 0.92 if label == "BLOCK" else 0.78
    return [
        {
            "rule": name,
            "confidence": round(rng.uniform(base_conf - 0.15, base_conf + 0.06), 3),
            "source": rng.choice(("ai_defense", "defenseclaw_regex", "splunklib_security")),
        }
        for name in rule_names
    ]


def _agent_id(rng: random.Random) -> str:
    """A deterministic but varied set of agent IDs so dashboards have group-by data."""
    pool = (
        "support-agent",
        "billing-agent",
        "researcher",
        "summarizer",
        "kyc-bot",
        "ops-copilot",
        "claims-agent",
        "discharge-summary-bot",
        "compliance-reviewer",
    )
    return rng.choice(pool)


def _model_name(rng: random.Random) -> str:
    return rng.choice(
        (
            "claude-sonnet-4-6",
            "gpt-5-mini",
            "gemini-2.5-flash",
            "llama-3.1-70b-instruct",
            "foundation-sec-1.1-8b-instruct",
        )
    )


def _jurisdictional_tag(rng: random.Random) -> str:
    return rng.choice(("FSI", "HIPAA", "PCI", "PUBSEC", "DEFAULT"))


def _synthesize_verdict(
    rng: random.Random, now_anchor: datetime, idx: int
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build one verdict event payload + sidecar fields.

    Returns (verdict_dict, aux_fields). The verdict_dict is canonical
    splunkgate_core.verdict.Verdict shape (Verdict(extra="forbid") accepts
    it without ValidationError). The aux_fields live on the HEC envelope's
    `fields` block per Splunk HEC spec — Splunk indexes them as flat fields
    without polluting the canonical Verdict schema.
    """
    label = _weighted_choice(rng, VERDICT_LABELS, _LABEL_WEIGHTS)
    severity = _weighted_choice(rng, SEVERITIES, _SEVERITY_BY_LABEL[label])
    surface = SURFACES[idx % len(SURFACES)]
    # Jitter timestamps across the last 24h so dashboards show a time series.
    ts_jitter_s = rng.uniform(0, 86400)
    ts = now_anchor - timedelta(seconds=ts_jitter_s)
    rules = _pick_rules(rng, label)
    # Latency log-normal around 120 ms; clamp to a sensible range.
    latency_ms = round(max(8.0, min(2500.0, rng.lognormvariate(4.78, 0.55))), 2)
    modifications: dict[str, object] | None = None
    if label == "MODIFY":
        modifications = {"redacted_text": "[REDACTED]"}
    verdict_payload = {
        # version=4 sets the RFC 4122 version nibble — Pydantic UUID4 fields
        # downstream may someday tighten the validator.
        "trace_id": str(UUID(int=rng.getrandbits(128), version=4)),
        "timestamp": ts.isoformat(),
        "verdict": label,
        "severity": severity,
        "rules": rules,
        "explanation": _explanation(label, severity, rules),
        "classifications": [],
        "modifications": modifications,
        "surface": surface,
        "latency_ms": latency_ms,
        "agent_id": _agent_id(rng),
    }
    aux_fields = {
        "model_name": _model_name(rng),
        "jurisdictional_tag": _jurisdictional_tag(rng),
        # Token cost — what the LLM inference WOULD have used.
        # For BLOCK verdicts, dashboards aggregate this as "tokens saved"
        # (the interception prevented the inference). For ALLOW, it's the
        # actual model spend. Borrowed from TruongSinhAI/splunk-token-optimizer
        # — token-progressive-disclosure pattern as a dashboard narrative.
        "tokens_used": str(_tokens_used(rng)),
    }
    return verdict_payload, aux_fields


def _tokens_used(rng: random.Random) -> int:
    """Log-normal token count, clamped to a sensible chat-LLM range."""
    raw = rng.lognormvariate(6.6, 0.65)
    return int(max(80, min(8000, raw)))


def _explanation(label: str, severity: str, rules: list[dict[str, Any]]) -> str:
    if not rules:
        return f"{label} (severity {severity}): no rules fired; input deemed safe."
    body = ", ".join(f"{r['rule']} [{r['source']}]" for r in rules)
    return f"{label} (severity {severity}): {body}."


def _wrap_for_hec(
    verdict: dict[str, Any], aux_fields: dict[str, str], index: str
) -> dict[str, Any]:
    """Wrap a Verdict in a Splunk HEC envelope per docs/architecture.md ADR-005.

    Aux metadata (model_name, jurisdictional_tag) lives in the HEC `fields`
    sibling block — Splunk's native pattern for indexed metadata that should
    NOT pollute the canonical event payload. `Verdict(extra="forbid")` would
    otherwise raise ValidationError for any consumer that round-trips the
    envelope's `event` through the Pydantic model.

    The `time` field is omitted intentionally — Splunk falls back to the HEC
    receive-time, so demo dashboards filtered to "Last 24h" show data
    immediately. The verdict.timestamp inside the event payload preserves
    the deterministic anchor for vision-loop anchor capture.
    """
    return {
        "sourcetype": _SOURCETYPE,
        "source": _SOURCE,
        "index": index,
        "event": verdict,
        "fields": aux_fields,
    }


def _post_to_hec(
    client: httpx.Client, hec_url: str, hec_token: str, batch: list[dict[str, Any]]
) -> None:
    """POST a batch of envelopes to Splunk HEC, retrying on 5xx / connection errors.

    Splunk HEC accepts concatenated JSON objects (no array wrapper) so we
    join with newlines.
    """
    body = "\n".join(json.dumps(env) for env in batch)
    url = f"{hec_url.rstrip('/')}/services/collector/event"
    headers = {"Authorization": f"Splunk {hec_token}"}
    last_exc: BaseException | None = None
    for attempt in range(_HEC_MAX_RETRIES):
        try:
            resp = client.post(url, content=body, headers=headers, timeout=_HEC_TIMEOUT_S)
            if 200 <= resp.status_code < 300:
                return
            if 500 <= resp.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"HEC {resp.status_code}", request=resp.request, response=resp
                )
            else:
                resp.raise_for_status()
        except (httpx.HTTPError, httpx.ConnectError) as e:
            last_exc = e
        time.sleep(0.5 * (2**attempt))
    msg = f"HEC POST failed after {_HEC_MAX_RETRIES} retries: {last_exc}"
    raise RuntimeError(msg)


def emit(args: Args) -> int:
    """Generate `args.count` verdicts and either print or POST them."""
    rng = random.Random(args.seed)  # noqa: S311 — synthesis only, deterministic by design
    now_anchor = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    pairs = [_synthesize_verdict(rng, now_anchor, i) for i in range(args.count)]
    envelopes = [_wrap_for_hec(v, aux, args.index) for v, aux in pairs]
    if args.dry_run:
        for env in envelopes:
            sys.stdout.write(json.dumps(env, sort_keys=True) + "\n")
        return 0
    if not args.hec_url or not args.hec_token:
        sys.stderr.write(
            "live mode requires --hec-url + --hec-token (or env "
            "SPLUNKGATE_SPLUNK_HEC_URL + SPLUNKGATE_SPLUNK_HEC_TOKEN)\n"
        )
        return 1
    # Batch by 100 to stay within HEC payload-size limits.
    with httpx.Client(verify=True) as client:
        for i in range(0, len(envelopes), 100):
            batch = envelopes[i : i + 100]
            try:
                _post_to_hec(client, args.hec_url, args.hec_token, batch)
            except RuntimeError as e:
                sys.stderr.write(f"{e}\n")
                return 2
            sys.stderr.write(f"emitted {min(i + 100, len(envelopes))}/{len(envelopes)}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        # argparse exits 2 on bad args; remap to 1 per the BDD contract.
        return 1 if exc.code != 0 else 0
    return emit(args)


if __name__ == "__main__":
    sys.exit(main())
