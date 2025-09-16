from typing import List, Dict, Any
import json
import re
from pathlib import Path
from sympy import (
    simplify,
    latex,
    Rational,
    symbols,
    sin,
    cos,
    tan,
    sqrt,
    expand,
    factor,
    pi,
    Function,
    solve,
)
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
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


def run_cas(jobs: List[CASJob]) -> List[CASResult]:
    out: List[CASResult] = []
    for j in jobs:
        expr_s = (j.target_expr or "").strip()
        try:
            # 허용된 함수만 확인
            for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr_s):
                name = match.group(1)
                if name not in SAFE_FUNCS:
                    raise ValueError(f"function {name} not allowed")

            # 암시적 곱셈 허용 파서
            transformations = standard_transformations + (
                implicit_multiplication_application,
            )
            expr = parse_expr(expr_s, transformations=transformations, local_dict=SAFE_FUNCS)

            # 함수 안전성 체크
            for f in expr.atoms(Function):
                name = f.func.__name__
                if name not in SAFE_FUNCS:
                    raise ValueError(f"function {name} not allowed")

            # Task에 따른 분기
            task = j.task.lower() if j.task else "simplify"
            if task == "simplify":
                val = simplify(expr)
            elif task == "expand":
                val = expand(expr)
            elif task == "factor":
                val = factor(expr)
            elif task == "evaluate":
                val = expr.evalf()
            elif task == "solve":
                if not j.variables:
                    raise ValueError("solve requires 'variables'")
                vars = [symbols(v) for v in j.variables]
                val = solve(expr, *vars, dict=True)
            else:
                raise ValueError(f"Unsupported task: {task}")

            out.append(
                CASResult(
                    id=j.id,
                    result_tex=latex(val),
                    result_py=str(val),
                )
            )

        except Exception as e:
            import traceback
            error_detail = (
                f"CAS error in {j.id}: {e}\nExpression: {expr_s}\nTraceback: {traceback.format_exc()}"
            )
            raise ValueError(error_detail)

    return out


def _coerce_jobs(raw_jobs: List[Dict[str, Any]]) -> List[CASJob]:
    """Raw job dictionaries를 CASJob 객체로 변환"""
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

    results = run_cas(jobs)
    data = [r.model_dump() for r in results]

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {output_path}")

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(output_path), "results": data, "status": "computed"}
