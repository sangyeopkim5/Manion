from __future__ import annotations

import logging
from typing import List

from libs.schemas import CASResult, RenderOutput


def fill_placeholders(draft: str, repls: List[CASResult]) -> RenderOutput:
    """Replace CAS placeholders in ``draft`` using ``repls``.

    When no placeholders are present in the input ``draft`` the function simply
    returns the original code unchanged. This makes it safe to call even when
    the code generation step produced no CAS jobs.
    """

    if "[[CAS:" not in draft:
        return RenderOutput(manim_code_final=draft)

    code = draft
    seen: set[str] = set()
    for result in repls:
        if result.id in seen:
            logging.warning("duplicate CAS id %s", result.id)
            continue
        seen.add(result.id)
        code = code.replace(f"[[CAS:{result.id}]]", "{" + result.result_tex + "}")

    if "[[CAS:" in code:
        raise ValueError("Unreplaced CAS placeholder remains")

    return RenderOutput(manim_code_final=code)
