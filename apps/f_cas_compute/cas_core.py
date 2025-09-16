from typing import List
import re
from typing import List
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
