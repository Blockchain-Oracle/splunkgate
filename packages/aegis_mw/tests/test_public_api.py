"""Public API contract tests for aegis_mw.

Tests gate (a) the four middleware classes are importable from the package
top-level, (b) each is a subclass of splunklib.ai.middleware.AgentMiddleware,
(c) Config and Profile construct, (d) the public surface (__all__) is
locked, and (e) each stub middleware delegates to the handler without
modifying the response.
"""

import aegis_mw
import pytest
from aegis_mw import (
    DEFAULT_PROFILE,
    Config,
    Profile,
    SafetyAgentMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
)
from pydantic import SecretStr
from splunklib.ai.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    SubagentRequest,
    SubagentResponse,
    ToolRequest,
    ToolResponse,
)

MIDDLEWARE_CLASSES = (
    SafetyToolMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyAgentMiddleware,
)


def test_all_four_middleware_classes_importable_from_top_level() -> None:
    """Each of the 4 middleware classes is reachable from `aegis_mw`."""
    for cls in MIDDLEWARE_CLASSES:
        assert cls.__module__.startswith("aegis_mw"), cls


def test_each_middleware_is_subclass_of_splunklib_ai_agent_middleware() -> None:
    """Public-API class hierarchy matches the splunklib.ai 3.0.0 contract."""
    for cls in MIDDLEWARE_CLASSES:
        assert issubclass(cls, AgentMiddleware), cls


def test_public_api_all_is_exactly_locked() -> None:
    """__all__ contract — extending requires intentional update."""
    assert sorted(aegis_mw.__all__) == [
        "Config",
        "DEFAULT_PROFILE",
        "Profile",
        "SafetyAgentMiddleware",
        "SafetyModelMiddleware",
        "SafetySubagentMiddleware",
        "SafetyToolMiddleware",
    ]


def test_aegis_mw_version_is_set() -> None:
    assert aegis_mw.__version__ == "0.1.0"


def test_profile_constructs_default() -> None:
    p = Profile(name="default", description="balanced")
    assert p.name == "default"
    assert p.description == "balanced"


def test_default_profile_singleton_present() -> None:
    assert isinstance(DEFAULT_PROFILE, Profile)
    assert DEFAULT_PROFILE.name == "default"


def test_config_constructs_with_defaults() -> None:
    cfg = Config()
    assert cfg.splunklib_security_first_pass is True
    assert cfg.foundation_sec_enabled is True
    assert cfg.escalate_on_first_pass_hit is True
    assert cfg.ai_defense_api_key is None
    assert cfg.ai_defense_endpoint.startswith("https://")


def test_config_accepts_secret_str_api_key() -> None:
    cfg = Config(ai_defense_api_key=SecretStr("synth-key-1234567890abcdef"))
    assert cfg.ai_defense_api_key is not None
    assert cfg.ai_defense_api_key.get_secret_value().startswith("synth-")


def test_config_rejects_unknown_field() -> None:
    """extra='forbid' catches typos at the boundary."""
    with pytest.raises(ValueError, match="extra_attr"):
        Config(extra_attr="nope")  # type: ignore[call-arg]


def test_config_is_frozen() -> None:
    """frozen=True — mutation should raise ValidationError."""
    cfg = Config()
    with pytest.raises((ValueError, AttributeError, TypeError)):
        cfg.foundation_sec_enabled = False  # type: ignore[misc]


def test_middleware_classes_construct_with_string_profile() -> None:
    """3-line integration shape: SafetyToolMiddleware(profile='financial_services')."""
    for cls in MIDDLEWARE_CLASSES:
        instance = cls(profile="financial_services")
        assert isinstance(instance, AgentMiddleware)


def test_middleware_classes_construct_with_profile_object() -> None:
    """Profile objects work too."""
    p = Profile(name="test", description="test profile")
    for cls in MIDDLEWARE_CLASSES:
        instance = cls(profile=p)
        assert isinstance(instance, AgentMiddleware)


def test_middleware_classes_construct_with_custom_config() -> None:
    """Custom Config kwarg works."""
    cfg = Config(foundation_sec_enabled=False)
    for cls in MIDDLEWARE_CLASSES:
        instance = cls(config=cfg)
        assert isinstance(instance, AgentMiddleware)


def test_middleware_kwargs_only() -> None:
    """profile + config must be keyword-only — positional should raise."""
    for cls in MIDDLEWARE_CLASSES:
        with pytest.raises(TypeError):
            cls("default")  # type: ignore[misc]


@pytest.mark.asyncio
async def test_tool_middleware_stub_delegates_to_handler() -> None:
    """Stub pass-through: handler return must propagate unchanged."""
    instance = SafetyToolMiddleware(profile="default")
    sentinel = object()

    async def handler(_request: ToolRequest) -> ToolResponse:
        return sentinel  # type: ignore[return-value]

    request = object()
    result = await instance.tool_middleware(request, handler)  # type: ignore[arg-type]
    assert result is sentinel


@pytest.mark.asyncio
async def test_model_middleware_stub_delegates_to_handler() -> None:
    instance = SafetyModelMiddleware(profile="default")
    sentinel = object()

    async def handler(_request: ModelRequest) -> ModelResponse:
        return sentinel  # type: ignore[return-value]

    result = await instance.model_middleware(object(), handler)  # type: ignore[arg-type]
    assert result is sentinel


@pytest.mark.asyncio
async def test_subagent_middleware_stub_delegates_to_handler() -> None:
    instance = SafetySubagentMiddleware(profile="default")
    sentinel = object()

    async def handler(_request: SubagentRequest) -> SubagentResponse:
        return sentinel  # type: ignore[return-value]

    result = await instance.subagent_middleware(object(), handler)  # type: ignore[arg-type]
    assert result is sentinel
