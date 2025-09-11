"""GraphSampling builder stub.

This module bridges the OCR output (stage 1) and later stages by
transforming the OCR JSON and image into a simple `ProblemDoc` schema.
It currently performs minimal processing: it loads the OCR result and
stores it together with the image path as `outputschema.json`.

The function signature mimics the expected interface so that the
pipelines and server can call it without modification.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from libs.schemas import OCRItem, ProblemDoc


def _find_first(path: Path, pattern: str) -> Path | None:
    """Return the first file matching ``pattern`` inside ``path``."""
    files = list(path.glob(pattern))
    return files[0] if files else None


def build_outputschema(
    problem_dir: str | Path,
    output_path: str | Path,
    args: SimpleNamespace | None = None,
) -> None:
    """Build ``outputschema.json`` from OCR results.

    Parameters
    ----------
    problem_dir:
        Directory produced by stage 1 containing ``<name>.json`` and
        ``<name>.jpg``.
    output_path:
        Destination path for the generated ``outputschema.json``.
    args:
        Placeholder for future options (e.g., vectorizer settings). The
        current implementation does not make use of these arguments but
        keeps the signature for compatibility with the pipeline.
    """

    problem_dir = Path(problem_dir)
    problem_name = problem_dir.name

    # Locate JSON and image files inside the problem directory
    json_path = problem_dir / f"{problem_name}.json"
    if not json_path.exists():
        json_path = _find_first(problem_dir, "*.json")
    if not json_path or not json_path.exists():
        raise FileNotFoundError(f"OCR JSON not found in {problem_dir}")

    image_path = problem_dir / f"{problem_name}.jpg"
    if not image_path.exists():
        image_path = _find_first(problem_dir, "*.jpg")

    # Parse OCR items
    items_raw: list[dict[str, Any]] = json.loads(json_path.read_text(encoding="utf-8"))
    items = [OCRItem(**it) for it in items_raw]

    doc = ProblemDoc(
        items=items,
        image_path=str(image_path) if image_path and image_path.exists() else None,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(doc.dict(), f, ensure_ascii=False, indent=2)


__all__ = ["build_outputschema"]

