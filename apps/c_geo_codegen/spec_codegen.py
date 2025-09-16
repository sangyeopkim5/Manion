"""Utilities for creating and maintaining ``spec.json`` drafts."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import tomllib
from dotenv import load_dotenv
from openai import OpenAI

from pipelines.utils import strip_code_fences

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR.parent.parent / "configs"
SYSTEM_PROMPT_PATH = BASE_DIR / "geo_system_prompt.txt"

DEFAULT_BOX = {"min": [-6.0, -3.0], "max": [6.0, 3.0], "margin": 0.2}
DEFAULT_NOTES = [
    "Fill in the geometric constraints before running geo_compute.",
    "Set 'type' to a supported template (e.g. quad_diag2len2ang).",
]

load_dotenv()


@dataclass
class SpecPaths:
    """Canonical locations of geometry artefacts for a single problem."""

    problem_dir: Path
    spec_path: Path


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are a geometry spec assistant. Produce a JSON object describing the diagram."
    )


def _load_openai_config() -> Dict[str, Any]:
    cfg_path = CONFIG_DIR / "openai.toml"
    if not cfg_path.exists():
        return {"model": "gpt-4o-mini", "temperature": 0.0}
    with cfg_path.open("rb") as fh:
        cfg = tomllib.load(fh)
    section = cfg.get("geo_codegen") or cfg.get("default", {})
    return {
        "model": section.get("model", cfg.get("default", {}).get("model", "gpt-4o-mini")),
        "temperature": float(section.get("temperature", cfg.get("default", {}).get("temperature", 0.0))),
    }


def _default_spec_template() -> Dict[str, Any]:
    return {
        "type": "__TBD__",
        "seed": {},
        "angles": {},
        "lengths": {},
        "box": DEFAULT_BOX.copy(),
        "points": {},
        "scale": 1.0,
        "extras": [],
        "point_labels": {},
        "status": "draft",
        "meta": {
            "notes": list(DEFAULT_NOTES),
        },
    }




def _ensure_spec_shape(spec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        spec = {}
    spec.setdefault("type", "__TBD__")
    spec.setdefault("seed", {})
    spec.setdefault("angles", {})
    spec.setdefault("lengths", {})
    box = spec.get("box")
    if not isinstance(box, dict):
        box = DEFAULT_BOX.copy()
    else:
        box = {
            "min": list(box.get("min", DEFAULT_BOX["min"])),
            "max": list(box.get("max", DEFAULT_BOX["max"])),
            "margin": float(box.get("margin", DEFAULT_BOX["margin"])),
        }
    spec["box"] = box
    spec.setdefault("points", {})
    spec.setdefault("scale", 1.0)
    extras = spec.get("extras")
    spec["extras"] = extras if isinstance(extras, list) else []
    labels = spec.get("point_labels")
    spec["point_labels"] = labels if isinstance(labels, dict) else {}
    spec["status"] = spec.get("status") or "draft"
    meta = spec.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    notes = meta.get("notes")
    if not isinstance(notes, list) or not notes:
        meta["notes"] = list(DEFAULT_NOTES)
    spec["meta"] = meta
    return spec


def _encode_image(path: Path) -> Optional[Dict[str, str]]:
    """이미지를 base64로 인코딩하여 OpenAI API에 전송할 수 있는 형태로 변환"""
    if not path.exists():
        return None
    mime = "image/jpeg"
    ext = path.suffix.lower()
    if ext == ".png":
        mime = "image/png"
    try:
        data = base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        return None
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def _find_crop_images(problem_dir: Path) -> List[Path]:
    """crop된 이미지 파일들을 찾아서 반환"""
    crop_images = []
    for pattern in ["*__pic_i*.jpg", "*__pic_i*.png", "*__pic_i*.jpeg"]:
        crop_images.extend(sorted(problem_dir.glob(pattern)))
    return crop_images


def _generate_spec_via_llm(paths: SpecPaths) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    ocr_path = paths.problem_dir / "problem.json"
    if not ocr_path.exists():
        return None

    try:
        ocr_data = _load_json(ocr_path)
    except Exception:
        return None

    # .env에서 GPT API 키 읽기
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    cfg = _load_openai_config()
    client = OpenAI(api_key=api_key)

    # crop된 이미지 찾기
    crop_images = _find_crop_images(paths.problem_dir)
    
    # 사용자 메시지 구성
    user_content = [
        {"type": "text", "text": "다음은 문제의 OCR JSON입니다. 이 정보를 바탕으로 geo_system_prompt에 따라 spec.json을 JSON 형태로 작성하세요. 다른 설명 없이 오직 schema만 반환하세요.\n\n[OCR JSON]\n" + json.dumps(ocr_data, ensure_ascii=False, indent=2)}
    ]
    
    # crop된 이미지가 있으면 추가
    for crop_image in crop_images:
        encoded_image = _encode_image(crop_image)
        if encoded_image:
            user_content.append(encoded_image)

    messages = [
        {"role": "system", "content": load_system_prompt()},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat.completions.create(
            model=cfg.get("model", "gpt-4o-mini"),
            temperature=cfg.get("temperature", 0.0),
            messages=messages,
        )
    except Exception:
        return None

    content = response.choices[0].message.content or ""
    candidate_text = strip_code_fences(content).strip()
    
    # 그래프인 경우 빈 문자열이 반환됨
    if not candidate_text or candidate_text.strip() == "":
        return None
    
    try:
        spec_obj = json.loads(candidate_text)
    except Exception:
        return None

    if not isinstance(spec_obj, dict):
        return None

    return spec_obj, {
        "model": cfg.get("model"),
        "temperature": cfg.get("temperature"),
    }


def generate_spec(
    problem_dir: str | Path,
    *,
    spec_path: str | Path | None = None,
    overwrite: bool = False,
    template: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create or update ``spec.json`` for ``problem_dir``.

    When ``spec_path`` already exists the file is returned as-is unless
    ``overwrite`` is set to :data:`True`.  A companion ``spec.draft.json`` copy
    is produced the first time so that manual edits can be tracked separately.
    """

    problem_dir_path = Path(problem_dir).expanduser().resolve()
    if spec_path is None:
        spec_path = problem_dir_path / "spec.json"
    spec_path = Path(spec_path)

    paths = SpecPaths(problem_dir=problem_dir_path, spec_path=spec_path)
    paths.problem_dir.mkdir(parents=True, exist_ok=True)

    if paths.spec_path.exists() and not overwrite:
        return _load_json(paths.spec_path)

    llm_result: Optional[tuple[Dict[str, Any], Dict[str, Any]]] = None
    if not template:
        llm_result = _generate_spec_via_llm(paths)

    if template:
        spec = template.copy()
        llm_meta: Optional[Dict[str, Any]] = None
    elif llm_result:
        spec, llm_meta = llm_result
    else:
        spec = _default_spec_template()
        llm_meta = None

    spec = _ensure_spec_shape(spec)
    meta = spec.setdefault("meta", {})
    meta["created_at"] = datetime.utcnow().isoformat() + "Z"

    if llm_result:
        meta["generated_by"] = "llm"
        meta.setdefault("llm", {}).update(llm_meta or {})
    elif template:
        meta.setdefault("generated_by", "template")
    else:
        meta.setdefault("generated_by", "default")
    spec["status"] = "draft"

    paths.spec_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.spec_path.open("w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)

    return spec


def ensure_spec(
    problem_dir: str | Path,
    *,
    spec_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Idempotent helper used by orchestration code.

    ``ensure_spec`` will always return the current spec contents, creating a
    draft when the file does not yet exist.
    """

    problem_dir_path = Path(problem_dir)
    if spec_path is None:
        spec_path = problem_dir_path / "spec.json"
    spec_path = Path(spec_path)

    if spec_path.exists():
        return _load_json(spec_path)

    return generate_spec(
        problem_dir_path,
        spec_path=spec_path,
        overwrite=False,
    )
