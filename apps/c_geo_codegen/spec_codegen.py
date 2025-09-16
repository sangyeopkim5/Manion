from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import tomllib
from dotenv import load_dotenv
from openai import OpenAI

from pipelines.utils import strip_code_fences

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = BASE_DIR / "geo_system_prompt.txt"
CONFIG_DIR = BASE_DIR.parent.parent / "configs"

DEFAULT_BOX = {"min": [-6.0, -3.0], "max": [6.0, 3.0], "margin": 0.2}


@dataclass
class SpecPaths:
    """Canonical locations of geometry artefacts for a single problem."""

    problem_dir: Path
    spec_path: Path
    vector_path: Optional[Path] = None

    @property
    def draft_path(self) -> Path:
        return self.problem_dir / "spec.draft.json"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


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
            "notes": [
                "Fill in the geometric constraints before running geo_compute.",
                "Set 'type' to a supported template (e.g. quad_diag2len2ang).",
            ]
        },
    }


def _summarise_vector_payload(vector_path: Optional[Path]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    if not vector_path or not vector_path.exists():
        return summary

    payload = _load_json(vector_path)
    if isinstance(payload, dict):
        pictures = payload.get("pictures", [])
        summary["picture_count"] = len(pictures)
        summary["images"] = [p.get("image") for p in pictures if isinstance(p, dict)]
        if "vectorizer" in payload:
            summary["vectorizer"] = payload.get("vectorizer")
        if "frame_size" in payload:
            summary["frame_size"] = payload.get("frame_size")
        summary["source"] = vector_path.name
    return summary


def _load_openai_config() -> Dict[str, Any]:
    cfg_path = CONFIG_DIR / "openai.toml"
    if not cfg_path.exists():
        return {"model": "gpt-4o-mini", "temperature": 0.0}
    with cfg_path.open("rb") as fh:
        cfg = tomllib.load(fh)
    section = cfg.get("geo_codegen", {})
    fallback = cfg.get("default", {})
    model = section.get("model") or fallback.get("model") or "gpt-4o-mini"
    temperature = section.get("temperature", fallback.get("temperature", 0.0))
    return {"model": model, "temperature": float(temperature)}


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You draft geometry specs for downstream deterministic solvers. "
        "Return valid JSON following the requested schema."
    )


def _encode_image(path: Path) -> Optional[Dict[str, Any]]:
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


def _gather_crop_images(problem_dir: Path) -> List[Path]:
    images: List[Path] = []
    images.extend(sorted(problem_dir.glob("*__pic_i*.jpg")))
    images.extend(sorted(problem_dir.glob("*__pic_i*.png")))
    return images


def _llm_generate_spec(
    *,
    client: OpenAI,
    model: str,
    temperature: float,
    vector_payload: Dict[str, Any],
    crop_images: Iterable[Path],
    existing_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_sections: List[str] = [
        "벡터화된 다이어그램 데이터를 참고하여 spec.json 초안을 작성하세요.",
        "다음 JSON 구조를 준수하세요: type, seed, angles, lengths, box, extras, point_labels, meta.",
        "좌표 계산은 하지 말고, planner가 사용할 수 있는 파라미터만 선언하세요.",
        "필요 시 seed, angle, length 값은 추정치로 제안하고 status는 'draft'로 두세요.",
        "[Vector JSON]\n" + json.dumps(vector_payload, ensure_ascii=False, indent=2),
    ]
    if existing_spec:
        user_sections.append("[현재 spec.json]\n" + json.dumps(existing_spec, ensure_ascii=False, indent=2))

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": [{"type": "text", "text": "\n\n".join(user_sections)}]},
    ]

    image_parts = [_encode_image(p) for p in crop_images]
    for part in image_parts:
        if part:
            messages[1]["content"].append(part)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    content = response.choices[0].message.content or ""
    return json.loads(strip_code_fences(content))


def _merge_with_template(spec_template: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = json.loads(json.dumps(spec_template))  # deep copy
    for key, value in update.items():
        if key == "meta" and isinstance(value, dict):
            meta = merged.setdefault("meta", {})
            meta.update(value)
        else:
            merged[key] = value
    merged.setdefault("status", "draft")
    return merged


def generate_spec(
    problem_dir: str | Path,
    *,
    spec_path: str | Path | None = None,
    vector_json_path: str | Path | None = None,
    overwrite: bool = False,
    template: Optional[Dict[str, Any]] = None,
    client: Optional[OpenAI] = None,
) -> Dict[str, Any]:
    """Create or update ``spec.json`` for ``problem_dir`` using an LLM draft when possible."""

    problem_dir_path = Path(problem_dir).expanduser().resolve()
    if spec_path is None:
        spec_path = problem_dir_path / "spec.json"
    spec_path = Path(spec_path)

    vector_path = Path(vector_json_path).expanduser().resolve() if vector_json_path else None
    if vector_path and not vector_path.exists():
        vector_path = None

    paths = SpecPaths(problem_dir=problem_dir_path, spec_path=spec_path, vector_path=vector_path)
    paths.problem_dir.mkdir(parents=True, exist_ok=True)

    existing_spec = _load_json(paths.spec_path) if paths.spec_path.exists() else None
    if existing_spec and not overwrite:
        return existing_spec

    spec_template = template.copy() if template else _default_spec_template()
    meta = spec_template.setdefault("meta", {})
    meta["created_at"] = datetime.utcnow().isoformat() + "Z"
    meta["vector_summary"] = _summarise_vector_payload(paths.vector_path)
    if paths.vector_path:
        meta["vector_json"] = str(paths.vector_path)

    vector_payload: Dict[str, Any] = {}
    if paths.vector_path and paths.vector_path.exists():
        try:
            vector_payload = _load_json(paths.vector_path)
        except Exception:
            vector_payload = {}

    crop_images = _gather_crop_images(paths.problem_dir)

    draft_spec: Optional[Dict[str, Any]] = None
    cfg = _load_openai_config()
    model = cfg.get("model", "gpt-4o-mini")
    temperature = cfg.get("temperature", 0.0)

    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            client = OpenAI(api_key=api_key)

    if client and vector_payload:
        try:
            llm_spec = _llm_generate_spec(
                client=client,
                model=model,
                temperature=temperature,
                vector_payload=vector_payload,
                crop_images=crop_images,
                existing_spec=existing_spec,
            )
            draft_spec = _merge_with_template(spec_template, llm_spec)
            draft_spec.setdefault("meta", {}).update({
                "generator": "llm",
                "llm_model": model,
            })
        except Exception as exc:
            meta.setdefault("notes", []).append(f"LLM draft failed: {exc}")
            draft_spec = None

    if draft_spec is None:
        draft_spec = spec_template
        draft_spec.setdefault("meta", {}).update({"generator": "template"})

    paths.spec_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.spec_path.open("w", encoding="utf-8") as fh:
        json.dump(draft_spec, fh, ensure_ascii=False, indent=2)

    if not paths.draft_path.exists():
        with paths.draft_path.open("w", encoding="utf-8") as fh:
            json.dump(draft_spec, fh, ensure_ascii=False, indent=2)

    return draft_spec


def ensure_spec(
    problem_dir: str | Path,
    *,
    spec_path: str | Path | None = None,
    vector_json_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Idempotent helper used by orchestration code."""

    problem_dir_path = Path(problem_dir)
    if spec_path is None:
        spec_path = problem_dir_path / "spec.json"
    spec_path = Path(spec_path)

    if spec_path.exists():
        return _load_json(spec_path)

    return generate_spec(
        problem_dir_path,
        spec_path=spec_path,
        vector_json_path=vector_json_path,
        overwrite=False,
    )
