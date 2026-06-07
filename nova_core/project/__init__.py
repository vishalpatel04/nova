"""Active project context and repo inspection."""

from nova_core.project.context import ProjectRootValidation, validate_project_root
from nova_core.project.inspect import (
    RepoInspection,
    format_inspection,
    inspect_repo,
    normalize_git_branch,
)

__all__ = [
    "ProjectRootValidation",
    "RepoInspection",
    "format_inspection",
    "inspect_repo",
    "normalize_git_branch",
    "validate_project_root",
]
