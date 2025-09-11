from typing import List
import logging
from libs.schemas import CASResult, RenderOutput


def fill_placeholders(draft: str, repls: List[CASResult]) -> RenderOutput:
    """Replace CAS placeholders in ``draft`` using ``repls``.

    When no placeholders are present in the input ``draft`` the function simply
    returns the original code unchanged. This makes it safe to call even when
    the code generation step produced no CAS jobs.
    """

    # Fast path: if there are no CAS placeholders, return as-is
    if "[[CAS:" not in draft:
        return RenderOutput(manim_code_final=draft)

    code = draft
    seen = set()
    for r in repls:
        if r.id in seen:
            logging.warning(f"duplicate CAS id {r.id}")
            continue
        seen.add(r.id)
        code = code.replace(f"[[CAS:{r.id}]]", "{" + r.result_tex + "}")
    if "[[CAS:" in code:
        raise ValueError("Unreplaced CAS placeholder remains")
    return RenderOutput(manim_code_final=code)

