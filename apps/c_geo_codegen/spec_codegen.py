"""Utilities for creating and maintaining ``spec.json`` drafts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

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
    pictures = payload.get("pictures", []) if isinstance(payload, dict) else []
    summary["picture_count"] = len(pictures)
    summary["images"] = [p.get("image") for p in pictures if isinstance(p, dict)]
    if "vectorizer" in payload:
        summary["vectorizer"] = payload.get("vectorizer")
    if "frame_size" in payload:
        summary["frame_size"] = payload.get("frame_size")
    summary["source"] = vector_path.name
    return summary


def generate_spec(
    problem_dir: str | Path,
    *,
    spec_path: str | Path | None = None,
    vector_json_path: str | Path | None = None,
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

    vector_path = Path(vector_json_path).expanduser().resolve() if vector_json_path else None
    if vector_path and not vector_path.exists():
        vector_path = None

    paths = SpecPaths(problem_dir=problem_dir_path, spec_path=spec_path, vector_path=vector_path)
    paths.problem_dir.mkdir(parents=True, exist_ok=True)

    if paths.spec_path.exists() and not overwrite:
        return _load_json(paths.spec_path)

    spec = template.copy() if template else _default_spec_template()
    meta = spec.setdefault("meta", {})
    meta["created_at"] = datetime.utcnow().isoformat() + "Z"
    meta["vector_summary"] = _summarise_vector_payload(paths.vector_path)

    if paths.vector_path:
        meta["vector_json"] = str(paths.vector_path)
    spec["status"] = "draft"

    paths.spec_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.spec_path.open("w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)

    # Keep a pristine copy for manual iteration if we are creating from scratch.
    if not paths.draft_path.exists():
        with paths.draft_path.open("w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False, indent=2)

    return spec


def ensure_spec(
    problem_dir: str | Path,
    *,
    spec_path: str | Path | None = None,
    vector_json_path: str | Path | None = None,
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
        vector_json_path=vector_json_path,
        overwrite=False,
    )
