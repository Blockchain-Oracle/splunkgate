"""SplunkGate eval harness — JailbreakBench, AdvBench, synthetic prompt-injection datasets."""

from splunkgate_core.errors import AdvBenchSubmoduleMissingError

from splunkgate_eval.advbench import load_advbench
from splunkgate_eval.baselines import (
    BASELINES,
    ai_defense_alone,
    defenseclaw_regex_only,
    gpt_oss_120b_judge,
)
from splunkgate_eval.imprompter import IMPRoMPTER_PAPER_CITATION, load_imprompter
from splunkgate_eval.jailbreakbench import load_jailbreakbench
from splunkgate_eval.synthetic import (
    EvalPrompt,
    load_benign_control,
    load_multi_turn_injection,
    load_tool_call_abuse,
)

__all__ = [
    "BASELINES",
    "AdvBenchSubmoduleMissingError",
    "EvalPrompt",
    "IMPRoMPTER_PAPER_CITATION",
    "ai_defense_alone",
    "defenseclaw_regex_only",
    "gpt_oss_120b_judge",
    "load_advbench",
    "load_benign_control",
    "load_imprompter",
    "load_jailbreakbench",
    "load_multi_turn_injection",
    "load_tool_call_abuse",
]
