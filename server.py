from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pipelines.e2e import run_e2e
from pipelines.stages import (
    Stage,
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

app = FastAPI(title="Manion Deterministic Pipeline")


def _parse_stage(value: str) -> Stage:
    value = value.strip().lower()
    for stage in Stage:
        if value == stage.value:
            return stage
        if value == stage.name.lower():
            return stage
        if value == stage.value.split("_")[0]:
            return stage
    raise HTTPException(status_code=400, detail=f"Unknown stage: {value}")


class E2ERequest(BaseModel):
    image_path: Optional[str] = None
    problem_name: Optional[str] = None
    base_dir: Optional[str] = "Probleminput"
    start_stage: Optional[str] = Stage.A_OCR.value
    end_stage: Optional[str] = Stage.H_POSTPROC.value
    force: bool = False


class StageRequest(BaseModel):
    stage: str
    problem_name: str
    base_dir: Optional[str] = "Probleminput"
    image_path: Optional[str] = None
    force: bool = False


class SpecUploadRequest(BaseModel):
    problem_name: str
    spec: Dict[str, Any]
    base_dir: Optional[str] = "Probleminput"


def _run_single_stage(req: StageRequest) -> tuple[Stage, Dict[str, Any]]:
    stage = _parse_stage(req.stage)
    paths = PipelinePaths(Path(req.base_dir), req.problem_name)

    if stage == Stage.A_OCR:
        if not req.image_path:
            raise HTTPException(status_code=400, detail="image_path required for OCR stage")
        return stage, run_stage_a(paths, image_path=req.image_path, overwrite=req.force)
    if stage == Stage.B_GRAPH:
        return stage, run_stage_b(paths)
    if stage == Stage.C_GEO_CODEGEN:
        return stage, run_stage_c(paths, overwrite=req.force)
    if stage == Stage.D_GEO_COMPUTE:
        return stage, run_stage_d(paths, overwrite=req.force)
    if stage == Stage.E_CAS_CODEGEN:
        return stage, run_stage_e(paths, force=req.force)
    if stage == Stage.F_CAS_COMPUTE:
        return stage, run_stage_f(paths, overwrite=req.force)
    if stage == Stage.G_RENDER:
        return stage, run_stage_g(paths)
    if stage == Stage.H_POSTPROC:
        result = run_stage_h(paths)
        return stage, result if result is not None else {"status": "skipped"}
    raise HTTPException(status_code=400, detail=f"Unsupported stage: {req.stage}")


@app.post("/pipeline/e2e")
def pipeline_e2e(req: E2ERequest) -> Dict[str, Any]:
    start = _parse_stage(req.start_stage) if req.start_stage else Stage.A_OCR
    end = _parse_stage(req.end_stage) if req.end_stage else Stage.H_POSTPROC

    try:
        result = run_e2e(
            image_path=req.image_path,
            problem_name=req.problem_name,
            base_dir=req.base_dir or "Probleminput",
            start_stage=start,
            end_stage=end,
            force=req.force,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.post("/pipeline/stage")
def pipeline_stage(req: StageRequest) -> Dict[str, Any]:
    try:
        stage, result = _run_single_stage(req)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"stage": stage.value, "result": result}


@app.post("/pipeline/spec")
def upload_spec(req: SpecUploadRequest) -> Dict[str, Any]:
    paths = PipelinePaths(Path(req.base_dir), req.problem_name)
    spec_path = paths.spec
    spec_path.write_text(json.dumps(req.spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"spec_path": str(spec_path)}


@app.get("/pipeline/spec")
def read_spec(problem_name: str, base_dir: str = "Probleminput") -> Dict[str, Any]:
    paths = PipelinePaths(Path(base_dir), problem_name)
    if not paths.spec.exists():
        raise HTTPException(status_code=404, detail="spec.json not found")
    data = json.loads(paths.spec.read_text(encoding="utf-8"))
    return {"spec": data, "spec_path": str(paths.spec)}


@app.get("/health")
def health() -> Dict[str, Any]:  # pragma: no cover
    return {"status": "ok"}
