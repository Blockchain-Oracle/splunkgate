"""SplunkGate safety profiles — stub.

Full FSI / HIPAA / PubSec profile registry lands in story-mw-07. This
story ships only the `default` profile so downstream stories can wire
the kwarg without breaking the API later.
"""

from dataclasses import dataclass

__all__ = ["DEFAULT_PROFILE", "Profile"]


@dataclass(frozen=True)
class Profile:
    """Safety profile — name + description.

    The actual rule weighting per profile is wired in story-mw-07.
    """

    name: str
    description: str


DEFAULT_PROFILE = Profile(
    name="default",
    description="Balanced safety defaults; no domain-specific tuning.",
)
