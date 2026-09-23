"""Tools the agent can call, and the uniform result of a call."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class Tool:
    """A named capability. ``read_only=False`` or ``requires_approval=True`` means it never runs unapproved."""

    name: str
    description: str
    fn: Callable[..., Any]
    read_only: bool = True
    requires_approval: bool = False

    @property
    def gated(self) -> bool:
        return self.requires_approval or not self.read_only


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    status: Literal["done", "pending_approval", "failed"]
    data: Any = None
    error: str | None = None


class ToolError(Exception):
    """Raised by a tool function to report a failure the caller should see as ``ToolResult.error``."""
