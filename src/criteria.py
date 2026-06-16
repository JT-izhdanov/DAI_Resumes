"""Load and validate role rubrics.

A role's criteria live in ``roles/<role>/role.yaml``. A role may ``extends`` a
reusable template in ``templates/<name>.yaml`` so that a seniority ladder
(Associate → Principal) shares one rubric and only overrides the experience bar
and weights. A role may also point at a job description, which is loaded and fed
to the scorer as additional context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from . import config

# Recognized seniority levels, lowest to highest. ``None`` means unspecified.
SENIORITY_LEVELS = ["associate", "mid", "senior", "principal"]


class Criterion(BaseModel):
    """A single weighted criterion in a rubric."""

    id: str
    name: str
    weight: float = Field(gt=0)
    guidance: str = ""


class Rubric(BaseModel):
    """A role's scoring rubric, after template resolution."""

    role: str
    title: str
    family: Optional[str] = None
    seniority: Optional[str] = None
    description: str = ""
    scale: Dict[int, str]
    criteria: List[Criterion]
    must_haves: List[str] = []

    # Populated after load from the role's job_description file (not in YAML body).
    jd_text: Optional[str] = None

    @field_validator("seniority")
    @classmethod
    def _known_seniority(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SENIORITY_LEVELS:
            raise ValueError(
                f"seniority '{v}' must be one of {SENIORITY_LEVELS} or omitted"
            )
        return v

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


# ---- Raw loading + template resolution ---------------------------------------


def _merge(base: dict, child: dict) -> dict:
    """Overlay ``child`` onto ``base``.

    Scalars and dict fields (e.g. ``scale``) are replaced wholesale by the child
    when present. ``criteria`` are merged by ``id``: a child entry patches the
    matching base entry (so a child can set just ``weight``), and new ids are
    appended in child order.
    """
    merged = dict(base)
    base_criteria = {c["id"]: dict(c) for c in base.get("criteria", [])}
    order = [c["id"] for c in base.get("criteria", [])]

    for key, value in child.items():
        if key == "criteria":
            for entry in value:
                cid = entry["id"]
                if cid in base_criteria:
                    base_criteria[cid].update(entry)
                else:
                    base_criteria[cid] = dict(entry)
                    order.append(cid)
        else:
            merged[key] = value

    if base_criteria:
        merged["criteria"] = [base_criteria[cid] for cid in order]
    return merged


def _resolve_template(name: str, _seen: Optional[set] = None) -> dict:
    """Resolve a template's ``extends`` chain (templates only) into a dict.

    ``extends`` always refers to a template in ``templates/``; a template may in
    turn extend another template.
    """
    _seen = _seen if _seen is not None else set()
    if name in _seen:
        raise ValueError(f"Circular 'extends' detected involving '{name}'.")
    _seen.add(name)

    path = config.template_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"'extends: {name}' refers to a template, but {path} does not exist. "
            f"Available templates: {available_templates()}"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parent = raw.get("extends")
    raw = {k: v for k, v in raw.items() if k != "extends"}
    if not parent:
        return raw
    return _merge(_resolve_template(parent, _seen), raw)


def load_rubric(role: str) -> Rubric:
    """Load and validate the fully-resolved rubric for a role."""
    spec_path = config.role_spec_path(role)
    if not spec_path.exists():
        raise FileNotFoundError(
            f"No rubric for role '{role}'. Expected: {spec_path}"
        )
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    parent = raw.get("extends")
    child = {k: v for k, v in raw.items() if k != "extends"}
    data = _merge(_resolve_template(parent), child) if parent else child
    data.setdefault("role", role)
    rubric = Rubric.model_validate(data)
    rubric.jd_text = _load_job_description(role, data.get("job_description_file"))
    return rubric


def _load_job_description(role: str, filename: Optional[str]) -> Optional[str]:
    if not filename:
        # Fall back to a conventional job_description.md if present.
        default = config.role_dir(role) / "job_description.md"
        if default.exists():
            text = default.read_text(encoding="utf-8").strip()
            return text or None
        return None
    path = config.role_dir(role) / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Role '{role}' references job description '{filename}' but {path} "
            f"does not exist."
        )
    return path.read_text(encoding="utf-8").strip() or None


# ---- Discovery ---------------------------------------------------------------


def available_roles() -> List[str]:
    """Roles that have a role.yaml, sorted alphabetically."""
    if not config.ROLES_DIR.exists():
        return []
    return sorted(
        p.name
        for p in config.ROLES_DIR.iterdir()
        if p.is_dir() and (p / config.ROLE_SPEC_FILENAME).exists()
    )


def available_templates() -> List[str]:
    """Reusable family templates, sorted alphabetically."""
    if not config.TEMPLATES_DIR.exists():
        return []
    return sorted(p.stem for p in config.TEMPLATES_DIR.glob("*.yaml"))


def is_role(name: str) -> bool:
    return config.role_spec_path(name).exists()
