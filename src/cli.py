"""Command-line entry point for the résumé scoring pipeline.

Usage:
    python -m src.cli list-roles
    python -m src.cli rank <role>
    python -m src.cli score-file <role> <path-to-resume>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from . import criteria as criteria_mod
from . import parsing, ranking
from .scorer import ScoredResume, score_resume


def _cmd_list_roles(_args: argparse.Namespace) -> int:
    roles = criteria_mod.available_roles()
    if not roles:
        print("No roles found. Add a rubric at criteria/<role>.yaml.")
        return 1
    print("Available roles:")
    for role in roles:
        n = len(parsing.list_resumes(role))
        print(f"  - {role} ({n} résumé{'s' if n != 1 else ''})")
    return 0


def _score_one(role, rubric, path: Path) -> ScoredResume | None:
    print(f"  Scoring {path.name} ...", flush=True)
    try:
        text = parsing.extract_text(path)
        return score_resume(role, path.name, text, rubric)
    except Exception as exc:  # keep going on a single bad file
        print(f"    ! skipped: {exc}", file=sys.stderr)
        return None


def _cmd_rank(args: argparse.Namespace) -> int:
    role = args.role
    rubric = criteria_mod.load_rubric(role)
    files = parsing.list_resumes(role)
    if not files:
        print(
            f"No résumés found in roles/{role}/resumes/. "
            f"Add .pdf or .docx files and re-run."
        )
        return 1

    print(f"Scoring {len(files)} résumé(s) for role '{role}' with the Claude API...")
    scored: List[ScoredResume] = [s for f in files if (s := _score_one(role, rubric, f))]
    if not scored:
        print("No résumés were successfully scored.", file=sys.stderr)
        return 1

    ranked = ranking.rank(scored)
    out_dir = ranking.write_results(role, ranked)

    print(f"\nTop candidates for '{role}':")
    for i, s in enumerate(ranked, start=1):
        gate = "" if s.passes_must_haves else "  [fails must-haves]"
        print(f"  {i}. {s.assessment.candidate_name:<28} {s.weighted_score:.2f}/5{gate}")
    print(f"\nFull results written to {out_dir}/ (ranking.md + per-candidate JSON).")
    return 0


def _cmd_score_file(args: argparse.Namespace) -> int:
    role = args.role
    rubric = criteria_mod.load_rubric(role)
    path = Path(args.path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    scored = _score_one(role, rubric, path)
    if scored is None:
        return 1

    a = scored.assessment
    gate = "passes" if scored.passes_must_haves else "FAILS must-haves"
    print(f"\n{a.candidate_name} — {scored.weighted_score:.2f}/5 ({gate})")
    print(f"\n{a.summary}\n")
    for cs in a.criterion_scores:
        print(f"  {cs.criterion_id}: {cs.score}/5 — {cs.justification}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dai-resumes", description="Score and rank résumés by role using Claude."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-roles", help="List roles that have a rubric.").set_defaults(
        func=_cmd_list_roles
    )

    p_rank = sub.add_parser("rank", help="Score every résumé for a role and rank them.")
    p_rank.add_argument("role")
    p_rank.set_defaults(func=_cmd_rank)

    p_file = sub.add_parser("score-file", help="Score a single résumé file.")
    p_file.add_argument("role")
    p_file.add_argument("path")
    p_file.set_defaults(func=_cmd_score_file)

    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
