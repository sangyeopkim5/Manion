from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping

from .planner import load_spec, plan_and_solve, scale_into_box

DEFAULT_BOX = {"min": [-6.0, -3.0], "max": [6.0, 3.0], "margin": 0.2}


def _ensure_meta(spec: Dict[str, Any]) -> Dict[str, Any]:
    meta = spec.setdefault("meta", {})
    if not isinstance(meta, dict):
        spec["meta"] = {}
        meta = spec["meta"]
    return meta


def _serialise_points(points: Mapping[str, Any]) -> Dict[str, list]:
    serialised: Dict[str, list] = {}
    for key, value in points.items():
        if value is None:
            continue
        serialised[key] = [float(c) for c in value]
    return serialised


def solve_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    if spec.get("type") in (None, "", "__TBD__"):
        raise ValueError("spec.type must be defined before geo_compute can run")

    solution = plan_and_solve(spec)
    box = spec.get("box") or DEFAULT_BOX
    scaled_points, scale = scale_into_box(solution, box)

    spec["points"] = _serialise_points(scaled_points)
    spec["scale"] = float(scale)
    spec["status"] = "solved"

    meta = _ensure_meta(spec)
    meta["solved_at"] = datetime.utcnow().isoformat() + "Z"
    return spec


def solve_spec_file(
    spec_path: str | Path,
    *,
    overwrite: bool = True,
    output_path: str | Path | None = None,
) -> Dict[str, Any]:
    spec_path = Path(spec_path)
    if not spec_path.exists():
        raise FileNotFoundError(f"spec file not found: {spec_path}")

    spec = load_spec(str(spec_path))
    solved = solve_spec(spec)

    target = Path(output_path) if output_path else spec_path
    if target.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {target}")

    with target.open("w", encoding="utf-8") as fh:
        json.dump(solved, fh, ensure_ascii=False, indent=2)

    return solved


def solve_in_problem_dir(
    problem_dir: str | Path,
    *,
    spec_filename: str = "spec.json",
    overwrite: bool = True,
) -> Dict[str, Any]:
    problem_dir = Path(problem_dir)
    spec_path = problem_dir / spec_filename
    return solve_spec_file(spec_path, overwrite=overwrite)


__all__ = [
    "DEFAULT_BOX",
    "load_spec",
    "plan_and_solve",
    "scale_into_box",
    "solve_spec",
    "solve_spec_file",
    "solve_in_problem_dir",
]
