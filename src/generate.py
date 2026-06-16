"""Draft a role rubric from a job description using the Claude API.

Reads a JD, asks Claude to propose weighted criteria and must-haves, and writes
a starter ``roles/<role>/role.yaml`` (plus a copy of the JD) for you to edit.
This is a starting point, not a final rubric — review and tune the weights.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import anthropic
import yaml
from pydantic import BaseModel, Field

from . import config

DEFAULT_SCALE = {
    0: "No evidence / disqualifying",
    1: "Minimal — barely touches the criterion",
    2: "Below expectations",
    3: "Meets expectations",
    4: "Exceeds expectations",
    5: "Exceptional — clearly top-tier",
}


class DraftCriterion(BaseModel):
    id: str = Field(description="snake_case identifier, e.g. data_modeling")
    name: str
    weight: int = Field(ge=1, le=5, description="Relative importance, 1 (low)–5 (high).")
    guidance: str = Field(description="What evidence to look for in a résumé.")


class DraftRubric(BaseModel):
    title: str
    summary: str = Field(description="2–3 sentence description of the role.")
    criteria: List[DraftCriterion]
    must_haves: List[str] = Field(description="Hard-gate requirements.")


def draft_from_jd(
    role: str,
    jd_text: str,
    *,
    family: Optional[str] = None,
    seniority: Optional[str] = None,
    extends: Optional[str] = None,
) -> DraftRubric:
    """Ask Claude to propose a rubric for a role from its job description."""
    client = anthropic.Anthropic()
    level = f" The target seniority is '{seniority}'." if seniority else ""
    response = client.messages.parse(
        model=config.MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=(
            "You design hiring rubrics for a Data & AI team. Given a job "
            "description, propose 4–7 weighted, independently-scorable criteria "
            "and a short list of hard-gate must-haves. Criteria should be "
            "specific to the role's actual responsibilities and tools."
            + level
        ),
        messages=[
            {
                "role": "user",
                "content": f"Job description for '{role}':\n\n{jd_text}",
            }
        ],
        output_format=DraftRubric,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError("Could not draft a rubric from the job description.")
    return response.parsed_output


def write_role(
    role: str,
    draft: DraftRubric,
    jd_text: str,
    *,
    family: Optional[str] = None,
    seniority: Optional[str] = None,
    extends: Optional[str] = None,
    overwrite: bool = False,
) -> Path:
    """Write roles/<role>/role.yaml and job_description.md from a draft."""
    role_dir = config.role_dir(role)
    spec_path = config.role_spec_path(role)
    if spec_path.exists() and not overwrite:
        raise FileExistsError(
            f"{spec_path} already exists. Pass overwrite=True to replace it."
        )
    (role_dir / "resumes").mkdir(parents=True, exist_ok=True)

    body: dict = {"role": role, "title": draft.title}
    if family:
        body["family"] = family
    if seniority:
        body["seniority"] = seniority
    if extends:
        body["extends"] = extends
    body["description"] = draft.summary
    body["job_description_file"] = "job_description.md"
    # Inherit scale from the template when extending; otherwise include a default.
    if not extends:
        body["scale"] = DEFAULT_SCALE
    body["criteria"] = [c.model_dump() for c in draft.criteria]
    body["must_haves"] = draft.must_haves

    spec_path.write_text(
        "# Generated from a job description — review and tune before use.\n"
        + yaml.safe_dump(body, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (role_dir / "job_description.md").write_text(jd_text.strip() + "\n", encoding="utf-8")
    return spec_path
