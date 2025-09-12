import json
import re
import base64
import os
from pathlib import Path
from openai import OpenAI
import tomllib
from dotenv import load_dotenv

# ==============================
# 환경설정
# ==============================
BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR.parent.parent / "configs"
SYSTEM_PROMPT_PATH = BASE_DIR / "system_prompt.txt"

# .env 로드 (OPENAI_API_KEY 설정)
load_dotenv()

with open(CONFIG_DIR / "openai.toml", "rb") as f:
    openai_cfg = tomllib.load(f)
MODEL_NAME = openai_cfg.get("default", {}).get("model", "gpt-4o-mini")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a Manim+CAS code generator."


def encode_image_to_base64(image_path: str) -> str:
    """이미지를 base64로 인코딩"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def has_picture_blocks(ocr_json_path: str) -> bool:
    """
    OCR JSON에서 Picture 블록이 있는지 확인
    """
    try:
        with open(ocr_json_path, "r", encoding="utf-8") as f:
            ocr_data = json.load(f)
        
        if isinstance(ocr_data, list):
            for item in ocr_data:
                if item.get("category") == "Picture":
                    return True
        return False
    except Exception:
        return False


def get_crop_image_paths(problem_dir: str) -> list[str]:
    """
    crop된 이미지 경로들을 찾아서 반환
    """
    problem_path = Path(problem_dir)
    crop_images = []
    
    for img_file in problem_path.glob("*__pic_i*.jpg"):
        crop_images.append(str(img_file))
    
    return sorted(crop_images)


def run_codegen(outputschema_path: str, image_paths: list[str], out_dir: str, ocr_json_path: str = None) -> str:
    """
    Picture 유무에 따라 다른 경로로 GPT에 전달:
    1. Picture가 없는 경우: system_prompt + a_ocr JSON 바로 전달
    2. Picture가 있는 경우: system_prompt + b_graphsampling 결과 + crop 이미지들
    """
    system_prompt = load_system_prompt()
    
    # OCR JSON 경로가 제공되지 않으면 기본 경로에서 찾기
    if not ocr_json_path:
        problem_dir = Path(out_dir)
        problem_name = problem_dir.name
        ocr_json_path = str(problem_dir / f"{problem_name}.json")
    
    # Picture 블록이 있는지 확인
    has_pictures = has_picture_blocks(ocr_json_path)
    
    if has_pictures:
        print("[CodeGen] Picture blocks detected - using b_graphsampling + crop images")
        # 경로 2: Picture가 있는 경우 - b_graphsampling 결과 + crop 이미지들
        # outputschema_path 대신 ocr_json_path 사용 (1.json에 vector_anchors가 추가됨)
        schema = json.load(open(ocr_json_path, "r", encoding="utf-8"))
        
        # crop 이미지들 찾기
        crop_image_paths = get_crop_image_paths(out_dir)
        print(f"[CodeGen] Found {len(crop_image_paths)} crop images: {[Path(p).name for p in crop_image_paths]}")
        
        # 이미지 base64 인코딩 (crop 이미지들만)
        encoded_images = []
        for img in crop_image_paths:
            if Path(img).exists():
                encoded_images.append({
                    "path": str(img),
                    "data": encode_image_to_base64(img)
                })
        
        user_parts = []
        user_parts.append({
            "type": "text",
            "text": (
                "아래는 문제의.json과 crop된 이미지들이다.\n"
                "출력은 ---CAS-JOBS--- 섹션(JSON 배열)과 Manim Scene 코드 1개(Scene=ManimCode)만 포함하라.\n\n"
                f"[outputschema.json]\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            ),
        })
        
        # crop 이미지들 추가
        for img in encoded_images:
            mime = _mime_for(img.get("path", ""))
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{img['data']}"},
            })
    
    else:
        print("[CodeGen] No Picture blocks - using a_ocr JSON directly")
        # 경로 1: Picture가 없는 경우 - a_ocr JSON 바로 전달
        with open(ocr_json_path, "r", encoding="utf-8") as f:
            ocr_data = json.load(f)
        
        user_parts = []
        user_parts.append({
            "type": "text",
            "text": (
                "아래는 OCR 결과 JSON이다.\n"
                "출력은 ---CAS-JOBS--- 섹션(JSON 배열)과 Manim Scene 코드 1개(Scene=ManimCode)만 포함하라.\n\n"
                f"[OCR JSON]\n{json.dumps(ocr_data, ensure_ascii=False, indent=2)}\n\n"
            ),
        })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_parts},
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0,
    )

    code_text = response.choices[0].message.content

    # 코드펜스 제거: 맨 앞의 ``` 또는 ```python, 맨 뒤의 ``` 제거
    if code_text:
        code_text = re.sub(r"^\s*```(?:python)?\s*", "", code_text)
        code_text = re.sub(r"\s*```\s*$", "", code_text)

    # 저장
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "codegen_output.py"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(code_text)

    return code_text


def _mime_for(path: str) -> str:
    """이미지 파일의 MIME 타입 반환"""
    ext = Path(path).suffix.lower()
    if ext in [".png"]:
        return "image/png"
    if ext in [".jpg", ".jpeg", ".jpe"]:
        return "image/jpeg"
    return "image/*"
