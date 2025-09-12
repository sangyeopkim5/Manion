import sys
import json
import os
import re
import shutil
import traceback
from types import SimpleNamespace
from pathlib import Path
from typing import List, Dict

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from libs.schemas import ProblemDoc, CASJob, CASResult
from apps.b_graphsampling.builder import build_outputschema
from apps.c_codegen.codegen import run_codegen
from apps.d_cas.compute import run_cas
from apps.e_render.fill import fill_placeholders
from apps.a_ocr.dots_ocr.parser import DotsOCRParser


# --- helpers -----------------------------------------------------------------

def _strip_code_fences(s: str) -> str:
    """
    Remove leading and trailing markdown code fences (``` or ```python).
    This normalizes CodeGen output before extracting CAS-JOBS and code.
    """
    if not s:
        return s
    s = re.sub(r"^\s*```(?:python)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    return s

# --- CAS dependency resolution helpers --------------------------------------
_PLACEHOLDER_RE = re.compile(r"\[\[CAS:([A-Za-z0-9_\-]+)\]\]")

def _contains_placeholder(s: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(s or ""))

def _subst_placeholders(expr: str, got: Dict[str, CASResult]) -> str:
    def repl(m):
        _id = m.group(1)
        r = got.get(_id)
        if not r:
            # 아직 결과 없음 → 그대로 반환하여 다음 라운드에서 재시도
            return m.group(0)
        # CAS 내부 표현으로 치환 (안전하게 괄호로 감싸기)
        return f"({r.result_py})"
    return _PLACEHOLDER_RE.sub(repl, expr)

def _resolve_and_run_cas(jobs_raw: List[dict]) -> List[CASResult]:
    """
    1) 플레이스홀더 없는 원자 작업부터 실행
    2) 얻은 결과로 남은 작업의 target_expr에서 [[CAS:id]] 치환
    3) 더 이상 진행이 안되면 에러(순환/누락)
    """
    # id -> raw job 사전
    by_id: Dict[str, dict] = {}
    for j in jobs_raw:
        jid = str(j.get("id", "")).strip()
        if not jid:
            raise RuntimeError("CAS-JOBS에 id가 없습니다.")
        by_id[jid] = j

    remaining = set(by_id.keys())
    results: Dict[str, CASResult] = {}
    max_rounds = len(remaining) + 5

    for _ in range(max_rounds):
        # 1) 현재 라운드에 실행 가능한 job 선별(플레이스홀더가 없는 식)
        batch_ids: List[str] = []
        for jid in list(remaining):
            expr = by_id[jid].get("target_expr", "")
            expr_sub = _subst_placeholders(expr, results)
            by_id[jid]["_expr_sub"] = expr_sub  # 캐시
            if not _contains_placeholder(expr_sub):
                batch_ids.append(jid)

        if not batch_ids:
            # 진행 불가 → 아직 남아있다면 순환/누락
            if remaining:
                unresolved = []
                for jid in remaining:
                    expr_sub = by_id[jid].get("_expr_sub", by_id[jid].get("target_expr", ""))
                    unresolved.append({"id": jid, "target_expr": expr_sub})
                raise RuntimeError(f"CAS 의존성 해소 실패: {unresolved}")
            break

        # 2) 배치 실행 (compute.py는 CASJob.target_expr를 사용)
        batch_jobs: List[CASJob] = []
        for jid in batch_ids:
            src = by_id[jid]
            batch_jobs.append(CASJob(
                id=jid,
                task=src.get("task") or "simplify",
                target_expr=src.get("_expr_sub", src.get("target_expr", "")),
                variables=src.get("variables") or [],
                constraints=src.get("constraints") or [],
                assumptions=src.get("assumptions") or "default real domain",
            ))

        batch_res = run_cas(batch_jobs)

        # 3) 결과 저장 및 제거
        for r in batch_res:
            results[r.id] = r
            remaining.discard(r.id)

        if not remaining:
            break

    return list(results.values())

def _find_balanced_json_array(text: str, start_idx: int) -> str:
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
    CodeGen의 CAS-JOBS target_expr가 LaTeX 형태(\frac, \left..\right..)일 수 있으므로
    Sympy 파서가 이해할 수 있게 정규화한다.
    """
    if not s:
        return s
    # \left, \right 제거
    s = s.replace(r"\left", "").replace(r"\right", "")
    # \frac{a}{b} -> (a)/(b)
    s = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", s)
    # \pi -> pi 등: 역슬래시 제거(기본 심볼명은 sympy식)
    s = s.replace("\\", "")
    # 여백 정리
    return " ".join(s.split())


def _extract_jobs_and_code(code_text: str):
    """
    CodeGen 출력에서 ---CAS-JOBS--- JSON 배열을 추출하고,
    나머지(상단)의 Manim 코드를 분리해서 반환한다.
    - 코드펜스가 있어도 제거 후 처리
    - 마커 위치는 상/하 어디든 허용
    - 닫는 --- 없어도 대괄호 균형으로 JSON 배열만 안전 추출
    - JSON이 부분적으로 깨져도 salvage 시도
    """
    # 0) 코드펜스 제거
    code_text = _strip_code_fences(code_text)

    # 1) 마커 검색
    m = re.search(r"-{3}CAS-JOBS-{3}", code_text)
    if not m:
        raise RuntimeError("CAS-JOBS 섹션을 찾을 수 없습니다.")
    mark = m.start()

    # 2) 코드/꼬리 분리
    manim_code = code_text[:mark].strip()
    tail = code_text[mark + len("---CAS-JOBS---"):]

    # 3) 대괄호 균형으로 JSON 배열 추출
    json_text = _find_balanced_json_array(tail, 0)

    # 4) 표준 파싱, 실패 시 salvage
    try:
        jobs_raw = json.loads(json_text)
    except Exception:
        obj_pat = re.compile(r"\{[^{}]*?(\"task\"\s*:\s*\"[^\"]+\")[^{}]*?(\"target_expr\"\s*:\s*\"[^\"]+\")[^{}]*?\}", re.S)
        jobs_raw = []
        for mm in obj_pat.finditer(json_text):
            frag = re.sub(r",\s*(\}|$)", r"\1", mm.group(0))
            try:
                jobs_raw.append(json.loads(frag))
            except Exception:
                pass
        if not jobs_raw:
            raise RuntimeError("CAS-JOBS JSON 파싱 실패(수복 불가).")

    # 5) id 자동 부여 및 SymPy 정규화
    for idx, j in enumerate(jobs_raw, 1):
        j.setdefault("id", str(idx))
        j["target_expr"] = _normalize_expr_for_sympy(j.get("target_expr", ""))

    return jobs_raw, manim_code


# --- pipeline ----------------------------------------------------------------

def run_pipeline_with_ocr(image_path: str, problem_name: str = None) -> str:
    """
    OCR + End-to-end (로컬):
      1) OCR 처리 → JSON + 이미지
      2) Graphsampling → outputschema.json  
      3) CodeGen → ManimCode + ---CAS-JOBS---
      4) CAS 실행 → 결과
      5) placeholder 치환 → 최종 Manim 코드 저장 및 반환
    """
    if problem_name is None:
        problem_name = Path(image_path).stem
    
    # 0) 작업 디렉토리 구성
    output_root = Path("ManimcodeOutput")
    output_root.mkdir(exist_ok=True)
    problem_dir = output_root / problem_name
    problem_dir.mkdir(exist_ok=True)

    # 1) OCR 처리
    try:
        print(f"[e2e] Running OCR on: {image_path}", file=sys.stderr)
        ocr_parser = DotsOCRParser()
        ocr_results = ocr_parser.parse_file(
            input_path=image_path,
            output_dir=f"./temp_ocr_output/{problem_name}",
            prompt_mode="prompt_layout_all_en"
        )
        
        # OCR 결과에서 JSON과 이미지 경로 추출
        ocr_output_dir = f"./temp_ocr_output/{problem_name}/{problem_name}"
        json_files = [f for f in os.listdir(ocr_output_dir) if f.endswith('.json')]
        image_files = [f for f in os.listdir(ocr_output_dir) if f.endswith(('.jpg', '.png'))]
        
        if not json_files:
            raise FileNotFoundError("No JSON file found in OCR output")
        
        # OCR JSON을 problem_dir로 복사
        ocr_json_path = os.path.join(ocr_output_dir, json_files[0])
        dst_json_path = problem_dir / f"{problem_name}.json"
        shutil.copy2(ocr_json_path, dst_json_path)
        
        # OCR 이미지를 problem_dir로 복사
        if image_files:
            ocr_image_path = os.path.join(ocr_output_dir, image_files[0])
            dst_image_path = problem_dir / f"{problem_name}.jpg"
            shutil.copy2(ocr_image_path, dst_image_path)
            image_paths = [str(dst_image_path)]
        else:
            image_paths = []
        
        # crop된 이미지들도 복사 (picture-children이 있는 경우)
        crop_image_files = [f for f in os.listdir(ocr_output_dir) if f.endswith('.jpg') and '__pic_i' in f]
        crop_image_paths = []
        for crop_file in crop_image_files:
            src_crop_path = os.path.join(ocr_output_dir, crop_file)
            dst_crop_path = problem_dir / crop_file
            shutil.copy2(src_crop_path, dst_crop_path)
            crop_image_paths.append(str(dst_crop_path))
        
        print(f"[e2e] Found {len(crop_image_files)} crop images: {crop_image_files}", file=sys.stderr)

    except Exception as e:
        print(f"[ERROR] OCR failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)

    # 2) Picture 블록 확인 후 조건부 그래프샘플링
    try:
        # OCR JSON에서 Picture 블록이 있는지 확인
        from apps.c_codegen.codegen import has_picture_blocks
        has_pictures = has_picture_blocks(str(dst_json_path))
        
        if has_pictures:
            print("[e2e] Picture blocks detected - running b_graphsampling...", file=sys.stderr)
            # Picture가 있는 경우: b_graphsampling 실행
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
            if crop_image_paths:
                print(f"[e2e] Building outputschema.json for {len(crop_image_paths)} crop images...", file=sys.stderr)
                for crop_image_path in crop_image_paths:
                    crop_name = Path(crop_image_path).stem  # 예: "중1-2도형__pic_i0"
                    crop_outputschema_path = problem_dir / f"{crop_name}_outputschema.json"
                    
                    # crop 이미지를 위한 임시 디렉토리 생성
                    crop_temp_dir = problem_dir / f"temp_{crop_name}"
                    crop_temp_dir.mkdir(exist_ok=True)
                    
                    # crop 이미지를 임시 디렉토리로 복사
                    temp_crop_path = crop_temp_dir / f"{crop_name}.jpg"
                    shutil.copy2(crop_image_path, temp_crop_path)
                    
                    # 해당 crop에 대한 JSON이 있는지 확인하고 복사
                    crop_json_name = f"{crop_name}.json"
                    src_crop_json = Path(ocr_output_dir) / crop_json_name
                    if src_crop_json.exists():
                        dst_crop_json = crop_temp_dir / f"{crop_name}.json"
                        shutil.copy2(src_crop_json, dst_crop_json)
                    
                    try:
                        build_outputschema(str(crop_temp_dir), str(crop_outputschema_path), args=args)
                        print(f"[e2e] Crop outputschema created: {crop_outputschema_path}", file=sys.stderr)
                    except Exception as crop_e:
                        print(f"[WARN] Failed to create outputschema for crop {crop_name}: {crop_e}", file=sys.stderr)
                    finally:
                        # 임시 디렉토리 정리
                        shutil.rmtree(crop_temp_dir, ignore_errors=True)
        else:
            print("[e2e] No Picture blocks detected - skipping b_graphsampling", file=sys.stderr)
            # Picture가 없는 경우: b_graphsampling 스킵
            outputschema_path = problem_dir / "outputschema.json"
            # 빈 outputschema 파일 생성 (CodeGen에서 OCR JSON을 직접 사용)
            with open(outputschema_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)

    except Exception as e:
        print(f"[ERROR] GraphSampling failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)

    # 3) CodeGen (조건부: Picture 유무에 따라 다른 경로)
    try:
        print("[e2e] Running CodeGen...", file=sys.stderr)
        code_text = run_codegen(str(outputschema_path), image_paths, str(problem_dir), str(dst_json_path))
        if not code_text or not code_text.strip():
            print("[WARN] CodeGen produced empty code", file=sys.stderr)
            return ""
        print("[e2e] CodeGen OK", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Code generation failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)

    # 4) CAS-JOBS 추출 → CAS 실행
    try:
        jobs_raw, manim_code_draft = _extract_jobs_and_code(code_text)
        print(f"[e2e] Resolving and running CAS on {len(jobs_raw)} job(s)...", file=sys.stderr)
        cas_res = _resolve_and_run_cas(jobs_raw)
        print("[e2e] CAS OK", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] CAS computation failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)

    # 5) placeholder 치환 → 최종 코드 저장
    try:
        final = fill_placeholders(manim_code_draft, cas_res)
        manim_final = final.manim_code_final.strip()

        out_py = problem_dir / f"{problem_name}.py"
        with open(out_py, "w", encoding="utf-8") as f:
            f.write(manim_final)

        print(f"[e2e] Saved Manim code -> {out_py}", file=sys.stderr)
        return manim_final

    except Exception as e:
        print(f"[ERROR] Final render/save failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)


def run_pipeline(doc: ProblemDoc) -> str:
    """
    기존 End-to-end (로컬):
      1) Graphsampling → outputschema.json
      2) CodeGen → ManimCode + ---CAS-JOBS---
      3) CAS 실행 → 결과
      4) placeholder 치환 → 최종 Manim 코드 저장 및 반환
    """
    # 0) 작업 디렉토리 구성
    output_root = Path("ManimcodeOutput")
    output_root.mkdir(exist_ok=True)
    problem_name = Path(doc.image_path).stem if doc.image_path else "local"
    problem_dir = output_root / problem_name
    problem_dir.mkdir(exist_ok=True)

    # 1) 그래프샘플링 (입력 보관 + outputschema.json 생성)
    try:
        print("[e2e] Writing input.json...", file=sys.stderr)
        input_json_path = problem_dir / "input.json"
        with open(input_json_path, "w", encoding="utf-8") as f:
            json.dump([i.model_dump() for i in doc.items], f, ensure_ascii=False, indent=2)

        image_paths: List[str] = []
        if doc.image_path and os.path.isfile(doc.image_path):
            dst_image_path = problem_dir / Path(doc.image_path).name
            try:
                shutil.copy(doc.image_path, dst_image_path)
                image_paths.append(str(dst_image_path))
            except Exception:
                pass

        print("[e2e] Building outputschema.json (emit_anchors=True)...", file=sys.stderr)
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

    except Exception as e:
        print(f"[ERROR] GraphSampling failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)

    # 2) CodeGen (outputschema + 이미지 리스트)
    try:
        print("[e2e] Running CodeGen...", file=sys.stderr)
        code_text = run_codegen(str(outputschema_path), image_paths, str(problem_dir))
        if not code_text or not code_text.strip():
            print("[WARN] CodeGen produced empty code", file=sys.stderr)
            return ""
        print("[e2e] CodeGen OK", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Code generation failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)

    # 3) CAS-JOBS 추출 → CAS 실행
    try:
        jobs_raw, manim_code_draft = _extract_jobs_and_code(code_text)
        print(f"[e2e] Resolving and running CAS on {len(jobs_raw)} job(s)...", file=sys.stderr)
        cas_res = _resolve_and_run_cas(jobs_raw)
        print("[e2e] CAS OK", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] CAS computation failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)

    # 4) placeholder 치환 → 최종 코드 저장
    try:
        final = fill_placeholders(manim_code_draft, cas_res)
        manim_final = final.manim_code_final.strip()

        out_py = problem_dir / f"{problem_name}.py"
        with open(out_py, "w", encoding="utf-8") as f:
            f.write(manim_final)

        print(f"[e2e] Saved Manim code -> {out_py}", file=sys.stderr)
        return manim_final

    except Exception as e:
        print(f"[ERROR] Final render/save failed: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)


# --- cli ---------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipelines.e2e <image_path> [problem_name]", file=sys.stderr)
        print("       python -m pipelines.e2e <image_path> <json_path>  # 기존 방식", file=sys.stderr)
        sys.exit(2)

    img = sys.argv[1]
    
    # 새로운 OCR 방식 (이미지만 입력)
    if len(sys.argv) == 2 or (len(sys.argv) == 3 and not sys.argv[2].endswith('.json')):
        problem_name = sys.argv[2] if len(sys.argv) == 3 else None
        try:
            code = run_pipeline_with_ocr(img, problem_name)
            if code is None:
                print("[WARN] No code produced (None)", file=sys.stderr)
                sys.exit(1)
            if not code.strip():
                print("[WARN] Empty code produced", file=sys.stderr)
            print(code)
        except Exception as e:
            print(f"[ERROR] e2e with OCR failed: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            sys.exit(1)
    
    # 기존 방식 (이미지 + JSON)
    else:
        js = sys.argv[2]
        try:
            items = json.load(open(js, "r", encoding="utf-8"))
            doc = ProblemDoc(items=items, image_path=img)
            code = run_pipeline(doc)
            if code is None:
                print("[WARN] No code produced (None)", file=sys.stderr)
                sys.exit(1)
            if not code.strip():
                print("[WARN] Empty code produced", file=sys.stderr)
            print(code)
        except Exception as e:
            print(f"[ERROR] e2e main failed: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            sys.exit(1)
