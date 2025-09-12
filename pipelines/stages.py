"""
개별 단계별 실행 모듈
각 단계를 독립적으로 실행할 수 있는 함수들
"""
import os
import sys
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Any, Optional

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from libs.schemas import ProblemDoc, CASJob, CASResult
from apps.a_ocr.dots_ocr.parser import DotsOCRParser
from apps.a_ocr.tools.picture_ocr_pipeline import run_pipeline as run_picture_ocr_pipeline
from apps.b_graphsampling.builder import build_outputschema
from apps.c_codegen.codegen import run_codegen
from apps.d_cas.compute import run_cas
from apps.e_render.fill import fill_placeholders


def stage1_ocr(image_path: str, output_dir: str = "./temp_ocr_output", problem_name: str = None) -> str:
    """
    Stage 1: OCR 처리
    이미지를 OCR 처리하여 JSON과 이미지 출력
    
    Args:
        image_path: 입력 이미지 경로
        output_dir: 출력 디렉토리
        problem_name: 문제 이름
        
    Returns:
        str: OCR 출력 디렉토리 경로
    """
    if problem_name is None:
        problem_name = Path(image_path).stem
    
    print(f"[Stage 1] Running OCR on: {image_path}")
    
    try:
        ocr_parser = DotsOCRParser(output_dir=output_dir)
        ocr_results = run_picture_ocr_pipeline(
            parser=ocr_parser,
            input_path=image_path
        )
        
        ocr_output_dir = f"{output_dir}/{problem_name}/{problem_name}"
        print(f"[Stage 1] OCR completed. Output: {ocr_output_dir}")
        return ocr_output_dir
        
    except Exception as e:
        print(f"[Stage 1] OCR failed: {e}")
        raise


def stage2_graphsampling(problem_dir: str, output_path: str = None) -> str:
    """
    Stage 2: GraphSampling 처리 (조건부)
    OCR JSON에서 Picture 블록이 있는지 확인 후 조건부로 실행
    crop된 이미지들에 대해서도 그래프샘플링 수행
    
    Args:
        problem_dir: 문제 디렉토리 (JSON과 이미지 포함)
        output_path: 출력 스키마 경로
        
    Returns:
        str: outputschema.json 경로
    """
    if output_path is None:
        output_path = os.path.join(problem_dir, "outputschema.json")
    
    print(f"[Stage 2] Checking Picture blocks in: {problem_dir}")
    
    try:
        # Picture 블록이 있는지 확인
        from apps.c_codegen.codegen import has_picture_blocks
        problem_dir_path = Path(problem_dir)
        problem_name = problem_dir_path.name
        ocr_json_path = problem_dir_path / f"{problem_name}.json"
        
        if not ocr_json_path.exists():
            # JSON 파일을 찾을 수 없으면 첫 번째 JSON 파일 사용
            json_files = list(problem_dir_path.glob("*.json"))
            if json_files:
                ocr_json_path = json_files[0]
            else:
                raise FileNotFoundError(f"No JSON file found in {problem_dir}")
        
        has_pictures = has_picture_blocks(str(ocr_json_path))
        
        if has_pictures:
            print(f"[Stage 2] Picture blocks detected - running b_graphsampling...")
            # Picture가 있는 경우: b_graphsampling 실행
            args = SimpleNamespace(
                emit_anchors=True,
                frame="14x8",
                dpi=300,
                vectorizer="potrace",
                points_per_path=600,
                only_picture=False,
            )
            
            # b_graphsampling: 기존 JSON에 vector_anchors 추가
            build_outputschema(problem_dir, output_path, args=args)
            print(f"[Stage 2] GraphSampling completed. Vector anchors added to original JSON.")
        else:
            print(f"[Stage 2] No Picture blocks detected - skipping b_graphsampling")
            # Picture가 없는 경우: 빈 outputschema 파일 생성
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)
        
        return output_path
        
    except Exception as e:
        print(f"[Stage 2] GraphSampling failed: {e}")
        raise


def stage3_codegen(outputschema_path: str, image_paths: List[str], output_dir: str, ocr_json_path: str = None) -> str:
    """
    Stage 3: CodeGen 처리 (조건부)
    Picture 유무에 따라 다른 경로로 GPT에 전달
    
    Args:
        outputschema_path: outputschema.json 경로
        image_paths: 이미지 경로 리스트
        output_dir: 출력 디렉토리
        ocr_json_path: OCR JSON 경로 (선택사항)
        
    Returns:
        str: 생성된 코드 텍스트
    """
    print(f"[Stage 3] Running CodeGen...")
    
    try:
        # OCR JSON 경로가 제공되지 않으면 기본 경로에서 찾기
        if not ocr_json_path:
            output_dir_path = Path(output_dir)
            problem_name = output_dir_path.name
            ocr_json_path = str(output_dir_path / f"{problem_name}.json")
        
        # b_graphsampling에서 1.json에 vector_anchors를 추가했으므로, 1.json을 직접 사용
        code_text = run_codegen(ocr_json_path, image_paths, output_dir, ocr_json_path)
        if not code_text or not code_text.strip():
            raise ValueError("CodeGen produced empty code")
        
        print(f"[Stage 3] CodeGen completed")
        return code_text
        
    except Exception as e:
        print(f"[Stage 3] CodeGen failed: {e}")
        raise


def stage4_cas(code_text: str) -> tuple[List[Dict], str, List[CASResult]]:
    """
    Stage 4: CAS 처리
    코드에서 CAS 작업을 추출하고 SymPy로 계산
    
    Args:
        code_text: CodeGen 출력 텍스트
        
    Returns:
        tuple: (jobs_raw, manim_code_draft, cas_results)
    """
    print(f"[Stage 4] Processing CAS...")
    
    try:
        # CAS 작업과 Manim 코드 분리
        jobs_raw, manim_code_draft = _extract_jobs_and_code(code_text)
        
        # CAS 실행
        jobs = [CASJob(**j) for j in jobs_raw]
        cas_res = run_cas(jobs)
        
        print(f"[Stage 4] CAS completed. Processed {len(cas_res)} jobs")
        return jobs_raw, manim_code_draft, cas_res
        
    except Exception as e:
        print(f"[Stage 4] CAS failed: {e}")
        raise


def stage5_render(manim_code_draft: str, cas_results: List[CASResult], output_path: str) -> str:
    """
    Stage 5: Render 처리
    Placeholder 치환하여 최종 Manim 코드 생성
    
    Args:
        manim_code_draft: 초안 Manim 코드
        cas_results: CAS 계산 결과
        output_path: 출력 파일 경로
        
    Returns:
        str: 최종 Manim 코드
    """
    print(f"[Stage 5] Rendering final code...")
    
    try:
        # Placeholder 치환
        final = fill_placeholders(manim_code_draft, cas_results)
        manim_final = final.manim_code_final.strip()
        
        # 파일 저장
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(manim_final)
        
        print(f"[Stage 5] Render completed. Output: {output_path}")
        return manim_final
        
    except Exception as e:
        print(f"[Stage 5] Render failed: {e}")
        raise


def _extract_jobs_and_code(code_text: str):
    """CodeGen 출력에서 CAS 작업과 Manim 코드 분리"""
    import re
    
    # 코드펜스 제거
    code_text = re.sub(r'^\s*```(?:python)?\s*', '', code_text)
    code_text = re.sub(r'\s*```\s*$', '', code_text)
    
    # CAS-JOBS 섹션 찾기
    m = re.search(r"-{3}CAS-JOBS-{3}", code_text)
    if not m:
        raise RuntimeError("CAS-JOBS 섹션을 찾을 수 없습니다.")
    
    mark = m.start()
    manim_code = code_text[:mark].strip()
    tail = code_text[mark + len("---CAS-JOBS---"):]
    
    # JSON 배열 추출
    json_text = _find_balanced_json_array(tail, 0)
    jobs_raw = json.loads(json_text)
    
    # ID 자동 부여
    for idx, j in enumerate(jobs_raw, 1):
        j.setdefault("id", str(idx))
    
    return jobs_raw, manim_code


def _find_balanced_json_array(text: str, start_idx: int) -> str:
    """균형 잡힌 JSON 배열 추출"""
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


def run_stage(stage_num: int, **kwargs) -> Any:
    """
    특정 단계 실행
    
    Args:
        stage_num: 실행할 단계 번호 (1-5)
        **kwargs: 단계별 필요한 인자들
        
    Returns:
        Any: 단계별 출력 결과
    """
    if stage_num == 1:
        return stage1_ocr(**kwargs)
    elif stage_num == 2:
        return stage2_graphsampling(**kwargs)
    elif stage_num == 3:
        return stage3_codegen(**kwargs)
    elif stage_num == 4:
        return stage4_cas(**kwargs)
    elif stage_num == 5:
        return stage5_render(**kwargs)
    else:
        raise ValueError(f"Invalid stage number: {stage_num}. Must be 1-5.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run individual pipeline stages")
    parser.add_argument("stage", type=int, choices=[1,2,3,4,5], help="Stage number to run")
    parser.add_argument("--image-path", help="Input image path (for stage 1)")
    parser.add_argument("--problem-dir", help="Problem directory (for stage 2)")
    parser.add_argument("--outputschema-path", help="Outputschema path (for stage 3)")
    parser.add_argument("--image-paths", nargs="+", help="Image paths (for stage 3)")
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--code-text", help="Code text (for stage 4)")
    parser.add_argument("--manim-code", help="Manim code draft (for stage 5)")
    parser.add_argument("--cas-results", help="CAS results JSON (for stage 5)")
    parser.add_argument("--output-path", help="Output file path")
    
    args = parser.parse_args()
    
    # 단계별 인자 구성
    kwargs = {}
    if args.image_path:
        kwargs["image_path"] = args.image_path
    if args.problem_dir:
        kwargs["problem_dir"] = args.problem_dir
    if args.outputschema_path:
        kwargs["output_path"] = args.outputschema_path
    if args.image_paths:
        kwargs["image_paths"] = args.image_paths
    if args.output_dir:
        kwargs["output_dir"] = args.output_dir
    if args.code_text:
        kwargs["code_text"] = args.code_text
    if args.output_path:
        kwargs["output_path"] = args.output_path
    
    try:
        result = run_stage(args.stage, **kwargs)
        print(f"Stage {args.stage} completed successfully")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Stage {args.stage} failed: {e}")
        sys.exit(1)
