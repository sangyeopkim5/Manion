from fastapi import FastAPI, APIRouter, HTTPException
from typing import List
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
import os
import re
import json
import shutil

from dotenv import load_dotenv

from libs.schemas import ProblemDoc, CASJob
from apps.b_graphsampling.builder import build_outputschema
from apps.c_codegen.codegen import run_codegen
from apps.d_cas.compute import run_cas
from apps.e_render.fill import fill_placeholders
from apps.a_ocr.dots_ocr.parser import DotsOCRParser

load_dotenv()

app = FastAPI(title="Manion-CAS")

# ------------------------------ Helpers ------------------------------

def _strip_code_fences(s: str) -> str:
    """GPT가 붙일 수 있는 ```python / ``` 코드펜스 제거."""
    s = re.sub(r'^\s*```(?:python)?\s*', '', s)
    s = re.sub(r'\s*```\s*$', '', s)
    return s

def _find_balanced_json_array(text: str, start_idx: int) -> str:
    """
    text[start_idx:]에서 첫 '['부터 짝이 맞는 ']'까지의 JSON 배열 슬라이스를 반환.
    (닫는 --- 마커가 없어도 안전)
    """
    i = text.find("[", start_idx)
    if i == -1:
        raise RuntimeError("CAS-JOBS JSON 배열 시작 '['를 찾지 못했습니다.")
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[i:j+1]
    raise RuntimeError("대괄호 균형이 맞는 JSON 배열 끝을 찾지 못했습니다.")

def _normalize_expr_for_sympy(s: str) -> str:
    """
    LaTeX 스타일(\frac, \left..\right..) → SymPy 친화 표기.
    system_prompt가 대부분 정리해주지만 혹시 남은 이스케이프/제어문자를 마무리 정리.
    """
    if not s:
        return s
    s = s.replace("\\\\", "\\")              # 이중 백슬래시 축소
    s = s.replace(r"\left", "").replace(r"\right", "")
    s = re.sub(r"\\frac\s*\{\s*([^{}]+?)\s*\}\s*\{\s*([^{}]+?)\s*\}", r"(\1)/(\2)", s)
    s = " ".join(s.split())                  # 공백/개행 정리
    s = s.replace("\\", "")                  # 남은 백슬래시 제거
    return s

def _extract_jobs_and_code(code_text: str):
    """
    CodeGen 출력에서 Manim 코드와 ---CAS-JOBS--- JSON을 분리.
    - 코드펜스 허용(제거)
    - JSON 뒤에 잡텍스트가 있어도 허용
    - JSON이 일부 깨졌을 경우 salvage 시도(유효 객체만 추출)
    """
    # 0) 코드펜스 제거
    code_text = _strip_code_fences(code_text)

    # 1) 마커 찾기 (위/아래 어디든 허용)
    m = re.search(r"-{3}CAS-JOBS-{3}", code_text)
    if not m:
        raise RuntimeError("CAS-JOBS 섹션을 찾을 수 없습니다.")
    mark = m.start()

    # 2) Manim 코드(마커 앞)와 tail(마커 뒤) 분리
    manim_code = code_text[:mark].strip()
    tail = code_text[mark + len("---CAS-JOBS---"):]

    # 3) 균형 매칭으로 JSON 배열만 안전 추출
    json_text = _find_balanced_json_array(tail, 0)

    # 4) 표준 파싱 시도
    try:
        jobs_raw = json.loads(json_text)
    except Exception:
        # 5) salvage: 개별 객체를 느슨히 추출하여 유효한 것만 사용
        obj_pat = re.compile(
            r"\{[^{}]*?(\"id\"\s*:\s*\"[^\"]+\")[^{}]*?(\"task\"\s*:\s*\"[^\"]+\")[^{}]*?(\"target_expr\"\s*:\s*\"[^\"]+\")[^{}]*?\}",
            re.S,
        )
        jobs_raw = []
        for mm in obj_pat.finditer(json_text):
            frag = re.sub(r",\s*(\}|$)", r"\1", mm.group(0))
            try:
                jobs_raw.append(json.loads(frag))
            except Exception:
                pass
        if not jobs_raw:
            raise RuntimeError("CAS-JOBS JSON 파싱 실패(수복 불가).")

    # 6) id/표기 정리
    for j in jobs_raw:
        if "id" not in j or not str(j["id"]).strip():
            # 만약 id가 없다면 시스템이 자동부여(프롬프트상 강제되지만 혹시 모를 경우)
            j["id"] = f"S{len(jobs_raw)}"
        j["target_expr"] = _normalize_expr_for_sympy(j.get("target_expr", ""))

    return jobs_raw, manim_code

def _pretty_results(jobs_raw: list, cas_res: list):
    out = []
    # id 매칭 사전을 만들어 안정적으로 매핑
    res_by_id = {r.id: r for r in cas_res}
    for j in jobs_raw:
        r = res_by_id.get(j.get("id"))
        if r is None:
            continue
        out.append({
            "id": j.get("id", ""),
            "task": j.get("task", ""),
            "expr": j.get("target_expr", ""),
            "result": r.result_py
        })
    return out

def _save_outputs(problem_dir: Path, problem_name: str, manim_code_final: str):
    # 코드 저장
    manim_file = problem_dir / f"{problem_name}.py"
    with open(manim_file, "w", encoding="utf-8") as f:
        f.write(manim_code_final)

    # 실행 안내 README 저장/갱신
    readme_file = problem_dir / "README.md"
    with open(readme_file, "w", encoding="utf-8") as f:
        f.write(f"# {problem_name} Manim Code\n\n")
        f.write("## 실행 방법\n\n")
        f.write(f"1. Manim 설치: `pip install manim`\n")
        f.write(f"2. 코드 실행: `manim {problem_name}.py -pql`\n")
        f.write("   - `-p`: 완료 후 자동 재생\n")
        f.write("   - `-q`: 품질 설정 (l=low, m=medium, h=high)\n")
        f.write("   - `-l`: 라이브 프리뷰\n\n")
        f.write("## 생성 시간\n")
        f.write(f"- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


# ------------------------------ Routers ------------------------------

codegen_router = APIRouter(prefix="/codegen", tags=["codegen"])

@codegen_router.post("/generate")
def generate_endpoint(doc: ProblemDoc):
    """
    outputschema.json + image → GPT 호출 → (ManimCode + ---CAS-JOBS---) → CAS → [[CAS:id]] 치환 → 최종 코드 저장
    """
    try:
        # 작업 디렉토리 준비
        output_dir = Path("ManimcodeOutput")
        output_dir.mkdir(exist_ok=True)
        problem_name = Path(doc.image_path).stem if doc.image_path else "unknown"
        problem_dir = output_dir / problem_name
        problem_dir.mkdir(exist_ok=True)

        # input.json 저장
        input_json_path = problem_dir / "input.json"
        with open(input_json_path, "w", encoding="utf-8") as f:
            json.dump([i.model_dump() for i in doc.items], f, ensure_ascii=False, indent=2)

        # 이미지 복사
        image_paths = []
        if doc.image_path and os.path.isfile(doc.image_path):
            dst_image_path = problem_dir / Path(doc.image_path).name
            try:
                shutil.copy(doc.image_path, dst_image_path)
                image_paths.append(str(dst_image_path))
            except Exception:
                pass

        # Picture 블록 확인 후 조건부 그래프샘플링
        from apps.c_codegen.codegen import has_picture_blocks
        problem_name = problem_dir.name
        ocr_json_path = problem_dir / f"{problem_name}.json"
        
        if not ocr_json_path.exists():
            # JSON 파일을 찾을 수 없으면 첫 번째 JSON 파일 사용
            json_files = list(problem_dir.glob("*.json"))
            if json_files:
                ocr_json_path = json_files[0]
            else:
                raise FileNotFoundError(f"No JSON file found in {problem_dir}")
        
        has_pictures = has_picture_blocks(str(ocr_json_path))
        
        if has_pictures:
            print("[server] Picture blocks detected - running b_graphsampling...")
            # outputschema 생성 (emit anchors)
            outputschema_path = problem_dir / "outputschema.json"
            args = SimpleNamespace(
                emit_anchors=True,
                frame="14x8",
                dpi=300,
                vectorizer="potrace",
                points_per_path=600,
                only_picture=False,
            )
            build_outputschema(str(problem_dir), str(outputschema_path), args=args)
            
            # crop된 이미지들에 대해서도 그래프샘플링 수행
            crop_image_files = [f for f in os.listdir(problem_dir) if f.endswith('.jpg') and '__pic_i' in f]
            if crop_image_files:
                print(f"[server] Found {len(crop_image_files)} crop images, processing with GraphSampling...")
                
                for crop_file in crop_image_files:
                    crop_name = Path(crop_file).stem  # 예: "중1-2도형__pic_i0"
                    crop_outputschema_path = problem_dir / f"{crop_name}_outputschema.json"
                    
                    # crop 이미지를 위한 임시 디렉토리 생성
                    crop_temp_dir = problem_dir / f"temp_{crop_name}"
                    crop_temp_dir.mkdir(exist_ok=True)
                    
                    # crop 이미지를 임시 디렉토리로 복사
                    src_crop_path = problem_dir / crop_file
                    temp_crop_path = crop_temp_dir / f"{crop_name}.jpg"
                    shutil.copy2(src_crop_path, temp_crop_path)
                    
                    # 해당 crop에 대한 JSON이 있는지 확인하고 복사
                    crop_json_name = f"{crop_name}.json"
                    src_crop_json = problem_dir / crop_json_name
                    if src_crop_json.exists():
                        dst_crop_json = crop_temp_dir / f"{crop_name}.json"
                        shutil.copy2(src_crop_json, dst_crop_json)
                    
                    try:
                        build_outputschema(str(crop_temp_dir), str(crop_outputschema_path), args=args)
                        print(f"[server] Crop outputschema created: {crop_outputschema_path}")
                    except Exception as crop_e:
                        print(f"[server] WARN: Failed to create outputschema for crop {crop_name}: {crop_e}")
                    finally:
                        # 임시 디렉토리 정리
                        shutil.rmtree(crop_temp_dir, ignore_errors=True)
        else:
            print("[server] No Picture blocks detected - skipping b_graphsampling")
            # Picture가 없는 경우: 빈 outputschema 파일 생성
            outputschema_path = problem_dir / "outputschema.json"
            with open(outputschema_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)

        # CodeGen 실행 (조건부: Picture 유무에 따라 다른 경로)
        code_text = run_codegen(str(outputschema_path), image_paths, str(problem_dir), str(ocr_json_path))

        # CAS-JOBS + Manim 코드 분리
        jobs_raw, manim_code_draft = _extract_jobs_and_code(code_text)

        # CAS 실행
        jobs = [CASJob(**j) for j in jobs_raw]
        cas_res = run_cas(jobs)

        # [[CAS:id]] 치환
        filled = fill_placeholders(manim_code_draft, cas_res)
        manim_code_final = filled.manim_code_final.strip()

        # 저장
        _save_outputs(problem_dir, problem_name, manim_code_final)

        # 사람이 읽기 쉬운 요약
        cas_results_pretty = _pretty_results(jobs_raw, cas_res)

        return {
            "status": "ok",
            "cas_results": cas_results_pretty,
            "manim_code": manim_code_final[:800]  # 미리보기
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


cas_router = APIRouter(prefix="/cas", tags=["cas"])

@cas_router.post("/run")
def cas_endpoint(jobs: List[CASJob]):
    try:
        return run_cas(jobs)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# Mount
app.include_router(codegen_router)
app.include_router(cas_router)

@app.post("/e2e")
def e2e(doc: ProblemDoc):
    """
    End-to-End 실행:
    Graphsampling → CodeGen → CAS → [[CAS:id]] 치환 → ManimCode 저장
    """
    return generate_endpoint(doc)

@app.post("/e2e_with_ocr")
def e2e_with_ocr(image_path: str, problem_name: str = None):
    """
    OCR + End-to-End 실행:
    OCR → Graphsampling → CodeGen → CAS → [[CAS:id]] 치환 → ManimCode 저장
    """
    try:
        from pipelines.e2e import run_pipeline_with_ocr
        
        # 통합 파이프라인 실행
        result = run_pipeline_with_ocr(image_path, problem_name)
        
        return {
            "status": "ok",
            "message": "OCR + E2E pipeline completed successfully",
            "result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Manion-CAS API Server"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
