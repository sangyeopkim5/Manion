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


def _generate_spec_for_single_image(image_index: int, vector_anchor_item: Dict[str, Any], crop_images: List[Path], paths: SpecPaths) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """개별 이미지에 대해 spec을 생성"""
    
    # .env에서 GPT API 키 읽기
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    cfg = _load_openai_config()
    client = OpenAI(api_key=api_key)

    # 해당 이미지의 crop 이미지 찾기
    target_crop_image = None
    if image_index < len(crop_images):
        target_crop_image = crop_images[image_index]
    
    # 사용자 메시지 구성
    user_content = [
        {"type": "text", "text": f"다음은 문제의 {image_index + 1}번째 이미지의 벡터 정보입니다. 이 정보를 바탕으로 geo_system_prompt에 따라 spec.json을 JSON 형태로 작성하세요. 다른 설명 없이 오직 schema만 반환하세요.\n\n[Vector Anchor - Image {image_index + 1}]\n" + json.dumps(vector_anchor_item, ensure_ascii=False, indent=2)}
    ]
    
    # 해당 이미지만 추가
    if target_crop_image:
        encoded_image = _encode_image(target_crop_image)
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
        "image_index": image_index
    }

def _generate_spec_via_llm(paths: SpecPaths) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    # vector_anchors.json 파일 찾기
    vector_path = paths.problem_dir / "vector_anchors.json"
    if not vector_path.exists():
        print(f"[c_geo_codegen] No vector_anchors.json found in {paths.problem_dir}")
        return None

    try:
        vector_data = _load_json(vector_path)
    except Exception:
        print(f"[c_geo_codegen] Failed to load vector_anchors.json")
        return None

    # crop된 이미지 찾기
    crop_images = _find_crop_images(paths.problem_dir)
    
    vector_anchors = vector_data.get("vector_anchors", [])
    if not vector_anchors:
        print(f"[c_geo_codegen] No vector anchors found in vector_anchors.json")
        return None
    
    # 각 이미지에 대해 개별적으로 spec 생성
    specs = []
    for i, vector_anchor_item in enumerate(vector_anchors):
        print(f"[c_geo_codegen] Generating spec for image {i + 1}/{len(vector_anchors)}")
        
        spec_result = _generate_spec_for_single_image(i, vector_anchor_item, crop_images, paths)
        if spec_result:
            spec_obj, meta = spec_result
            # 각 spec에 이미지 인덱스 정보 추가
            spec_obj["meta"] = spec_obj.get("meta", {})
            spec_obj["meta"]["image_index"] = i
            spec_obj["meta"]["image_path"] = vector_anchor_item.get("image_path", "")
            specs.append((spec_obj, meta))
        else:
            print(f"[c_geo_codegen] Failed to generate spec for image {i + 1}")
    
    if not specs:
        return None
    
    # 첫 번째 성공한 spec을 반환 (기존 인터페이스 유지)
    return specs[0]


def generate_specs_for_all_images(
    problem_dir: str | Path,
    *,
    overwrite: bool = False,
) -> List[Dict[str, Any]]:
    """모든 이미지에 대해 개별 spec.json 파일들을 생성"""
    
    problem_dir_path = Path(problem_dir).expanduser().resolve()
    paths = SpecPaths(problem_dir=problem_dir_path, spec_path=problem_dir_path / "spec.json")
    paths.problem_dir.mkdir(parents=True, exist_ok=True)

    # vector_anchors.json 파일 찾기
    vector_path = paths.problem_dir / "vector_anchors.json"
    if not vector_path.exists():
        print(f"[c_geo_codegen] No vector_anchors.json found in {paths.problem_dir}")
        return []

    try:
        vector_data = _load_json(vector_path)
    except Exception:
        print(f"[c_geo_codegen] Failed to load vector_anchors.json")
        return []

    # crop된 이미지 찾기
    crop_images = _find_crop_images(paths.problem_dir)
    
    vector_anchors = vector_data.get("vector_anchors", [])
    if not vector_anchors:
        print(f"[c_geo_codegen] No vector anchors found in vector_anchors.json")
        return []
    
    generated_specs = []
    
    # 각 이미지에 대해 개별적으로 spec 생성
    for i, vector_anchor_item in enumerate(vector_anchors):
        print(f"[c_geo_codegen] Generating spec for image {i + 1}/{len(vector_anchors)}")
        
        # 개별 spec 파일 경로
        spec_path = problem_dir_path / f"spec_{i}.json"
        
        # 이미 존재하고 overwrite가 False면 건너뛰기
        if spec_path.exists() and not overwrite:
            print(f"[c_geo_codegen] spec_{i}.json already exists, skipping")
            try:
                existing_spec = _load_json(spec_path)
                generated_specs.append(existing_spec)
                continue
            except Exception:
                print(f"[c_geo_codegen] Failed to load existing spec_{i}.json, regenerating")
        
        spec_result = _generate_spec_for_single_image(i, vector_anchor_item, crop_images, paths)
        if spec_result:
            spec_obj, meta = spec_result
            # 각 spec에 이미지 인덱스 정보 추가
            spec_obj["meta"] = spec_obj.get("meta", {})
            spec_obj["meta"]["image_index"] = i
            spec_obj["meta"]["image_path"] = vector_anchor_item.get("image_path", "")
            spec_obj["meta"]["created_at"] = datetime.utcnow().isoformat() + "Z"
            spec_obj["meta"]["generated_by"] = "llm"
            spec_obj["meta"]["llm"] = meta
            
            # 개별 spec 파일 저장
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            with spec_path.open("w", encoding="utf-8") as fh:
                json.dump(spec_obj, fh, ensure_ascii=False, indent=2)
            
            print(f"[c_geo_codegen] Generated spec_{i}.json")
            generated_specs.append(spec_obj)
        else:
            print(f"[c_geo_codegen] Failed to generate spec for image {i + 1}")
    
    return generated_specs

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
