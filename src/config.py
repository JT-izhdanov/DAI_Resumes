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

ROLES_DIR = ROOT / "roles"
TEMPLATES_DIR = ROOT / "templates"
RESULTS_DIR = ROOT / "results"

# Default model. Override with the DAI_MODEL env var.
# claude-opus-4-8 is Anthropic's most capable Opus-tier model.
MODEL = os.environ.get("DAI_MODEL", "claude-opus-4-8")

# File extensions we know how to parse.
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

# Name of the criteria file inside each role folder.
ROLE_SPEC_FILENAME = "role.yaml"


def role_dir(role: str) -> Path:
    """Folder for a role: criteria, job description, and its résumé pool."""
    return ROLES_DIR / role


def role_spec_path(role: str) -> Path:
    """Criteria/rubric file for a role."""
    return role_dir(role) / ROLE_SPEC_FILENAME


def role_resume_dir(role: str) -> Path:
    """Folder holding résumés submitted for a role."""
    return role_dir(role) / "resumes"


def template_path(name: str) -> Path:
    """A reusable family rubric in templates/."""
    return TEMPLATES_DIR / f"{name}.yaml"


def role_results_dir(role: str, label: str) -> Path:
    """Output folder for one assessment run (role + résumé-pool label)."""
    return RESULTS_DIR / role / label
