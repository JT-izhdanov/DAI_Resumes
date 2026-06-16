"""Aggregate scored résumés into a ranking and render the output."""

from __future__ import annotations

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


def write_results(role: str, label: str, ranked: List[ScoredResume]) -> Path:
    """Write per-candidate JSON and a ranking.md; return the results folder."""
    out_dir = config.role_results_dir(role, label)
    out_dir.mkdir(parents=True, exist_ok=True)

    for s in ranked:
        stem = Path(s.source_file).stem
        (out_dir / f"{stem}.json").write_text(
            s.model_dump_json(indent=2), encoding="utf-8"
        )

    ranking_path = out_dir / "ranking.md"
    ranking_path.write_text(_render_markdown(role, label, ranked), encoding="utf-8")
    return out_dir


def _render_markdown(role: str, label: str, ranked: List[ScoredResume]) -> str:
    lines = [f"# Candidate ranking — {role}", "", f"_Résumé pool: {label}_", ""]
    if not ranked:
        lines.append("_No résumés scored._")
        return "\n".join(lines) + "\n"

    # Show the Source column only when résumés come from more than one pool.
    multi_source = len({s.source_pool for s in ranked}) > 1
    header = "| Rank | Candidate | Score | Must-haves |"
    sep = "| ---- | --------- | ----- | ---------- |"
    if multi_source:
        header += " Source |"
        sep += " ------ |"
    header += " File |"
    sep += " ---- |"
    lines += [header, sep]

    for i, s in enumerate(ranked, start=1):
        gate = "✅" if s.passes_must_haves else "⚠️ fails"
        row = f"| {i} | {s.assessment.candidate_name} | {s.weighted_score:.2f} / 5 | {gate} |"
        if multi_source:
            row += f" {s.source_pool} |"
        row += f" `{s.source_file}` |"
        lines.append(row)

    lines += ["", "---"]
    for i, s in enumerate(ranked, start=1):
        a = s.assessment
        provenance = f" · submitted for `{s.source_pool}`" if multi_source else ""
        lines += [
            "",
            f"## {i}. {a.candidate_name} — {s.weighted_score:.2f} / 5",
            "",
            f"_{s.source_file}{provenance}_",
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
