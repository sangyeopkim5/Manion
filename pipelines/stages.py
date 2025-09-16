"""Pipeline stage orchestration for the deterministic geo workflow."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional


from libs.schemas import CASResult
from apps.a_ocr.dots_ocr.parser import DotsOCRParser
from apps.a_ocr.tools.picture_ocr_pipeline import run_pipeline as run_picture_ocr_pipeline
from apps.b_graphsampling.builder import build_outputschema
from apps.c_geo_codegen import generate_spec
from apps.d_geo_compute import solve_in_problem_dir
from apps.e_cas_codegen import run_cas_codegen
from apps.f_cas_compute import run_cas_compute
from apps.g_render import fill_placeholders
from apps.h_postproc import run_postproc_stage
from pipelines.utils import contains_placeholder


class Stage(Enum):
    A_OCR = "a_ocr"
    B_GRAPH = "b_graphsampling"
    C_GEO_CODEGEN = "c_geo_codegen"
    D_GEO_COMPUTE = "d_geo_compute"
    E_CAS_CODEGEN = "e_cas_codegen"
    F_CAS_COMPUTE = "f_cas_compute"
    G_RENDER = "g_render"
    H_POSTPROC = "h_postproc"

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return self.value


STAGE_ORDER: List[Stage] = [
    Stage.A_OCR,
    Stage.B_GRAPH,
    Stage.C_GEO_CODEGEN,
    Stage.D_GEO_COMPUTE,
    Stage.E_CAS_CODEGEN,
    Stage.F_CAS_COMPUTE,
    Stage.G_RENDER,
    Stage.H_POSTPROC,
]


@dataclass
class PipelinePaths:
    base_dir: Path
    problem_name: str

    def __post_init__(self) -> None:
        self.base_dir = self.base_dir.expanduser().resolve()
        self.problem_dir = self.base_dir / self.problem_name
        self.problem_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ocr_json(self) -> Path:
        return self.problem_dir / "problem.json"

    @property
    def ocr_markdown(self) -> Path:
        return self.problem_dir / "problem.md"

    @property
    def ocr_visual(self) -> Path:
        return self.problem_dir / "problem.jpg"

    @property
    def vector_json(self) -> Path:
        return self.problem_dir / "problem_vector.json"

    @property
    def spec(self) -> Path:
        return self.problem_dir / "spec.json"

    @property
    def codegen_output(self) -> Path:
        return self.problem_dir / "codegen_output.py"

    @property
    def manim_draft(self) -> Path:
        return self.problem_dir / "manim_draft.py"

    @property
    def cas_jobs(self) -> Path:
        return self.problem_dir / "cas_jobs.json"

    @property
    def cas_results(self) -> Path:
        return self.problem_dir / "cas_results.json"

    @property
    def final_code(self) -> Path:
        return self.problem_dir / "problem_final.py"

    def input_image_copy(self) -> Optional[Path]:
        for candidate in sorted(self.problem_dir.glob("problem_input.*")):
            return candidate
        return None

    def crop_images(self) -> List[Path]:
        images = sorted(self.problem_dir.glob("*__pic_i*.jpg"))
        images.extend(sorted(self.problem_dir.glob("*__pic_i*.png")))
        return images


def _copy_with_name(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def run_stage_a(paths: PipelinePaths, image_path: str, *, overwrite: bool = False) -> Dict[str, Any]:
    src = Path(image_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"input image not found: {image_path}")

    if not overwrite and paths.ocr_json.exists():
        return {
            "status": "skipped",
            "reason": "problem.json already exists",
            "json": str(paths.ocr_json),
        }

    tmp_root = paths.problem_dir / "__ocr_raw"
    if tmp_root.exists():
        shutil.rmtree(tmp_root)

    parser = DotsOCRParser(output_dir=str(tmp_root))
    run_picture_ocr_pipeline(parser=parser, input_path=str(src))

    # dots OCR saves results inside <output>/<stem>/<stem>
    stem = src.stem
    candidate_dir = tmp_root / stem
    if (candidate_dir / stem).exists():
        candidate_dir = candidate_dir / stem
    search_root = candidate_dir if candidate_dir.exists() else tmp_root

    json_candidates = sorted(
        [p for p in search_root.rglob("*.json") if "__pic_i" not in p.stem]
    )
    if not json_candidates:
        raise FileNotFoundError("OCR stage did not produce a JSON file")

    main_json = next((p for p in json_candidates if p.stem == stem), json_candidates[0])
    md_candidates = sorted(search_root.rglob("*.md"))
    visual_candidates = sorted(
        [p for p in search_root.rglob("*.jpg") if "__pic_i" not in p.stem]
    )

    _copy_with_name(main_json, paths.ocr_json)
    if md_candidates:
        _copy_with_name(md_candidates[0], paths.ocr_markdown)
    if visual_candidates:
        _copy_with_name(visual_candidates[0], paths.ocr_visual)

    for crop in search_root.rglob("*__pic_i*.jpg"):
        _copy_with_name(crop, paths.problem_dir / crop.name)
    for crop in search_root.rglob("*__pic_i*.png"):
        _copy_with_name(crop, paths.problem_dir / crop.name)
    for crop_json in search_root.rglob("*__pic_i*.json"):
        _copy_with_name(crop_json, paths.problem_dir / crop_json.name)

    # Preserve original image for downstream prompts
    input_copy = paths.problem_dir / f"problem_input{src.suffix.lower()}"
    _copy_with_name(src, input_copy)

    shutil.rmtree(tmp_root, ignore_errors=True)

    return {
        "status": "ok",
        "json": str(paths.ocr_json),
        "markdown": str(paths.ocr_markdown) if paths.ocr_markdown.exists() else None,
        "visual": str(paths.ocr_visual) if paths.ocr_visual.exists() else None,
        "crops": [p.name for p in paths.crop_images()],
    }


def run_stage_b(paths: PipelinePaths) -> Dict[str, Any]:
    if not paths.ocr_json.exists():
        raise FileNotFoundError("problem.json missing – run OCR stage first")

    args = SimpleNamespace(
        emit_anchors=True,
        frame="14x8",
        dpi=300,
        vectorizer="potrace",
        points_per_path=600,
    )
    payload = build_outputschema(
        str(paths.problem_dir),
        str(paths.vector_json),
        args=args,
        vector_output_path=str(paths.vector_json),
    )
    return {
        "status": "ok",
        "vector_json": str(paths.vector_json),
        "picture_count": len(payload.get("pictures", [])),
    }


def run_stage_c(paths: PipelinePaths, *, overwrite: bool = False) -> Dict[str, Any]:
    vector_path = paths.vector_json if paths.vector_json.exists() else None
    spec = generate_spec(
        paths.problem_dir,
        spec_path=paths.spec,
        vector_json_path=vector_path,
        overwrite=overwrite,
    )
    return {
        "status": spec.get("status", "draft"),
        "spec_path": str(paths.spec),
    }


def run_stage_d(paths: PipelinePaths, *, overwrite: bool = True) -> Dict[str, Any]:
    try:
        spec = solve_in_problem_dir(paths.problem_dir, overwrite=overwrite)
    except ValueError as exc:
        return {
            "status": "incomplete",
            "error": str(exc),
            "spec_path": str(paths.spec),
        }
    return {
        "status": spec.get("status", "solved"),
        "spec_path": str(paths.spec),
    }


def run_stage_e(paths: PipelinePaths, *, force: bool = False) -> Dict[str, Any]:
    return run_cas_codegen(
        paths.problem_dir,
        spec_path=paths.spec,
        ocr_json_path=paths.ocr_json,
        image_paths=None,
        force=force,
    )


def run_stage_f(paths: PipelinePaths, *, overwrite: bool = True) -> Dict[str, Any]:
    return run_cas_compute(
        paths.problem_dir,
        cas_jobs_path=paths.cas_jobs,
        output_path=paths.cas_results,
        overwrite=overwrite,
    )


def _load_cas_results(path: Path) -> List[CASResult]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    results: List[CASResult] = []
    for item in data:
        try:
            results.append(CASResult(**item))
        except Exception:
            continue
    return results


def run_stage_g(paths: PipelinePaths) -> Dict[str, Any]:
    if not paths.manim_draft.exists():
        raise FileNotFoundError("manim_draft.py missing – run cas_codegen first")

    manim_code = paths.manim_draft.read_text(encoding="utf-8")
    cas_results = _load_cas_results(paths.cas_results)
    final = fill_placeholders(manim_code, cas_results)
    paths.final_code.write_text(final.manim_code_final, encoding="utf-8")

    legacy_dir = Path("ManimcodeOutput") / paths.problem_name
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / f"{paths.problem_name}.py"
    legacy_file.write_text(final.manim_code_final, encoding="utf-8")

    return {
        "status": "rendered",
        "final_path": str(paths.final_code),
        "placeholders_remaining": contains_placeholder(final.manim_code_final),
    }


# --- Post-processing -------------------------------------------------------

def run_stage_h(paths: PipelinePaths) -> Optional[Dict[str, Any]]:
    return run_postproc_stage(paths.problem_name)
