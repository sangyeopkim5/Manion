#!/usr/bin/env python3
"""Command line interface for the deterministic end-to-end pipeline."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from pipelines.e2e import run_e2e
from pipelines.stages import Stage


def _parse_stage(value: Optional[str]) -> Optional[Stage]:
    if value is None:
        return None
    value = value.strip().lower()
    for stage in Stage:
        if value == stage.value:
            return stage
        if value == stage.name.lower():
            return stage
        if value == stage.value.split("_")[0]:
            return stage
    raise argparse.ArgumentTypeError(f"unknown stage: {value}")


def _apply_postproc_overrides(args: argparse.Namespace) -> None:
    if getattr(args, "postproc", False) and getattr(args, "no_postproc", False):
        print("[warn] both --postproc and --no-postproc supplied; ignoring overrides")
        return
    if getattr(args, "postproc", False):
        os.environ["POSTPROC_ENABLED_OVERRIDE"] = "1"
    elif getattr(args, "no_postproc", False):
        os.environ["POSTPROC_ENABLED_OVERRIDE"] = "0"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Manion deterministic pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline from OCR
  python -m pipelines.cli_e2e path/to/problem.jpg --problem-name DemoProblem

  # Resume from geo stages (spec must exist)
  python -m pipelines.cli_e2e --geo --problem-name DemoProblem
        """,
    )
    parser.add_argument("image_path", nargs="?", help="Input image to process")
    parser.add_argument("--problem-name", help="Identifier for the problem")
    parser.add_argument("--problem-dir", help="Existing problem directory")
    parser.add_argument("--base-dir", default="ManimcodeOutput", help="Root directory for pipeline outputs")
    parser.add_argument("--from-stage", help="Start from this stage (e.g. a_ocr, c_geo_codegen)")
    parser.add_argument("--to-stage", help="Stop after this stage")
    parser.add_argument("--geo", action="store_true", help="Shortcut for --from-stage c_geo_codegen")
    parser.add_argument("--force", action="store_true", help="Re-run stages even if outputs exist")
    parser.add_argument("--postproc", action="store_true", help="Force-enable post processing stage")
    parser.add_argument("--no-postproc", action="store_true", help="Disable post processing stage")

    args = parser.parse_args()
    _apply_postproc_overrides(args)

    start_stage = Stage.C_GEO_CODEGEN if args.geo else Stage.A_OCR
    if args.from_stage:
        start_stage = _parse_stage(args.from_stage)
        if start_stage is None:
            start_stage = Stage.A_OCR
    end_stage = _parse_stage(args.to_stage)

    problem_name = args.problem_name
    base_dir = Path(args.base_dir)

    if args.problem_dir:
        problem_dir = Path(args.problem_dir)
        if not problem_dir.exists():
            parser.error(f"problem directory not found: {problem_dir}")
        base_dir = problem_dir.parent
        if problem_name is None:
            problem_name = problem_dir.name

    image_path = args.image_path
    if start_stage == Stage.A_OCR and not image_path:
        parser.error("image_path is required when starting from OCR stage")

    if problem_name is None:
        if image_path:
            problem_name = Path(image_path).stem
        else:
            parser.error("--problem-name is required when image_path is omitted")

    result = run_e2e(
        image_path=image_path,
        problem_name=problem_name,
        base_dir=base_dir,
        start_stage=start_stage,
        end_stage=end_stage,
        force=args.force,
    )

    print(f"\n✅ Pipeline completed. Outputs stored in {result['problem_dir']}")
    for entry in result["results"]:
        stage = entry["stage"]
        status = entry["result"].get("status") if isinstance(entry["result"], dict) else "ok"
        print(f" - {stage}: {status}")


if __name__ == "__main__":  # pragma: no cover
    main()
