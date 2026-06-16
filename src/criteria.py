"""Load and validate role rubrics from criteria/<role>.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field, field_validator

from . import config


class Criterion(BaseModel):
    """A single weighted criterion in a rubric."""

    id: str
    name: str
    weight: float = Field(gt=0)
    guidance: str = ""


class Rubric(BaseModel):
    """A role's scoring rubric, loaded from YAML."""

    role: str
    title: str
    description: str = ""
    scale: Dict[int, str]
    criteria: List[Criterion]
    must_haves: List[str] = []

    @field_validator("criteria")
    @classmethod
    def _non_empty(cls, v: List[Criterion]) -> List[Criterion]:
        if not v:
            raise ValueError("rubric must define at least one criterion")
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("criterion ids must be unique")
        return v

    def normalized_weights(self) -> Dict[str, float]:
        """Criterion weights normalized to sum to 1.0."""
        total = sum(c.weight for c in self.criteria)
        return {c.id: c.weight / total for c in self.criteria}


def load_rubric(role: str) -> Rubric:
    """Load the rubric for a role, raising a clear error if it's missing."""
    path = config.role_criteria_path(role)
    if not path.exists():
        raise FileNotFoundError(
            f"No rubric for role '{role}'. Expected: {path}\n"
            f"Create it (copy an existing criteria/*.yaml as a template)."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Rubric.model_validate(data)


def available_roles() -> List[str]:
    """Roles that have a rubric file, sorted alphabetically."""
    if not config.CRITERIA_DIR.exists():
        return []
    return sorted(p.stem for p in config.CRITERIA_DIR.glob("*.yaml"))
