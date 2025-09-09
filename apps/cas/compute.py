from typing import List
import re
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
        expr_s = j.expr.strip()
        try:
            # Allow only functions present in SAFE_FUNCS. Without this pre-check
            # unknown tokens like ``badfunc(1)`` would be interpreted as a
            # multiplication of symbols when using implicit multiplication.
            for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr_s):
                name = match.group(1)
                if name not in SAFE_FUNCS:
                    raise ValueError(f"function {name} not allowed")

            # 암시적 곱셈을 지원하는 변환 규칙 설정
            transformations = standard_transformations + (
                implicit_multiplication_application,
            )
            # parse_expr을 사용하여 암시적 곱셈 지원 (예: 2a -> 2*a)
            expr = parse_expr(expr_s, transformations=transformations, local_dict=SAFE_FUNCS)
            for f in expr.atoms(Function):
                name = f.func.__name__
                if name not in SAFE_FUNCS:
                    raise ValueError(f"function {name} not allowed")
            val = simplify(expr)
            out.append(CASResult(id=j.id, result_tex=latex(val), result_py=str(val)))
        except Exception as e:
            # 더 자세한 오류 정보 제공
            import traceback
            error_detail = (
                f"CAS error in {j.id}: {e}\nExpression: {expr_s}\nTraceback: {traceback.format_exc()}"
            )
            raise ValueError(error_detail)
    return out

