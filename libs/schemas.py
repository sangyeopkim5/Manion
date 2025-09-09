from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class OCRItem(BaseModel):
    bbox: List[int]
    category: str
    text: Optional[str] = None


class ProblemDoc(BaseModel):
    items: List[OCRItem]
    image_path: Optional[str] = None


class CASJob(BaseModel):
    id: str
    task: str                      # evaluate | solve | factor | expand | geometry_check | probability
    target_expr: str               # 수식 문자열
    variables: Optional[List[str]] = []   # solve 등에서 필요한 변수 리스트
    constraints: Optional[List[str]] = [] # 선택적 제약조건
    assumptions: Optional[str] = "default real domain"  # 선택적 도메인 가정


class CASResult(BaseModel):
    id: str
    result_tex: str
    result_py: str


class CodegenJob(BaseModel):
    manim_code_draft: str
    cas_jobs: List[Dict[str, Any]]


class RenderInput(BaseModel):
    manim_code_draft: str
    replacements: List[CASResult]


class RenderOutput(BaseModel):
    manim_code_final: str
