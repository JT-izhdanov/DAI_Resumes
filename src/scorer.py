"""Score a résumé against a role rubric using the Claude API.

Uses structured outputs (`client.messages.parse`) so the model returns a
validated, per-criterion breakdown rather than free text. The weighted total is
computed in code from the model's per-criterion scores — the judgment is the
model's, the math is ours.

The system prompt is assembled from the rubric, the target seniority, and the
role's job description (when present), so the same résumé can be assessed
against different roles and levels.
"""

from __future__ import annotations

from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from . import config
from .criteria import Rubric

# Reusable client. Reads ANTHROPIC_API_KEY from the environment.
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# Per-level calibration guidance injected into the prompt.
_SENIORITY_GUIDANCE = {
    "associate": (
        "This is an Associate / entry-level role (typically 0–2 years). Reward "
        "strong fundamentals, trajectory, and potential; do not penalize limited "
        "professional experience."
    ),
    "mid": (
        "This is a mid-level role (typically 2–5 years) where the candidate owns "
        "well-scoped work independently."
    ),
    "senior": (
        "This is a Senior role (typically 5–8+ years) expecting ownership of "
        "significant systems, technical leadership, and mentorship."
    ),
    "principal": (
        "This is a Principal role (typically 10+ years) expecting org-wide "
        "technical leadership, architecture ownership, and strategic impact."
    ),
}


# ---- Structured output schema -------------------------------------------------


class CriterionScore(BaseModel):
    criterion_id: str = Field(description="Matches an `id` from the rubric criteria.")
    score: int = Field(ge=0, le=5, description="0–5 score on the rubric scale.")
    justification: str = Field(
        description="One or two sentences citing evidence from the résumé."
    )


class MustHaveCheck(BaseModel):
    requirement: str
    verdict: Literal["pass", "fail", "unknown"]
    note: str = Field(description="Brief reason for the verdict.")


class ResumeAssessment(BaseModel):
    candidate_name: str = Field(
        description="Candidate's name as it appears on the résumé, or 'Unknown'."
    )
    summary: str = Field(description="2–3 sentence overall summary of fit.")
    criterion_scores: List[CriterionScore]
    must_have_checks: List[MustHaveCheck]
    strengths: List[str] = Field(description="Key strengths for this role.")
    concerns: List[str] = Field(description="Gaps, risks, or missing information.")


class ScoredResume(BaseModel):
    """An assessment plus the weighted total computed in code."""

    source_file: str
    source_pool: str = Field(description="Pool the résumé came from (provenance).")
    role: str
    seniority: Optional[str] = None
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

    parts = [
        f"You are an expert technical recruiter for a Data & AI team, screening "
        f"candidates for the role of {rubric.title}."
    ]
    if rubric.seniority and rubric.seniority in _SENIORITY_GUIDANCE:
        parts.append(_SENIORITY_GUIDANCE[rubric.seniority])
    if rubric.description.strip():
        parts.append(f"Role description:\n{rubric.description.strip()}")
    if rubric.jd_text:
        parts.append(
            "Full job description (authoritative — prefer it where it conflicts "
            f"with the summary):\n{rubric.jd_text}"
        )
    parts.append(f"Score each criterion on this 0–5 scale:\n{scale_lines}")
    parts.append(
        "Criteria to score (return one entry per id, using the exact id):\n"
        f"{criteria_lines}"
    )
    parts.append(f"Hard-gate requirements (judge pass/fail/unknown):\n{must_have_lines}")
    parts.append(
        "Be evidence-based and calibrated to the target seniority. Credit only "
        "what the résumé actually shows; use 'unknown' for must-haves when the "
        "résumé is silent rather than assuming pass or fail. Do not invent "
        "experience that isn't stated. Note that a résumé may have been submitted "
        "for a different role — assess it purely against the criteria above."
    )
    return "\n\n".join(parts)


def score_resume(
    rubric: Rubric,
    source_file: str,
    resume_text: str,
    source_pool: str,
) -> ScoredResume:
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
        source_pool=source_pool,
        role=rubric.role,
        seniority=rubric.seniority,
        weighted_score=round(weighted, 3),
        passes_must_haves=passes,
        assessment=assessment,
    )


def _weighted_total(assessment: ResumeAssessment, rubric: Rubric) -> float:
    weights = rubric.normalized_weights()
    by_id = {cs.criterion_id: cs.score for cs in assessment.criterion_scores}
    total = 0.0
    for criterion_id, weight in weights.items():
        total += weight * by_id.get(criterion_id, 0)  # missing → 0, surfaces gaps
    return total
