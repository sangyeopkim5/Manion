from __future__ import annotations

import json
import os
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


def build_outputschema(problem_dir: str, output_path: str, args: Any | None = None) -> Dict[str, Any]:
    # 기존 a_ocr JSON 파일 찾기 (원본 JSON)
    json_files = [f for f in os.listdir(problem_dir) if f.endswith(".json") and "__pic_i" not in f]
    if not json_files:
        print("[WARN] No original OCR JSON found")
        return {}
    
    # 원본 JSON 로드
    original_json_path = os.path.join(problem_dir, json_files[0])
    with open(original_json_path, "r", encoding="utf-8") as f:
        original_data = json.load(f)
    
    # crop된 이미지 파일 찾기 (__pic_i 패턴, 순서대로)
    crop_images = []
    for f in os.listdir(problem_dir):
        if "__pic_i" in f and any(f.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
            crop_images.append(os.path.join(problem_dir, f))
    
    # 순서대로 정렬 (__pic_i0, __pic_i1, __pic_i2, ...)
    crop_images.sort(key=lambda x: int(x.split("__pic_i")[1].split(".")[0]) if "__pic_i" in x else 0)
    
    if not crop_images:
        print("[WARN] No crop images found for vectorization")
        return original_data
    
    # 첫 번째 crop 이미지만 사용
    crop_image = crop_images[0]
    print(f"[b_graphsampling] Using crop image: {crop_image}")
    
    # vector화 수행
    if args is not None and getattr(args, "emit_anchors", False):
        try:
            fw, fh = (14.0, 8.0)
            if hasattr(args, "frame") and isinstance(args.frame, str):
                parts = args.frame.lower().split("x")
                if len(parts) == 2:
                    fw = float(parts[0])
                    fh = float(parts[1])
            
            # crop된 이미지 전체를 vector화 (bbox 없이)
            anchor_item = build_anchor_item(
                image_path=crop_image,
                frame_w=fw,
                frame_h=fh,
                dpi=getattr(args, "dpi", 300),
                vectorizer=getattr(args, "vectorizer", "potrace"),
                points_per_path=getattr(args, "points_per_path", 600),
                crop_bbox=None,  # crop된 이미지 전체 사용
            )
            
            # Picture 블록 찾아서 vector_anchors 추가
            if isinstance(original_data, list):
                for item in original_data:
                    if isinstance(item, dict) and item.get("category") == "Picture":
                        item["vector_anchors"] = anchor_item
                        break
            
            # 수정된 원본 JSON을 원본 파일에 덮어쓰기
            with open(original_json_path, "w", encoding="utf-8") as f:
                json.dump(original_data, f, ensure_ascii=False, indent=2)
            
            print(f"[b_graphsampling] Added vector_anchors to {original_json_path}")
            return original_data
            
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"[anchor_ir] injection failed: {e}")
            return original_data
    
    return original_data


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
        ir = build_outputschema(target, out_path, args)
        print(f"Wrote {out_path} with {len(ir.get('reading_order', []))} items.")
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
            ir = build_outputschema(sd, out_path, args)
            print(f"Wrote {out_path} with {len(ir.get('reading_order', []))} items.")
            processed += 1
    if processed == 0:
        raise SystemExit("No problem directories with JSON found to process.")


if __name__ == "__main__":
    main()


