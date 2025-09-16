from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

try:
    from .router import route_from_boxes, route_from_dir
    from .anchor_ir import build_anchor_item
except ImportError:  # Fallback for direct script execution
    from router import route_from_boxes, route_from_dir
    from anchor_ir import build_anchor_item


def _infer_type_from_category(category: str) -> str:
    mapping = {
        "Text": "text",
        "List": "text",
        "List-item": "text",
        "Choice": "text",
        "Options": "text",
        "Picture": "image",
        # Extend as needed: Formula, Graph, Diagram, etc.
    }
    return mapping.get(category, "text")


def _extract_content(box: Dict[str, Any]) -> Any:
    # Prefer explicit text fields; otherwise, keep minimal content for the category
    if "text" in box and isinstance(box["text"], str):
        return box["text"].strip()
    if box.get("category") == "Picture":
        # For a picture box, we don't inline the image bytes here; we flag presence.
        return None
    return None


def parse_boxes_to_linear_ir(boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Minimal schema with reading_order, each entry has category, type, content
    reading_order: List[Dict[str, Any]] = []
    for b in boxes:
        category = b.get("category")
        if category is None:
            continue
        item_type = _infer_type_from_category(category)
        content = _extract_content(b)
        item = {
            "category": category,
            "type": item_type,
            "content": content,
        }
        # Preserve original bbox if provided in input boxes
        if isinstance(b, dict) and "bbox" in b:
            item["bbox"] = b.get("bbox")
        # Preserve all other fields from original box (including picture-children)
        for key, value in b.items():
            if key not in ["category", "bbox"]:
                item[key] = value
        reading_order.append(item)

    return {
        "schema": "LinearIR.v1",
        "reading_order": reading_order,
    }


def load_boxes_from_problem_dir(problem_dir: str) -> List[Dict[str, Any]]:
    json_files = [f for f in os.listdir(problem_dir) if f.lower().endswith(".json")]
    if not json_files:
        raise FileNotFoundError("No JSON file found in problem directory")
    json_path = os.path.join(problem_dir, json_files[0])
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Problem JSON must be a list of box dicts")
    return data  # list of boxes with bbox, category, text


def build_outputschema(
    problem_dir: str,
    output_path: str | None,
    args: Any | None = None,
    *,
    vector_output_path: str | None = None,
) -> Dict[str, Any]:
    """Generate vector anchors for every Picture block discovered in the OCR JSON.

    Historically this function injected the first crop image's anchors directly
    back into the OCR JSON.  The deterministic pipeline now requires the
    complete vectorisation result to be stored separately so that downstream
    geo stages can reason about the diagram independent from OCR text.  The
    behaviour is therefore extended as follows:

    * ``problem_dir`` is expected to contain the OCR outputs produced by
      :mod:`apps.a_ocr` – notably ``problem.json`` and optional crop images
      named ``problem__pic_i*.jpg``.
    * every ``Picture`` block receives a ``vector_anchors`` payload built via
      :func:`apps.b_graphsampling.anchor_ir.build_anchor_item`.
    * a consolidated ``problem_vector.json`` snapshot is written so that later
      stages can reference only the geometric information.

    The function still returns the patched OCR JSON object for backwards
    compatibility with older callers.
    """

    problem_dir_path = Path(problem_dir).expanduser().resolve()
    if not problem_dir_path.exists():
        raise FileNotFoundError(f"problem directory does not exist: {problem_dir}")

    json_files = sorted(
        [
            p
            for p in problem_dir_path.glob("*.json")
            if "__pic_i" not in p.name and not p.name.endswith("_vector.json")
        ]
    )
    if not json_files:
        raise FileNotFoundError(f"No OCR JSON found inside {problem_dir}")

    original_json_path = json_files[0]
    with original_json_path.open("r", encoding="utf-8") as f:
        original_data = json.load(f)

    crop_images = sorted(
        problem_dir_path.glob("*__pic_i*.jpg")
    )
    crop_images += sorted(problem_dir_path.glob("*__pic_i*.png"))
    crop_images += sorted(problem_dir_path.glob("*__pic_i*.jpeg"))

    picture_items: List[Dict[str, Any]] = []
    if isinstance(original_data, list):
        for entry in original_data:
            if isinstance(entry, dict) and entry.get("category") == "Picture":
                picture_items.append(entry)

    frame_w, frame_h = 14.0, 8.0
    if args is not None and hasattr(args, "frame") and isinstance(args.frame, str):
        parts = args.frame.lower().split("x")
        if len(parts) == 2:
            try:
                frame_w = float(parts[0])
                frame_h = float(parts[1])
            except ValueError:
                pass

    dpi = getattr(args, "dpi", 300) if args is not None else 300
    vectorizer = getattr(args, "vectorizer", "potrace") if args is not None else "potrace"
    points_per_path = getattr(args, "points_per_path", 600) if args is not None else 600

    vector_records: List[Dict[str, Any]] = []
    for idx, picture in enumerate(picture_items):
        crop_path = crop_images[idx] if idx < len(crop_images) else None
        if crop_path is None:
            print(f"[b_graphsampling] WARN: missing crop image for picture index {idx}")
            continue

        try:
            anchor_item = build_anchor_item(
                image_path=str(crop_path),
                frame_w=frame_w,
                frame_h=frame_h,
                dpi=dpi,
                vectorizer=vectorizer,
                points_per_path=points_per_path,
                crop_bbox=None,
            )
        except Exception as exc:  # pragma: no cover - diagnostic aid
            print(f"[b_graphsampling] WARN: failed to vectorise {crop_path}: {exc}")
            continue

        picture["vector_anchors"] = anchor_item
        vector_records.append(
            {
                "picture_index": idx,
                "picture_id": picture.get("id") or picture.get("uuid") or f"picture_{idx}",
                "image": Path(crop_path).name,
                "anchors": anchor_item,
            }
        )

    # Persist the patched OCR JSON so downstream stages read the enriched data.
    with original_json_path.open("w", encoding="utf-8") as f:
        json.dump(original_data, f, ensure_ascii=False, indent=2)

    vector_payload = {
        "problem": problem_dir_path.name,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "pictures": vector_records,
        "source_json": original_json_path.name,
        "vectorizer": vectorizer,
        "frame_size": [frame_w, frame_h],
        "dpi": dpi,
    }

    if vector_output_path is None and output_path:
        vector_output_path = Path(output_path)

    if vector_output_path is None:
        vector_output_path = problem_dir_path / f"{problem_dir_path.name}_vector.json"
    else:
        vector_output_path = Path(vector_output_path)

    vector_output_path.parent.mkdir(parents=True, exist_ok=True)
    with vector_output_path.open("w", encoding="utf-8") as f:
        json.dump(vector_payload, f, ensure_ascii=False, indent=2)

    vector_payload["path"] = str(vector_output_path)
    return vector_payload


def is_problem_dir(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    return any(f.lower().endswith(".json") for f in os.listdir(path))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build outputschema.json from a problem directory")
    parser.add_argument("problem_dir", help="Path to the problem directory containing JSON/MD/Image")
    parser.add_argument("--out", default=None, help="Output schema JSON path (defaults to parent/outputjson/<problem_name>.outputschema.json)")
    parser.add_argument("--emit-anchors", action="store_true", help="For Picture items, attach anchorIR (raster_with_anchors).")
    parser.add_argument("--points-per-path", type=int, default=600)
    parser.add_argument("--vectorizer", choices=["potrace","inkscape"], default="potrace")
    parser.add_argument("--frame", default="14x8", help="Manim frame size like 14x8")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--only-picture", action="store_true", help="reading_order를 Picture 항목만 남김")
    args = parser.parse_args()

    target = os.path.abspath(args.problem_dir)
    if is_problem_dir(target):
        out_path = args.out
        if out_path is None:
            base_name = os.path.basename(os.path.normpath(target))
            problem_parent = os.path.dirname(target)
            root_parent = os.path.dirname(problem_parent)
            out_dir = os.path.join(root_parent, "outputjson")
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{base_name}.outputschema.json")
        payload = build_outputschema(target, out_path, args)
        count = len(payload.get("pictures", []))
        print(f"Wrote {payload.get('path', out_path)} with {count} vector picture(s).")
        return

    # If not a single problem dir, process each subdirectory that contains a problem JSON
    subdirs = [os.path.join(target, d) for d in os.listdir(target) if os.path.isdir(os.path.join(target, d))]
    processed = 0
    for sd in subdirs:
        if is_problem_dir(sd):
            base_name = os.path.basename(os.path.normpath(sd))
            root_parent = os.path.dirname(target)
            out_dir = os.path.join(root_parent, "outputjson")
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{base_name}.outputschema.json")
            payload = build_outputschema(sd, out_path, args)
            count = len(payload.get("pictures", []))
            print(f"Wrote {payload.get('path', out_path)} with {count} vector picture(s).")
            processed += 1
    if processed == 0:
        raise SystemExit("No problem directories with JSON found to process.")


if __name__ == "__main__":
    main()


