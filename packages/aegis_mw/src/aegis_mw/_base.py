"""Base middleware mixin + four stub middleware classes for splunklib.ai.

Each class subclasses splunklib.ai.middleware.AgentMiddleware and overrides
exactly ONE of the four wrap-point methods (tool/model/subagent/agent). The
stub implementations delegate to `await handler(request)` unchanged — real
risk-scoring logic lands in stories mw-02 through mw-06.

Per ../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md, the
public splunklib.ai 3.0.0 contract is FOUR distinct middleware methods,
NOT a 2x2 before/after matrix.
"""

from typing import TYPE_CHECKING

import structlog
from splunklib.ai.middleware import (
    AgentMiddleware,
    AgentRequest,
    ModelRequest,
    ModelResponse,
    SubagentRequest,
    SubagentResponse,
    ToolRequest,
    ToolResponse,
)

from aegis_mw.config import Config
from aegis_mw.profiles import Profile

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from splunklib.ai.messages import AgentResponse

__all__ = [
    "SafetyAgentMiddleware",
    "SafetyModelMiddleware",
    "SafetySubagentMiddleware",
    "SafetyToolMiddleware",
]


class _SafetyMiddlewareBase(AgentMiddleware):  # type: ignore[misc]  # splunklib has no py.typed
    """Shared init for every Aegis middleware class.

    Subclasses override exactly ONE of tool_middleware / model_middleware /
    subagent_middleware / agent_middleware. The constructor stores config,
    profile, and a bound logger; subclasses use `self._logger` and
    `self._config` from inside their override.
    """

    def __init__(
        self,
        *,
        profile: str | Profile = "default",
        config: Config | None = None,
    ) -> None:
        """Wire shared config + profile + structlog binder."""
        self._config: Config = config if config is not None else Config()
        if isinstance(profile, Profile):
            self._profile = profile
        else:
            # Story-mw-07 will resolve named profiles via a registry. For now
            # any string label maps to the default profile shape.
            self._profile = Profile(name=profile, description="resolved at mw-07")
        self._logger = structlog.get_logger(self.__class__.__name__).bind(
            profile=self._profile.name,
        )


class SafetyToolMiddleware(_SafetyMiddlewareBase):
    """Aegis safety wrap for tool calls.

    Stub: delegates to `await handler(request)`. Real risk scoring (DefenseClaw
    regex pack against tool args) lands in story-mw-02.
    """

    async def tool_middleware(
        self,
        request: ToolRequest,
        handler: "Callable[[ToolRequest], Awaitable[ToolResponse]]",
    ) -> ToolResponse:
        """Pass-through stub; real logic in story-mw-02."""
        return await handler(request)


class SafetyModelMiddleware(_SafetyMiddlewareBase):
    """Aegis safety wrap for model invocations.

    Stub: delegates to `await handler(request)`. Real risk scoring (AI Defense
    Prompt Injection pre-inference + PII post-inference) lands in stories
    mw-03 and mw-04.
    """

    async def model_middleware(
        self,
        request: ModelRequest,
        handler: "Callable[[ModelRequest], Awaitable[ModelResponse]]",
    ) -> ModelResponse:
        """Pass-through stub; real logic in stories mw-03 and mw-04."""
        return await handler(request)


class SafetySubagentMiddleware(_SafetyMiddlewareBase):
    """Aegis safety wrap for subagent handoffs.

    Stub: delegates to `await handler(request)`. Real risk scoring (handoff
    payload inspection) lands in story-mw-05.
    """

    async def subagent_middleware(
        self,
        request: SubagentRequest,
        handler: "Callable[[SubagentRequest], Awaitable[SubagentResponse]]",
    ) -> SubagentResponse:
        """Pass-through stub; real logic in story-mw-05."""
        return await handler(request)


class SafetyAgentMiddleware(_SafetyMiddlewareBase):
    """Aegis safety wrap at the agent-request boundary.

    Stub: delegates to `await handler(request)`. Real trace correlation +
    request-level verdict emission lands in story-mw-06.
    """

    async def agent_middleware(
        self,
        request: AgentRequest,
        handler: "Callable[[AgentRequest], Awaitable[AgentResponse[object]]]",
    ) -> "AgentResponse[object]":
        """Pass-through stub; real logic in story-mw-06."""
        return await handler(request)
