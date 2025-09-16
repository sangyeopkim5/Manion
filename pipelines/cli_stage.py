"""Run an individual stage of the deterministic pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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


def _parse_stage(value: str) -> Stage:
    value = value.strip().lower()
    for stage in Stage:
        if value == stage.value:
            return stage
        if value == stage.name.lower():
            return stage
        if value == stage.value.split("_")[0]:
            return stage
    raise argparse.ArgumentTypeError(f"unknown stage: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single pipeline stage")
    parser.add_argument("stage", help="Stage identifier (e.g. a_ocr, b_graphsampling)")
    parser.add_argument("--problem-name", required=True, help="Problem identifier")
    parser.add_argument("--base-dir", default="Probleminput", help="Root directory for pipeline outputs")
    parser.add_argument("--image", help="Input image (required for stage a)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing artefacts")

    args = parser.parse_args()
    stage = _parse_stage(args.stage)

    base_dir = Path(args.base_dir)
    paths = PipelinePaths(base_dir, args.problem_name)

    if stage == Stage.A_OCR:
        if not args.image:
            parser.error("--image is required for the OCR stage")
        result = run_stage_a(paths, image_path=args.image, overwrite=args.force)
    elif stage == Stage.B_GRAPH:
        result = run_stage_b(paths)
    elif stage == Stage.C_GEO_CODEGEN:
        result = run_stage_c(paths, overwrite=args.force)
    elif stage == Stage.D_GEO_COMPUTE:
        result = run_stage_d(paths, overwrite=args.force)
    elif stage == Stage.E_CEO_CODEGEN:
        result = run_stage_e(paths, force=args.force)
    elif stage == Stage.F_CEO_COMPUTE:
        result = run_stage_f(paths, overwrite=args.force)
    elif stage == Stage.G_RENDER:
        result = run_stage_g(paths)
    elif stage == Stage.H_POSTPROCESS:
        res = run_stage_h(paths)
        result = res if res is not None else {"status": "skipped"}
    else:  # pragma: no cover - defensive
        parser.error(f"Unsupported stage: {stage}")

    print(json.dumps({"stage": stage.value, "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
