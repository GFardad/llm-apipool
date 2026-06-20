"""Base types for provider completion results."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompletionResult:
    """Result of a provider API completion call."""

    text: str
    tokens_used: int
    was_429: bool
    error: str | None = None
    remaining_requests: int | None = None
    rate_limit_headers: dict[str, Any] = field(default_factory=dict)
