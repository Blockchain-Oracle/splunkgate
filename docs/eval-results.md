# SplunkGate eval results

> Rows marked `(mock)` ran against deterministic mock dispatchers — the underlying upstream call was NOT made. Do not interpret these rows as production benchmarks.

| Evaluator | Precision | Recall | F1 | ECE | p50 latency (ms) | p99 latency (ms) | $/1k verdicts |
|---|---|---|---|---|---|---|---|
| ai_defense_alone (mock) | 0.000 | 0.000 | 0.000 | 0.500 | 0.3 | 0.7 | $0.000 |
| defenseclaw_regex_only | 1.000 | 0.240 | 0.387 | 0.380 | 0.1 | 5.2 | $0.000 |


[^imprompter]: Per arxiv:2410.14923 (Fu et al., UCSD+NTU 2024), the
    Imprompter PII-exfil pattern was patched by Mistral on 2024-09-13 at
    the renderer layer (markdown-image rendering disabled). SplunkGate
    detects the payload pattern in LLM output for defense-in-depth, not
    as the sole defense.
[^msj]: Per Anthropic Many-Shot Jailbreaking — the power-law exponent
    is invariant to SFT/RL. We sit on the same probabilistic scaling
    curve. This is a probabilistic gate, not a deterministic one.
