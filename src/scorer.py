"""Score a résumé against a role rubric using the Claude API.

Uses structured outputs (`client.messages.parse`) so the model returns a
validated, per-criterion breakdown rather than free text. The weighted total is
computed in code from the model's per-criterion scores — the math is ours, the
judgment is the model's.
"""

from __future__ import annotations

from typing import List, Literal

import anthropic
from pydantic import BaseModel, Field

from . import config
from .criteria import Rubric

# Reusable client. Reads ANTHROPIC_API_KEY from the environment.
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ---- Structured output schema -------------------------------------------------


class CriterionScore(BaseModel):
    """The model's assessment of one criterion."""

    criterion_id: str = Field(description="Matches an `id` from the rubric criteria.")
    score: int = Field(ge=0, le=5, description="0–5 score on the rubric scale.")
    justification: str = Field(
        description="One or two sentences citing evidence from the résumé."
    )


class MustHaveCheck(BaseModel):
    """Pass/fail/unknown verdict on a hard-gate requirement."""

    requirement: str
    verdict: Literal["pass", "fail", "unknown"]
    note: str = Field(description="Brief reason for the verdict.")


class ResumeAssessment(BaseModel):
    """The full structured assessment the model returns for one résumé."""

    candidate_name: str = Field(
        description="Candidate's name as it appears on the résumé, or 'Unknown'."
    )
    summary: str = Field(description="2–3 sentence overall summary of fit.")
    criterion_scores: List[CriterionScore]
    must_have_checks: List[MustHaveCheck]
    strengths: List[str] = Field(description="Key strengths for this role.")
    concerns: List[str] = Field(description="Gaps, risks, or missing information.")


# ---- Scored result (assessment + computed weighted total) --------------------


class ScoredResume(BaseModel):
    """An assessment plus the weighted total computed in code."""

    source_file: str
    role: str
    weighted_score: float = Field(description="0–5 weighted total.")
    passes_must_haves: bool
    assessment: ResumeAssessment


def _build_system_prompt(rubric: Rubric) -> str:
    scale_lines = "\n".join(f"  {k}: {v}" for k, v in sorted(rubric.scale.items()))
    criteria_lines = "\n".join(
        f"  - id: {c.id}\n    name: {c.name}\n    what to assess: {c.guidance.strip()}"
        for c in rubric.criteria
    )
    must_have_lines = (
        "\n".join(f"  - {m}" for m in rubric.must_haves)
        if rubric.must_haves
        else "  (none)"
    )
    return (
        f"You are an expert technical recruiter screening candidates for the "
        f"role of {rubric.title}.\n\n"
        f"Role description:\n{rubric.description.strip()}\n\n"
        f"Score each criterion on this 0–5 scale:\n{scale_lines}\n\n"
        f"Criteria to score (return one entry per id, using the exact id):\n"
        f"{criteria_lines}\n\n"
        f"Hard-gate requirements (judge pass/fail/unknown):\n{must_have_lines}\n\n"
        "Be evidence-based and calibrated. Only credit what the résumé actually "
        "shows; use 'unknown' for must-haves when the résumé is silent rather than "
        "assuming pass or fail. Do not invent experience that isn't stated."
    )


def score_resume(role: str, source_file: str, resume_text: str, rubric: Rubric) -> ScoredResume:
    """Score a single résumé's text against the rubric."""
    if not resume_text.strip():
        raise ValueError(f"No text extracted from {source_file}; cannot score.")

    client = _get_client()
    response = client.messages.parse(
        model=config.MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_build_system_prompt(rubric),
        messages=[
            {
                "role": "user",
                "content": (
                    "Assess the following résumé against the rubric.\n\n"
                    "=== RÉSUMÉ START ===\n"
                    f"{resume_text}\n"
                    "=== RÉSUMÉ END ==="
                ),
            }
        ],
        output_format=ResumeAssessment,
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Model refused to assess {source_file}.")

    assessment = response.parsed_output
    if assessment is None:
        raise RuntimeError(f"Failed to parse a structured assessment for {source_file}.")

    weighted = _weighted_total(assessment, rubric)
    passes = all(c.verdict != "fail" for c in assessment.must_have_checks)

    return ScoredResume(
        source_file=source_file,
        role=role,
        weighted_score=round(weighted, 3),
        passes_must_haves=passes,
        assessment=assessment,
    )


def _weighted_total(assessment: ResumeAssessment, rubric: Rubric) -> float:
    """Combine per-criterion scores using the rubric's normalized weights."""
    weights = rubric.normalized_weights()
    by_id = {cs.criterion_id: cs.score for cs in assessment.criterion_scores}
    total = 0.0
    for criterion_id, weight in weights.items():
        # Missing criterion → treated as 0, surfacing incomplete assessments.
        total += weight * by_id.get(criterion_id, 0)
    return total
