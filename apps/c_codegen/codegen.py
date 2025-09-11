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
CONFIG_DIR = BASE_DIR / "configs"
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


def run_codegen(outputschema_path: str, image_paths: list[str], out_dir: str) -> str:
    """
    outputschema.json + 이미지들을 입력으로 GPT에 전달 → ManimCode + CAS-JOBS 출력
    """
    schema = json.load(open(outputschema_path, "r", encoding="utf-8"))
    system_prompt = load_system_prompt()

    # 이미지 base64 인코딩
    encoded_images = []
    for img in image_paths:
        if Path(img).exists():
            encoded_images.append({
                "path": str(img),
                "data": encode_image_to_base64(img)
            })

    # GPT 메시지 구성: 1) outputschema 전체 텍스트 2) 이미지 base64 3) system prompt(위)
    def _mime_for(path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext in [".png"]:
            return "image/png"
        if ext in [".jpg", ".jpeg", ".jpe"]:
            return "image/jpeg"
        return "image/*"

    user_parts = []
    user_parts.append({
        "type": "text",
        "text": (
            "아래는 LinearIR.v1 기반 outputschema.json과 문제 이미지들이다.\n"
            "출력은 ---CAS-JOBS--- 섹션(JSON 배열)과 Manim Scene 코드 1개(Scene=ManimCode)만 포함하라.\n\n"
            f"[outputschema.json]\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        ),
    })
    for img in encoded_images:
        mime = _mime_for(img.get("path", ""))
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{img['data']}"},
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
