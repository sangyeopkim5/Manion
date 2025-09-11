#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Two-pass OCR pipeline (minimal, fixed):

1. Pass1: dots.ocr with prompt_layout_all_en on the full original image.
   → produces <stem>.json / <stem>.md / <stem>.jpg

2. Pass2: For each Picture block in Pass1 JSON:
   → crop the bbox region from the ORIGINAL input image
   → run dots.ocr again on the crop with prompt_layout_all_en
   → take all Text/Formula blocks, convert to PictureText
   → insert as "picture-children" inside the Picture block

3. Save merged JSON back to <stem>.json (overwriting Pass1 JSON).
   .md and .jpg remain from Pass1.
   Crop images (<stem>__pic_i{n}.jpg) are saved for inspection.
"""

import argparse, json, os, shutil
from pathlib import Path
from typing import Any, Dict, List
from PIL import Image
from dots_ocr.parser import DotsOCRParser


# ---------- utils ----------
def _read_json(p: str):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_json(p: str, obj: Any):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _crop_save(original_img: str, bbox: List[int], save_path: str):
    """Crop bbox from the ORIGINAL input image and save."""
    x1, y1, x2, y2 = map(int, bbox)
    im = Image.open(original_img).convert("RGB")
    crop = im.crop((x1, y1, x2, y2))
    crop.save(save_path, quality=95)

def _blocks_to_children(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Text/Formula blocks to PictureText children."""
    children = []
    for b in blocks:
        if b.get("category") in ("Text", "Formula"):
            t = b.get("text", "").strip()
            if t:
                children.append({"category": "PictureText", "text": t})
    return children


# ---------- pipeline ----------
def run_pipeline(parser: "DotsOCRParser", input_path: str):
    # Pass1: full image
    results = parser.parse_file(input_path, prompt_mode="prompt_layout_all_en")

    for res in results:
        layout_json = res.get("layout_info_path")
        if not layout_json or not os.path.exists(layout_json):
            continue

        page_dir  = Path(layout_json).parent
        page_stem = Path(layout_json).stem
        blocks    = _read_json(layout_json)
        if not isinstance(blocks, list):
            continue

        changed = False

        for idx, blk in enumerate(blocks):
            if blk.get("category") != "Picture":
                continue
            bbox = blk.get("bbox")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                continue

            # crop from ORIGINAL input image
            crop_jpg = page_dir / f"{page_stem}__pic_i{idx}.jpg"
            _crop_save(input_path, bbox, str(crop_jpg))

            # run dots.ocr again on the crop with layout_all_en
            tmp_out = page_dir / f"__tmp_pic_i{idx}"
            tmp_parser = DotsOCRParser(
                output_dir=str(tmp_out),
                ip=parser.ip, port=parser.port, model_name=parser.model_name,
                temperature=parser.temperature, top_p=parser.top_p,
                max_completion_tokens=parser.max_completion_tokens,
                num_thread=parser.num_thread, dpi=parser.dpi,
                min_pixels=parser.min_pixels, max_pixels=parser.max_pixels,
                use_hf=parser.use_hf,
            )
            sec = tmp_parser.parse_file(str(crop_jpg), prompt_mode="prompt_layout_all_en")
            sec_json = sec and isinstance(sec, list) and sec[0].get("layout_info_path")
            children = _blocks_to_children(_read_json(sec_json)) if (sec_json and os.path.exists(sec_json)) else []

            shutil.rmtree(tmp_out, ignore_errors=True)

            if children:
                blk["picture-children"] = children
                changed = True

        if changed:
            _write_json(layout_json, blocks)

    return results


def main():
    ap = argparse.ArgumentParser(description="Two-pass OCR with layout_all_en for both passes, merging Picture children.")
    ap.add_argument("input_path", type=str, help="Input image/PDF path")
    ap.add_argument("--output", type=str, default="./output")
    ap.add_argument("--ip", type=str, default="localhost")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--model_name", type=str, default="model")
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument("--top_p", type=float, default=1.0)
    ap.add_argument("--max_completion_tokens", type=int, default=16384)
    ap.add_argument("--num_thread", type=int, default=16)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--min_pixels", type=int, default=None)
    ap.add_argument("--max_pixels", type=int, default=None)
    ap.add_argument("--use_hf", action="store_true")
    args = ap.parse_args()

    parser = DotsOCRParser(
        output_dir=args.output,
        ip=args.ip, port=args.port, model_name=args.model_name,
        temperature=args.temperature, top_p=args.top_p,
        max_completion_tokens=args.max_completion_tokens,
        num_thread=args.num_thread, dpi=args.dpi,
        min_pixels=args.min_pixels, max_pixels=args.max_pixels,
        use_hf=args.use_hf,
    )
    run_pipeline(parser, args.input_path)


if __name__ == "__main__":
    main()