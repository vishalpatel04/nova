"""Typed tool extension points — no dangerous execution in Slice 1."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolCategory(StrEnum):
    ORCHESTRATION = "orchestration"
    STATUS = "status"
    DELEGATION = "delegation"
    CODE = "code"
    SHELL = "shell"
    GIT = "git"
    FILESYSTEM = "filesystem"
    EMAIL = "email"
    CALENDAR = "calendar"
    TASKS = "tasks"
    RESEARCH = "research"
    WEB = "web"
    PLANNING = "planning"
    DESIGN = "design"
    SLIDES = "slides"
    CONTENT = "content"
    SEARCH = "search"
    MEMORY = "memory"
    REVIEW = "review"
    APPROVAL = "approval"
    AUDIT = "audit"


@dataclass
class ToolResult:
    success: bool
    output: Any = None
    error: str | None = None
    evidence_badge: str = "unverified"


class BaseTool(ABC):
    name: str
    category: ToolCategory
    requires_approval: bool = False
    enabled: bool = False  # Slice 1: all dangerous tools disabled

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult: ...


class ShellTool(BaseTool):
    name = "shell"
    category = ToolCategory.SHELL
    requires_approval = True
    enabled = False

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=False, error="Shell execution not enabled in Foundation Slice 1")


class FilesystemTool(BaseTool):
    name = "filesystem"
    category = ToolCategory.FILESYSTEM
    requires_approval = False
    enabled = False

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=False, error="Filesystem tools not enabled in Foundation Slice 1")


class RipgrepTool(BaseTool):
    name = "ripgrep"
    category = ToolCategory.SEARCH
    requires_approval = False
    enabled = False

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=False, error="Ripgrep not enabled in Foundation Slice 1")


class DesktopAutomationTool(BaseTool):
    name = "desktop_automation"
    category = ToolCategory.SHELL
    requires_approval = True
    enabled = False

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=False, error="Desktop automation not enabled in Foundation Slice 1"
        )


TOOL_REGISTRY: dict[str, type[BaseTool]] = {
    "shell": ShellTool,
    "filesystem": FilesystemTool,
    "ripgrep": RipgrepTool,
    "desktop_automation": DesktopAutomationTool,
}
