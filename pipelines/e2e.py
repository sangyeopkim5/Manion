"""End-to-end orchestration helpers for the deterministic pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pipelines.stages import (
    Stage,
    STAGE_ORDER,
    PipelinePaths,
    run_stage_a,
    run_stage_b,
    run_stage_c,
    run_stage_d,
    run_stage_e,
    run_stage_f,
    run_stage_g,
    run_stage_h,
)


def _ensure_stage(stage: Stage | str) -> Stage:
    if isinstance(stage, Stage):
        return stage
    try:
        return Stage(stage)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"unknown stage: {stage}") from exc


def _execute_stage(
    stage: Stage,
    paths: PipelinePaths,
    *,
    image_path: Optional[str],
    force: bool,
) -> Dict[str, Any]:
    if stage == Stage.A_OCR:
        if not image_path:
            raise ValueError("OCR stage requires an image_path")
        return run_stage_a(paths, image_path=image_path, overwrite=force)
    if stage == Stage.B_GRAPH:
        return run_stage_b(paths)
    if stage == Stage.C_GEO_CODEGEN:
        return run_stage_c(paths, overwrite=force)
    if stage == Stage.D_GEO_COMPUTE:
        return run_stage_d(paths, overwrite=force)
    if stage == Stage.E_CAS_CODEGEN:
        return run_stage_e(paths, force=force)
    if stage == Stage.F_CAS_COMPUTE:
        return run_stage_f(paths, overwrite=force)
    if stage == Stage.G_RENDER:
        return run_stage_g(paths)
    if stage == Stage.H_POSTPROC:
        result = run_stage_h(paths)
        return result if result is not None else {"status": "skipped"}
    raise ValueError(f"Unsupported stage: {stage}")


def run_e2e(
    image_path: Optional[str] = None,
    *,
    problem_name: Optional[str] = None,
    base_dir: str | Path = "Probleminput",
    start_stage: Stage | str = Stage.A_OCR,
    end_stage: Optional[Stage | str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Run the deterministic pipeline from ``start_stage`` to ``end_stage``."""

    start = _ensure_stage(start_stage)
    end = _ensure_stage(end_stage) if end_stage else STAGE_ORDER[-1]

    if problem_name is None:
        if image_path:
            problem_name = Path(image_path).stem
        else:
            raise ValueError("problem_name is required when image_path is omitted")

    base_dir = Path(base_dir)
    paths = PipelinePaths(base_dir, problem_name)

    order = STAGE_ORDER
    start_idx = order.index(start)
    end_idx = order.index(end)
    if start_idx > end_idx:
        raise ValueError("start_stage must come before end_stage")

    stage_results: List[Dict[str, Any]] = []
    current_image = image_path

    for stage in order[start_idx : end_idx + 1]:
        result = _execute_stage(stage, paths, image_path=current_image, force=force)
        stage_results.append({"stage": stage.value, "result": result})
        if stage == Stage.A_OCR:
            current_image = None  # subsequent stages read from disk

    return {
        "problem_dir": str(paths.problem_dir),
        "results": stage_results,
    }
