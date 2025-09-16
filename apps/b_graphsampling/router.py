from typing import Dict, List, Dict as _Dict
import os


PICTURE_CATS = {"Picture"}
LIST_CATS = {"List", "List-item", "Choice", "Options"}


def route_problem(doc) -> Dict:
    """Route using a ProblemDoc-like object (duck-typed) that has .items with .category."""
    has_diagram = any(getattr(i, "category", None) in PICTURE_CATS for i in getattr(doc, "items", []))
    has_list = any(getattr(i, "category", None) in LIST_CATS for i in getattr(doc, "items", []))
    mode = "vision" if has_diagram else "text"
    return {"mode": mode, "has_diagram": has_diagram, "has_list": has_list}


def route_from_boxes(boxes: List[_Dict]) -> Dict:
    """Route directly from raw OCR/box items (dicts with 'category')."""
    categories = [b.get("category") for b in boxes if isinstance(b, dict)]
    has_diagram = any(c in PICTURE_CATS for c in categories)
    has_list = any(c in LIST_CATS for c in categories)
    mode = "vision" if has_diagram else "text"
    return {"mode": mode, "has_diagram": has_diagram, "has_list": has_list}


def route_from_dir(problem_dir: str) -> Dict:
    """Route from a problem directory by checking for image presence and known list categories.

    - If any image file exists (*.jpg, *.jpeg, *.png), treats as vision mode.
    - If JSON exists with boxes, uses it to refine list detection.
    """
    image_exts = {".jpg", ".jpeg", ".png"}
    has_diagram = any(os.path.splitext(f)[1].lower() in image_exts for f in os.listdir(problem_dir))
    # Try to detect list categories from JSON if present
    json_files = [f for f in os.listdir(problem_dir) if f.lower().endswith(".json")]
    has_list = False
    if json_files:
        import json
        json_path = os.path.join(problem_dir, json_files[0])
        try:
            with open(json_path, "r", encoding="utf-8") as jf:
                data = json.load(jf)
            if isinstance(data, list):
                cats = [d.get("category") for d in data if isinstance(d, dict)]
                has_list = any(c in LIST_CATS for c in cats)
        except Exception:
            pass
    mode = "vision" if has_diagram else "text"
    return {"mode": mode, "has_diagram": has_diagram, "has_list": has_list}

