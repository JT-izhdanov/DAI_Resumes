"""Paths and runtime settings for the scoring pipeline."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass

# Repository root (this file lives in <root>/src/config.py).
ROOT = Path(__file__).resolve().parent.parent

CRITERIA_DIR = ROOT / "criteria"
ROLES_DIR = ROOT / "roles"
RESULTS_DIR = ROOT / "results"

# Default model. Override with the DAI_MODEL env var.
# claude-opus-4-8 is Anthropic's most capable Opus-tier model.
MODEL = os.environ.get("DAI_MODEL", "claude-opus-4-8")

# File extensions we know how to parse.
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def role_resume_dir(role: str) -> Path:
    """Folder holding résumés for a role."""
    return ROLES_DIR / role / "resumes"


def role_criteria_path(role: str) -> Path:
    """Rubric YAML for a role."""
    return CRITERIA_DIR / f"{role}.yaml"


def role_results_dir(role: str) -> Path:
    """Output folder for a role's scores and ranking."""
    return RESULTS_DIR / role
