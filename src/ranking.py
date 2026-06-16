"""Aggregate scored résumés into a ranking and render the output.

Results are written incrementally — one JSON per candidate as it's scored — so a
large batch is resumable and a crash never loses completed work. The ranking is
rebuilt from whatever JSON files are present.
"""

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


def result_path(role: str, label: str, source_file: str) -> Path:
    """Per-candidate JSON path for a résumé."""
    return config.role_results_dir(role, label) / f"{Path(source_file).stem}.json"


def write_one(role: str, label: str, scored: ScoredResume) -> Path:
    """Persist a single candidate's assessment immediately (idempotent)."""
    path = result_path(role, label, scored.source_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scored.model_dump_json(indent=2), encoding="utf-8")
    return path


def is_scored(role: str, label: str, source_file: str) -> bool:
    """Whether this résumé already has a result on disk (for resumability)."""
    return result_path(role, label, source_file).exists()


def load_results(role: str, label: str) -> List[ScoredResume]:
    """Load every per-candidate JSON in a results folder."""
    out_dir = config.role_results_dir(role, label)
    if not out_dir.exists():
        return []
    scored: List[ScoredResume] = []
    for p in sorted(out_dir.glob("*.json")):
        scored.append(ScoredResume.model_validate_json(p.read_text(encoding="utf-8")))
    return scored


def rebuild(role: str, label: str) -> Path:
    """Re-render ranking.md from all per-candidate JSON on disk."""
    ranked = rank(load_results(role, label))
    out_dir = config.role_results_dir(role, label)
    out_dir.mkdir(parents=True, exist_ok=True)
    ranking_path = out_dir / "ranking.md"
    ranking_path.write_text(_render_markdown(role, label, ranked), encoding="utf-8")
    return ranking_path


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
