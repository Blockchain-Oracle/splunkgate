"""SplunkGate eval harness — JailbreakBench, AdvBench, synthetic prompt-injection datasets."""

from splunkgate_core.errors import AdvBenchSubmoduleMissingError

from splunkgate_eval.advbench import load_advbench
from splunkgate_eval.jailbreakbench import load_jailbreakbench
from splunkgate_eval.synthetic import (
    EvalPrompt,
    load_benign_control,
    load_multi_turn_injection,
    load_tool_call_abuse,
)

__all__ = [
    "AdvBenchSubmoduleMissingError",
    "EvalPrompt",
    "load_advbench",
    "load_benign_control",
    "load_jailbreakbench",
    "load_multi_turn_injection",
    "load_tool_call_abuse",
]
