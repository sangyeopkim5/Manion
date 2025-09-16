"""SymPy execution helpers for the CEO pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Dict, Any

from libs.schemas import CASJob
from .cas_core import run_cas as _run_cas


def _coerce_jobs(raw_jobs: Iterable[dict | CASJob]) -> List[CASJob]:
    jobs: List[CASJob] = []
    for job in raw_jobs:
        if isinstance(job, CASJob):
            jobs.append(job)
        else:
            jobs.append(CASJob(**job))
    return jobs


def run_cas_compute(
    problem_dir: str | Path,
    *,
    cas_jobs_path: str | Path | None = None,
    output_path: str | Path | None = None,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Load CAS jobs from disk, execute them and store the results."""

    problem_dir_path = Path(problem_dir).expanduser().resolve()
    cas_jobs_path = Path(cas_jobs_path or (problem_dir_path / "cas_jobs.json"))
    output_path = Path(output_path or (problem_dir_path / "cas_results.json"))

    if not cas_jobs_path.exists():
        output_path.write_text("[]\n", encoding="utf-8")
        return {"path": str(output_path), "results": [], "status": "skipped"}

    raw = json.loads(cas_jobs_path.read_text(encoding="utf-8"))
    jobs = _coerce_jobs(raw)
    if not jobs:
        output_path.write_text("[]\n", encoding="utf-8")
        return {"path": str(output_path), "results": [], "status": "skipped"}

    results = _run_cas(jobs)
    data = [r.model_dump() for r in results]

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {output_path}")

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(output_path), "results": data, "status": "computed"}
