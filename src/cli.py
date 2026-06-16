"""Command-line entry point for the résumé scoring pipeline.

    python -m src.cli list-roles
    python -m src.cli list-templates
    python -m src.cli assess <role> [--pool <role|path> ...] [--label NAME]
    python -m src.cli rank <role>                 # alias: assess <role> own pool
    python -m src.cli score-file <role> <path>
    python -m src.cli draft-criteria <role> --jd FILE [--family F] [--seniority S]
                                                  [--extends TEMPLATE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import os

from . import batch
from . import criteria as criteria_mod
from . import parsing, ranking
from .parsing import ResumeRef
from .scorer import ScoredResume, score_resume


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _cmd_list_roles(_args: argparse.Namespace) -> int:
    roles = criteria_mod.available_roles()
    if not roles:
        print("No roles found. Create one at roles/<role>/role.yaml.")
        return 1
    print("Roles:")
    for role in roles:
        rubric = criteria_mod.load_rubric(role)
        n = len(parsing.list_resumes(role))
        meta = "/".join(x for x in (rubric.family, rubric.seniority) if x)
        meta = f" [{meta}]" if meta else ""
        print(f"  - {role}{meta}  ({n} résumé{'s' if n != 1 else ''} in own pool)")
    return 0


def _cmd_list_templates(_args: argparse.Namespace) -> int:
    templates = criteria_mod.available_templates()
    if not templates:
        print("No templates found in templates/.")
        return 0
    print("Templates (extend these from a role's role.yaml):")
    for t in templates:
        print(f"  - {t}")
    return 0


def _score_one(rubric, ref: ResumeRef) -> Optional[ScoredResume]:
    print(f"  Scoring {ref.path.name} (from {ref.source}) ...", flush=True)
    try:
        text = parsing.extract_text(ref.path)
        return score_resume(rubric, ref.path.name, text, ref.source)
    except Exception as exc:  # keep going on a single bad file
        print(f"    ! skipped: {exc}", file=sys.stderr)
        return None


def _default_label(role: str, pools: List[str]) -> str:
    if pools == [role]:
        return "applicants"
    return "from-" + "+".join(pools) if pools else "applicants"


def _print_preflight(pre: batch.Preflight, pools: List[str]) -> None:
    print(f"Preflight — assess '{pre.role}' [pool: {pre.label}]")
    print(f"  pools:           {', '.join(pools)}")
    print(f"  parseable:       {pre.parseable} résumé(s)")
    if pre.already_scored:
        print(f"  already scored:  {pre.already_scored} (skipped; use --force to redo)")
    print(f"  to score:        {pre.to_score}")
    if pre.unsupported:
        print(f"  unsupported:     {len(pre.unsupported)} file(s) will be skipped:")
        for p in pre.unsupported[:10]:
            print(f"                     - {p.name}")
        if len(pre.unsupported) > 10:
            print(f"                     ... and {len(pre.unsupported) - 10} more")
    if pre.to_score:
        lo, hi = pre.cost_band()
        print(f"  est. API cost:   ~${lo:.2f}–${hi:.2f} (rough; default model)")


def _run_assessment(
    role: str, pools: List[str], label: str, *,
    concurrency: int, force: bool, dry_run: bool, limit: Optional[int],
) -> int:
    rubric = criteria_mod.load_rubric(role)
    pre, todo = batch.plan(role, label, pools, force)

    if pre.parseable == 0 and not pre.unsupported:
        print(
            f"No résumés found in pool(s): {', '.join(pools)}.\n"
            f"Add .pdf/.docx files (e.g. into roles/{pools[0]}/resumes/) and re-run."
        )
        return 1

    if limit is not None:
        todo = todo[:limit]
        pre.to_score = len(todo)

    _print_preflight(pre, pools)

    if dry_run:
        print("\n(--dry-run: no résumés scored.)")
        return 0
    if not todo:
        print("\nNothing to score — all résumés already have results.")
        ranking.rebuild(role, label)
        return 0
    if not _has_api_key():
        print(
            "\nERROR: no ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in the "
            "environment. Set it (see .env.example) before scoring.",
            file=sys.stderr,
        )
        return 2

    target = rubric.title + (f" ({rubric.seniority})" if rubric.seniority else "")
    print(f"\nScoring {len(todo)} résumé(s) against '{target}' "
          f"with concurrency {concurrency}...")

    def _progress(done, total, ref, err):
        status = "ok " if err is None else "ERR"
        print(f"  [{done}/{total}] {status} {ref.path.name} (from {ref.source})", flush=True)

    result = batch.run(rubric, role, label, todo, concurrency=concurrency, progress=_progress)

    ranked = ranking.rank(ranking.load_results(role, label))
    print(f"\nScored {result.scored}, failed {result.failed}, "
          f"ranked {len(ranked)} total for '{role}' [{label}].")
    if result.errors:
        print("Failures:")
        for name, msg in result.errors[:10]:
            print(f"  - {name}: {msg}")
        if len(result.errors) > 10:
            print(f"  ... and {len(result.errors) - 10} more")

    print("\nTop candidates:")
    multi = len({s.source_pool for s in ranked}) > 1
    for i, s in enumerate(ranked[:10], start=1):
        gate = "" if s.passes_must_haves else "  [fails must-haves]"
        src = f"  ({s.source_pool})" if multi else ""
        print(f"  {i}. {s.assessment.candidate_name:<28} {s.weighted_score:.2f}/5{src}{gate}")
    if len(ranked) > 10:
        print(f"  ... {len(ranked) - 10} more in the full ranking.")
    print(f"\nFull results: {result.ranking_path} (+ per-candidate JSON).")
    return 0


def _cmd_assess(args: argparse.Namespace) -> int:
    role = args.role
    if not criteria_mod.is_role(role):
        print(f"Unknown role '{role}'. See `list-roles`.", file=sys.stderr)
        return 1
    pools = args.pool or [role]
    label = args.label or _default_label(role, pools)
    return _run_assessment(
        role, pools, label, concurrency=args.concurrency, force=args.force,
        dry_run=args.dry_run, limit=args.limit,
    )


def _cmd_rank(args: argparse.Namespace) -> int:
    # Convenience: assess a role against its own applicant pool.
    return _run_assessment(
        args.role, [args.role], "applicants", concurrency=args.concurrency,
        force=args.force, dry_run=args.dry_run, limit=args.limit,
    )


def _cmd_score_file(args: argparse.Namespace) -> int:
    role = args.role
    rubric = criteria_mod.load_rubric(role)
    path = Path(args.path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    scored = _score_one(rubric, ResumeRef(path=path, source="ad-hoc"))
    if scored is None:
        return 1

    a = scored.assessment
    gate = "passes" if scored.passes_must_haves else "FAILS must-haves"
    print(f"\n{a.candidate_name} — {scored.weighted_score:.2f}/5 ({gate})")
    print(f"\n{a.summary}\n")
    for cs in a.criterion_scores:
        print(f"  {cs.criterion_id}: {cs.score}/5 — {cs.justification}")
    return 0


def _cmd_draft_criteria(args: argparse.Namespace) -> int:
    from . import generate

    jd_path = Path(args.jd)
    if not jd_path.exists():
        print(f"Job description not found: {jd_path}", file=sys.stderr)
        return 1
    jd_text = jd_path.read_text(encoding="utf-8")

    print(f"Drafting criteria for '{args.role}' from {jd_path.name} with the Claude API...")
    draft = generate.draft_from_jd(
        args.role, jd_text, family=args.family, seniority=args.seniority,
        extends=args.extends,
    )
    try:
        spec_path = generate.write_role(
            args.role, draft, jd_text, family=args.family, seniority=args.seniority,
            extends=args.extends, overwrite=args.overwrite,
        )
    except FileExistsError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"\nWrote {spec_path} with {len(draft.criteria)} criteria:")
    for c in draft.criteria:
        print(f"  - {c.id} (weight {c.weight})")
    print("\nReview and tune the weights/must-haves, then add résumés and run "
          f"`assess {args.role}`.")
    return 0


def _add_batch_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--concurrency", type=int, default=8,
                   help="Parallel API calls (default 8).")
    p.add_argument("--force", action="store_true",
                   help="Re-score résumés that already have results.")
    p.add_argument("--dry-run", action="store_true",
                   help="Show the preflight (counts + cost estimate) and stop.")
    p.add_argument("--limit", type=int, default=None,
                   help="Score at most N résumés (useful for a trial run).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dai-resumes", description="Score and rank résumés by role using Claude."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-roles", help="List roles and their pools.").set_defaults(
        func=_cmd_list_roles
    )
    sub.add_parser("list-templates", help="List reusable family templates.").set_defaults(
        func=_cmd_list_templates
    )

    p_assess = sub.add_parser(
        "assess", help="Score résumés from one or more pools against a role's criteria."
    )
    p_assess.add_argument("role", help="Role whose criteria to score against.")
    p_assess.add_argument(
        "--pool", action="append", metavar="ROLE|PATH",
        help="Résumé source: a role name, directory, or glob. Repeatable. "
        "Defaults to the role's own pool.",
    )
    p_assess.add_argument("--label", help="Results subfolder name (auto if omitted).")
    _add_batch_flags(p_assess)
    p_assess.set_defaults(func=_cmd_assess)

    p_rank = sub.add_parser("rank", help="Assess a role against its own applicant pool.")
    p_rank.add_argument("role")
    _add_batch_flags(p_rank)
    p_rank.set_defaults(func=_cmd_rank)

    p_file = sub.add_parser("score-file", help="Score a single résumé file.")
    p_file.add_argument("role")
    p_file.add_argument("path")
    p_file.set_defaults(func=_cmd_score_file)

    p_draft = sub.add_parser(
        "draft-criteria", help="Draft a role.yaml from a job description (uses Claude)."
    )
    p_draft.add_argument("role")
    p_draft.add_argument("--jd", required=True, help="Path to the job description file.")
    p_draft.add_argument("--family", help="Role family, e.g. data_engineer.")
    p_draft.add_argument("--seniority", choices=criteria_mod.SENIORITY_LEVELS)
    p_draft.add_argument("--extends", help="Template to extend (see list-templates).")
    p_draft.add_argument("--overwrite", action="store_true")
    p_draft.set_defaults(func=_cmd_draft_criteria)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
