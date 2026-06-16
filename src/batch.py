"""Run a résumé assessment over a pool: preflight, parallel scoring, resume.

Designed for large pools (hundreds of résumés):
  - **Resumable** — each result is written as it completes; a re-run skips
    résumés that already have a result (unless ``force``), so a crash or a
    reclaimed container costs only the in-flight work.
  - **Parallel** — résumés are scored concurrently with a thread pool (the API
    calls are I/O-bound).
  - **Preflight** — counts and a rough cost estimate before any spend.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import parsing, ranking
from .criteria import Rubric
from .parsing import ResumeRef
from .scorer import ScoredResume, score_resume

# Rough per-résumé cost band for the default model (Opus 4.8: $5/$25 per MTok).
# Input ≈ system + résumé; output ≈ structured assessment + adaptive thinking.
# Deliberately a wide band — a true estimate needs token counting.
_COST_PER_RESUME_LOW = 0.04
_COST_PER_RESUME_HIGH = 0.09


@dataclass
class Preflight:
    role: str
    label: str
    parseable: int
    already_scored: int
    to_score: int
    unsupported: List[Path] = field(default_factory=list)

    def cost_band(self) -> tuple[float, float]:
        return (
            self.to_score * _COST_PER_RESUME_LOW,
            self.to_score * _COST_PER_RESUME_HIGH,
        )


def plan(role: str, label: str, pools: List[str], force: bool) -> tuple[Preflight, List[ResumeRef]]:
    """Resolve the pool and work out what still needs scoring."""
    refs = parsing.gather(pools)
    unsup = parsing.unsupported(pools)

    todo: List[ResumeRef] = []
    already = 0
    for ref in refs:
        if not force and ranking.is_scored(role, label, ref.path.name):
            already += 1
        else:
            todo.append(ref)

    pre = Preflight(
        role=role,
        label=label,
        parseable=len(refs),
        already_scored=already,
        to_score=len(todo),
        unsupported=unsup,
    )
    return pre, todo


@dataclass
class RunResult:
    scored: int = 0
    failed: int = 0
    errors: List[tuple[str, str]] = field(default_factory=list)
    ranking_path: Optional[Path] = None


def run(
    rubric: Rubric,
    role: str,
    label: str,
    todo: List[ResumeRef],
    *,
    concurrency: int = 8,
    progress: Optional[Callable[[int, int, ResumeRef, Optional[Exception]], None]] = None,
) -> RunResult:
    """Score ``todo`` in parallel, writing each result as it lands."""
    result = RunResult()
    total = len(todo)
    lock = threading.Lock()
    done = 0

    def _score(ref: ResumeRef) -> ScoredResume:
        text = parsing.extract_text(ref.path)
        return score_resume(rubric, ref.path.name, text, ref.source)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(_score, ref): ref for ref in todo}
        for future in as_completed(futures):
            ref = futures[future]
            err: Optional[Exception] = None
            try:
                scored = future.result()
                ranking.write_one(role, label, scored)
                result.scored += 1
            except Exception as exc:  # one bad résumé must not sink the batch
                err = exc
                result.failed += 1
                result.errors.append((ref.path.name, str(exc)))
            with lock:
                done += 1
                if progress:
                    progress(done, total, ref, err)

    # Rebuild the ranking from everything on disk (this run + prior runs).
    result.ranking_path = ranking.rebuild(role, label)
    return result
