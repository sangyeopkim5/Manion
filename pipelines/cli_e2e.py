#!/usr/bin/env python3
"""
E2E CLI 도구
전체 파이프라인을 실행하는 명령줄 인터페이스
"""
import os
import sys
import argparse
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipelines.e2e import run_pipeline, run_pipeline_with_ocr


def main():
    """E2E CLI 메인 함수"""
    parser = argparse.ArgumentParser(
        description="Manion-CAS E2E Pipeline CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # OCR 방식 (이미지만 입력)
  python -m pipelines.cli_e2e Manion/Probleminput/1.png
  python -m pipelines.cli_e2e Manion/Probleminput/1.png --problem-name "1"
  
  # 기존 방식 (이미지 + JSON)
  python -m pipelines.cli_e2e Manion/Probleminput/1.png Manion/Probleminput/1.json
        """
    )
    
    parser.add_argument("image_path", help="Input image file path")
    parser.add_argument("json_path", nargs="?", help="Input JSON file path (optional, for legacy mode)")
    parser.add_argument("--problem-name", help="Problem name (for OCR mode)")
    parser.add_argument("--output-dir", default="ManimcodeOutput", help="Output directory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    # Postproc flags
    parser.add_argument("--postproc", action="store_true", help="enable postproc stage (overrides configs/postproc.enabled)")
    parser.add_argument("--no-postproc", action="store_true", help="disable postproc stage (overrides configs/postproc.enabled)")
    
    args = parser.parse_args()
    
    # Postproc 설정 override
    if getattr(args, "postproc", False) and getattr(args, "no-postproc", False):
        print("[warn] both --postproc and --no-postproc provided; ignoring overrides.")
    elif getattr(args, "postproc", False):
        os.environ["POSTPROC_ENABLED_OVERRIDE"] = "1"
    elif getattr(args, "no-postproc", False):
        os.environ["POSTPROC_ENABLED_OVERRIDE"] = "0"
    
    # 입력 파일 존재 확인
    if not os.path.exists(args.image_path):
        print(f"Error: Image file not found: {args.image_path}")
        sys.exit(1)
    
    if args.json_path and not os.path.exists(args.json_path):
        print(f"Error: JSON file not found: {args.json_path}")
        sys.exit(1)
    
    try:
        # OCR 방식 (이미지만 입력)
        if not args.json_path:
            print("🚀 Running E2E pipeline with OCR...")
            print(f"📁 Input image: {args.image_path}")
            if args.problem_name:
                print(f"📝 Problem name: {args.problem_name}")
            
            result = run_pipeline_with_ocr(
                image_path=args.image_path,
                problem_name=args.problem_name
            )
            
            if result:
                print("✅ E2E pipeline completed successfully!")
                print(f"📄 Generated code length: {len(result)} characters")
                if args.verbose:
                    print("\n" + "="*50)
                    print("GENERATED CODE")
                    print("="*50)
                    print(result)
            else:
                print("❌ E2E pipeline failed - no code generated")
                sys.exit(1)
        
        # 기존 방식 (이미지 + JSON)
        else:
            print("🚀 Running E2E pipeline with existing JSON...")
            print(f"📁 Input image: {args.image_path}")
            print(f"📄 Input JSON: {args.json_path}")
            
            # ProblemDoc 생성
            import json
            from libs.schemas import ProblemDoc
            
            with open(args.json_path, 'r', encoding='utf-8') as f:
                items = json.load(f)
            
            doc = ProblemDoc(items=items, image_path=args.image_path)
            
            result = run_pipeline(doc)
            
            if result:
                print("✅ E2E pipeline completed successfully!")
                print(f"📄 Generated code length: {len(result)} characters")
                if args.verbose:
                    print("\n" + "="*50)
                    print("GENERATED CODE")
                    print("="*50)
                    print(result)
            else:
                print("❌ E2E pipeline failed - no code generated")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\n⚠️ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
