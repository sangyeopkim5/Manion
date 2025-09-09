import re
import time
import base64
from tomllib import load
from pathlib import Path
from typing import List, Dict, Any
from openai import APIError, RateLimitError
from libs.tokens import get_openai_client
from libs.schemas import ProblemDoc, CodegenJob
from libs.layout import reading_order


CONFIGS = Path(__file__).parents[2] / "configs"
ROOT = Path(__file__).parents[2]


def _cfg():
    with open(CONFIGS / "openai.toml", "rb") as f:
        return load(f)


def _sys_text() -> str:
    # 루트의 system_prompt.txt 하나만 사용
    return (ROOT / "system_prompt.txt").read_text(encoding="utf-8")


def _build_messages(doc: ProblemDoc) -> List[Dict[str, Any]]:
    ocr_dump = [{"bbox": i.bbox, "category": i.category, "text": i.text} for i in doc.items]
    user_parts: List[Dict[str, Any]] = []
    if doc.image_path:
        try:
            img_bytes = Path(doc.image_path).read_bytes()
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            # OpenAI API는 "type": "image_url"을 사용하며, data URL 스키마로 base64 전달
            user_parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}})
        except OSError:
            pass
    user_text = "IMAGE_PATH: " + (doc.image_path or "N/A") + "\n\nOCR_JSON:\n" + str(ocr_dump)
    user_parts.append({"type": "text", "text": user_text})
    return [
        {"role": "system", "content": _sys_text()},
        {"role": "user", "content": user_parts},
    ]


def _chat_completion_with_retry(client, **kwargs):
    for i in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except (RateLimitError, APIError):
            if i == 2:
                raise
            time.sleep(2 ** i)


IMAGE_CATS = {"Formula", "Picture", "Diagram", "Graph", "Figure"}


def generate_manim(doc: ProblemDoc) -> CodegenJob:
    cfg = _cfg()
    client = get_openai_client()
    sorted_items = reading_order(list(doc.items))
    doc = ProblemDoc(items=sorted_items, image_path=doc.image_path)
    messages = _build_messages(doc)

    # GPT-5 모델에서는 max_completion_tokens 사용
    kwargs = {
        "model": cfg["models"]["codegen"],
        "messages": messages,
        "temperature": cfg["gen"]["temperature"],
    }
    
    # 모델별로 다른 파라미터 사용
    if "gpt-5" in cfg["models"]["codegen"]:
        kwargs["max_completion_tokens"] = cfg["gen"]["max_tokens"]
    else:
        kwargs["max_tokens"] = cfg["gen"]["max_tokens"]
    
    resp = _chat_completion_with_retry(
        client,
        **kwargs
    )
    text = resp.choices[0].message.content.strip()

    # "---CAS-JOBS---" 구분자가 없으면 CAS 작업이 없는 것으로 처리한다.
    if "---CAS-JOBS---" in text:
        manim_code, jobs_block = text.split("---CAS-JOBS---", 1)
    else:
        manim_code, jobs_block = text, ""
    
    # 코드 블록 마커 제거 (맨 처음과 맨 마지막만)
    manim_code = manim_code.strip()
    
    # 맨 처음 ```python 또는 ``` 제거
    if manim_code.startswith("```python"):
        manim_code = manim_code[9:]
    elif manim_code.startswith("```"):
        manim_code = manim_code[3:]
    
    # 맨 마지막 ``` 또는 ''' 제거 (중간의 마커는 보존)
    # 여러 줄로 구성된 코드에서 마지막 줄의 마커만 제거
    lines = manim_code.split('\n')
    if lines and lines[-1].strip() in ['```', "'''"]:
        lines = lines[:-1]
    manim_code = '\n'.join(lines)
    
    # 앞뒤 공백 제거
    manim_code = manim_code.strip()

    jobs = []
    for line in jobs_block.strip().splitlines():
        m = re.match(r"\[\[CAS:(?P<id>[A-Za-z0-9_]+):(?P<expr>.+)\]\]$", line.strip())
        if m:
            jobs.append({"id": m["id"], "expr": m["expr"]})

    def _strip_expr(match):
        return f"[[CAS:{match.group('id')}]]"

    draft = re.sub(
        r"\[\[CAS:(?P<id>[A-Za-z0-9_]+):(?P<expr>.*?)\]\]",
        _strip_expr,
        manim_code,
    )

    return CodegenJob(manim_code_draft=draft, cas_jobs=jobs)

