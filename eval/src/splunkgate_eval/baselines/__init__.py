"""Three eval baselines: DefenseClaw regex-only, gpt-oss-120b judge, AI Defense alone."""

from collections.abc import Callable
from typing import Final

from splunkgate_core.verdict import Verdict

from splunkgate_eval.baselines.ai_defense_alone import ai_defense_alone
from splunkgate_eval.baselines.defenseclaw_regex_only import defenseclaw_regex_only
from splunkgate_eval.baselines.gpt_oss_120b_judge import gpt_oss_120b_judge
from splunkgate_eval.synthetic import EvalPrompt

__all__ = [
    "BASELINES",
    "ai_defense_alone",
    "defenseclaw_regex_only",
    "gpt_oss_120b_judge",
]

BASELINES: Final[dict[str, Callable[[EvalPrompt], Verdict]]] = {
    "defenseclaw_regex_only": defenseclaw_regex_only,
    "gpt_oss_120b_judge": gpt_oss_120b_judge,
    "ai_defense_alone": ai_defense_alone,
}
