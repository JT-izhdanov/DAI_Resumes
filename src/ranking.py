"""Aggregate scored résumés into a ranking and render the output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from . import config
from .scorer import ScoredResume


def rank(scored: List[ScoredResume]) -> List[ScoredResume]:
    """Sort best-first: must-have passers first, then by weighted score."""
    return sorted(
        scored,
        key=lambda s: (s.passes_must_haves, s.weighted_score),
        reverse=True,
    )


def write_results(role: str, ranked: List[ScoredResume]) -> Path:
    """Write per-candidate JSON and a ranking.md; return the results folder."""
    out_dir = config.role_results_dir(role)
    out_dir.mkdir(parents=True, exist_ok=True)

    for s in ranked:
        stem = Path(s.source_file).stem
        (out_dir / f"{stem}.json").write_text(
            s.model_dump_json(indent=2), encoding="utf-8"
        )

    ranking_path = out_dir / "ranking.md"
    ranking_path.write_text(_render_markdown(role, ranked), encoding="utf-8")
    return out_dir


def _render_markdown(role: str, ranked: List[ScoredResume]) -> str:
    lines = [f"# Candidate ranking — {role}", ""]
    if not ranked:
        lines.append("_No résumés scored._")
        return "\n".join(lines) + "\n"

    lines += [
        "| Rank | Candidate | Score | Must-haves | File |",
        "| ---- | --------- | ----- | ---------- | ---- |",
    ]
    for i, s in enumerate(ranked, start=1):
        gate = "✅" if s.passes_must_haves else "⚠️ fails"
        name = s.assessment.candidate_name
        lines.append(
            f"| {i} | {name} | {s.weighted_score:.2f} / 5 | {gate} | `{s.source_file}` |"
        )

    lines.append("")
    lines.append("---")
    for i, s in enumerate(ranked, start=1):
        a = s.assessment
        lines += [
            "",
            f"## {i}. {a.candidate_name} — {s.weighted_score:.2f} / 5",
            "",
            f"_{s.source_file}_",
            "",
            a.summary,
            "",
            "**Per-criterion:**",
        ]
        for cs in a.criterion_scores:
            lines.append(f"- `{cs.criterion_id}`: **{cs.score}/5** — {cs.justification}")
        if a.strengths:
            lines += ["", "**Strengths:**"] + [f"- {x}" for x in a.strengths]
        if a.concerns:
            lines += ["", "**Concerns:**"] + [f"- {x}" for x in a.concerns]
        lines += ["", "**Must-haves:**"]
        for c in a.must_have_checks:
            mark = {"pass": "✅", "fail": "❌", "unknown": "❓"}.get(c.verdict, "❓")
            lines.append(f"- {mark} {c.requirement} — {c.note}")

    return "\n".join(lines) + "\n"
