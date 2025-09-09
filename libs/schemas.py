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
    expr: str


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

