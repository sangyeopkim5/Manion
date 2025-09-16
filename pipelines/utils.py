"""Shared helpers for pipeline orchestration and server endpoints."""

from __future__ import annotations

import json
import re
from typing import Dict, List, Tuple

from libs.schemas import CASResult

_PLACEHOLDER_RE = re.compile(r"\[\[CAS:([A-Za-z0-9_\-]+)\]\]")


def strip_code_fences(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"^\s*```(?:python)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text


def find_balanced_json_array(text: str, start_idx: int = 0) -> str:
    i = text.find("[", start_idx)
    if i == -1:
        raise RuntimeError("CAS-JOBS JSON 배열 시작 '['를 찾지 못했습니다.")
    depth = 0
    for j, char in enumerate(text[i:], start=i):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    raise RuntimeError("대괄호 균형이 맞는 JSON 배열 끝을 찾지 못했습니다.")


def normalize_expr_for_sympy(expr: str) -> str:
    if not expr:
        return expr
    expr = expr.replace(r"\left", "").replace(r"\right", "")
    expr = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", expr)
    expr = expr.replace("\\", "")
    return " ".join(expr.split())


def extract_jobs_and_code(code_text: str) -> Tuple[List[dict], str]:
    code_text = strip_code_fences(code_text)
    marker = re.search(r"-{3}CAS-JOBS-{3}", code_text)
    if not marker:
        raise RuntimeError("CAS-JOBS 섹션을 찾을 수 없습니다.")
    manim_code = code_text[: marker.start()].strip()
    tail = code_text[marker.end() :]

    json_text = find_balanced_json_array(tail, 0)
    try:
        jobs_raw = json.loads(json_text)
    except Exception:
        obj_pat = re.compile(
            r"\{[^{}]*?(\"task\"\s*:\s*\"[^\"]+\")[^{}]*?(\"target_expr\"\s*:\s*\"[^\"]+\")[^{}]*?\}",
            re.S,
        )
        jobs_raw = []
        for match in obj_pat.finditer(json_text):
            fragment = re.sub(r",\s*(\}|$)", r"\1", match.group(0))
            try:
                jobs_raw.append(json.loads(fragment))
            except Exception:
                continue
        if not jobs_raw:
            raise RuntimeError("CAS-JOBS JSON 파싱 실패(수복 불가).")

    for idx, job in enumerate(jobs_raw, start=1):
        job.setdefault("id", f"S{idx}")
        job["target_expr"] = normalize_expr_for_sympy(job.get("target_expr", ""))
    return jobs_raw, manim_code


def contains_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(text or ""))


def substitute_placeholders(expr: str, results: Dict[str, CASResult]) -> str:
    def repl(match: re.Match[str]) -> str:
        identifier = match.group(1)
        if identifier not in results:
            return match.group(0)
        return f"({results[identifier].result_py})"

    return _PLACEHOLDER_RE.sub(repl, expr)
