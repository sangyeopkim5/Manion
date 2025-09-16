"""SymPy execution helpers for the deterministic CAS stage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Any

from sympy import (
    Function,
    Rational,
    cos,
    expand,
    factor,
    latex,
    pi,
    simplify,
    sin,
    solve,
    sqrt,
    symbols,
    tan,
)
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from libs.schemas import CASJob, CASResult


SAFE_FUNCS = {
    "simplify": simplify,
    "Rational": Rational,
    "symbols": symbols,
    "sin": sin,
    "cos": cos,
    "tan": tan,
    "sqrt": sqrt,
    "expand": expand,
    "factor": factor,
    "pi": pi,
}


def _run_cas(jobs: List[CASJob]) -> List[CASResult]:
    outputs: List[CASResult] = []
    for job in jobs:
        expr_text = (job.target_expr or "").strip()
        try:
            for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr_text):
                name = match.group(1)
                if name not in SAFE_FUNCS:
                    raise ValueError(f"function {name} not allowed")

            transformations = standard_transformations + (implicit_multiplication_application,)
            expr = parse_expr(expr_text, transformations=transformations, local_dict=SAFE_FUNCS)

            for func in expr.atoms(Function):
                if func.func.__name__ not in SAFE_FUNCS:
                    raise ValueError(f"function {func.func.__name__} not allowed")

            task = (job.task or "simplify").lower()
            if task == "simplify":
                value = simplify(expr)
            elif task == "expand":
                value = expand(expr)
            elif task == "factor":
                value = factor(expr)
            elif task == "evaluate":
                value = expr.evalf()
            elif task == "solve":
                if not job.variables:
                    raise ValueError("solve requires 'variables'")
                variables = [symbols(v) for v in job.variables]
                value = solve(expr, *variables, dict=True)
            else:
                raise ValueError(f"Unsupported task: {task}")

            outputs.append(
                CASResult(
                    id=job.id,
                    result_tex=latex(value),
                    result_py=str(value),
                )
            )
        except Exception as exc:  # pragma: no cover - debugging aid
            import traceback

            detail = (
                f"CAS error in {job.id}: {exc}\n"
                f"Expression: {expr_text}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            raise ValueError(detail)
    return outputs


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


__all__ = ["run_cas_compute"]
