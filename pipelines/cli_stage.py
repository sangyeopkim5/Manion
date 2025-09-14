#!/usr/bin/env python3
"""
개별 단계 CLI 도구
각 파이프라인 단계를 독립적으로 실행하는 명령줄 인터페이스
"""
import os
import sys
import argparse
import json
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipelines.stages import run_stage, stage1_ocr, stage2_graphsampling, stage3_codegen, stage4_cas, stage5_render, run_postproc_stage


def run_postproc_cli(problem_name: str):
    """Postproc 단독 실행 CLI 함수"""
    res = run_postproc_stage(problem_name)
    if res is None:
        print("[postproc] skipped (disabled or input missing)")
    else:
        print("[postproc] code:", res["code_path"])
        print("[postproc] video:", res["video_path"])


def main():
    """개별 단계 CLI 메인 함수"""
    parser = argparse.ArgumentParser(
        description="Manion-CAS Individual Stage CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stage 1: OCR 처리
  python -m pipelines.cli_stage 1 --image-path "Manion/Probleminput/1.png" --problem-name "1"
  
  # Stage 2: GraphSampling 처리
  python -m pipelines.cli_stage 2 --problem-dir "./temp_ocr_output/1/1"
  
  # Stage 3: CodeGen 처리
  python -m pipelines.cli_stage 3 --outputschema-path "outputschema.json" --image-paths "image.jpg" --output-dir "."
  
  # Stage 4: CAS 처리
  python -m pipelines.cli_stage 4 --code-text "$(cat codegen_output.py)"
  
  # Stage 5: Render 처리
  python -m pipelines.cli_stage 5 --manim-code "$(cat manim_draft.py)" --cas-results "cas_results.json" --output-path "final.py"
  
  # Postproc 단독 실행
  python -m pipelines.cli_stage postproc --problem "1"
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Stage parser
    stage_parser = subparsers.add_parser('stage', help='Run individual pipeline stage')
    stage_parser.add_argument("stage", type=int, choices=[1,2,3,4,5], help="Stage number to run")
    
    # Postproc parser
    postproc_parser = subparsers.add_parser("postproc", help="run postproc stage only")
    postproc_parser.add_argument("--problem", required=True, help="Problem name")
    
    # For backward compatibility, also support direct stage number
    parser.add_argument("stage", type=int, choices=[1,2,3,4,5], help="Stage number to run", nargs='?')
    parser.add_argument("--image-path", help="Input image path (for stage 1)")
    parser.add_argument("--problem-name", help="Problem name (for stage 1)")
    parser.add_argument("--output-dir", default="./temp_ocr_output", help="Output directory (for stage 1)")
    parser.add_argument("--problem-dir", help="Problem directory (for stage 2)")
    parser.add_argument("--outputschema-path", help="Outputschema path (for stage 2)")
    parser.add_argument("--image-paths", nargs="+", help="Image paths (for stage 3)")
    parser.add_argument("--code-text", help="Code text (for stage 4)")
    parser.add_argument("--manim-code", help="Manim code draft (for stage 5)")
    parser.add_argument("--cas-results", help="CAS results JSON file (for stage 5)")
    parser.add_argument("--output-path", help="Output file path (for stage 5)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Handle postproc subcommand
    if hasattr(args, 'command') and args.command == 'postproc':
        try:
            print(f"🚀 Running Postproc stage...")
            print(f"📝 Problem name: {args.problem}")
            run_postproc_cli(args.problem)
            print("✅ Postproc stage completed successfully!")
            return
        except Exception as e:
            print(f"❌ Postproc stage failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    
    # Handle stage subcommand or backward compatibility
    stage_num = None
    if hasattr(args, 'command') and args.command == 'stage':
        stage_num = args.stage
    elif hasattr(args, 'stage') and args.stage is not None:
        stage_num = args.stage
    else:
        print("Error: Please specify a stage number or use a subcommand")
        parser.print_help()
        sys.exit(1)
    
    try:
        # 단계별 인자 구성
        kwargs = {}
        
        if stage_num == 1:
            if not args.image_path:
                print("Error: --image-path is required for stage 1")
                sys.exit(1)
            if not os.path.exists(args.image_path):
                print(f"Error: Image file not found: {args.image_path}")
                sys.exit(1)
            
            kwargs["image_path"] = args.image_path
            kwargs["output_dir"] = args.output_dir
            if args.problem_name:
                kwargs["problem_name"] = args.problem_name
                
            print(f"🚀 Running Stage 1 (OCR)...")
            print(f"📁 Input image: {args.image_path}")
            if args.problem_name:
                print(f"📝 Problem name: {args.problem_name}")
            
        elif stage_num == 2:
            if not args.problem_dir:
                print("Error: --problem-dir is required for stage 2")
                sys.exit(1)
            if not os.path.exists(args.problem_dir):
                print(f"Error: Problem directory not found: {args.problem_dir}")
                sys.exit(1)
            
            kwargs["problem_dir"] = args.problem_dir
            if args.outputschema_path:
                kwargs["output_path"] = args.outputschema_path
                
            print(f"🚀 Running Stage 2 (GraphSampling)...")
            print(f"📁 Problem directory: {args.problem_dir}")
            
        elif stage_num == 3:
            if not args.outputschema_path:
                print("Error: --outputschema-path is required for stage 3")
                sys.exit(1)
            if not args.image_paths:
                print("Error: --image-paths is required for stage 3")
                sys.exit(1)
            if not args.output_dir:
                print("Error: --output-dir is required for stage 3")
                sys.exit(1)
            
            if not os.path.exists(args.outputschema_path):
                print(f"Error: Outputschema file not found: {args.outputschema_path}")
                sys.exit(1)
            
            for img_path in args.image_paths:
                if not os.path.exists(img_path):
                    print(f"Error: Image file not found: {img_path}")
                    sys.exit(1)
            
            kwargs["outputschema_path"] = args.outputschema_path
            kwargs["image_paths"] = args.image_paths
            kwargs["output_dir"] = args.output_dir
            
            print(f"🚀 Running Stage 3 (CodeGen)...")
            print(f"📄 Outputschema: {args.outputschema_path}")
            print(f"🖼️ Images: {args.image_paths}")
            
        elif stage_num == 4:
            if not args.code_text:
                print("Error: --code-text is required for stage 4")
                sys.exit(1)
            
            kwargs["code_text"] = args.code_text
            
            print(f"🚀 Running Stage 4 (CAS)...")
            print(f"📄 Code text length: {len(args.code_text)} characters")
            
        elif stage_num == 5:
            if not args.manim_code:
                print("Error: --manim-code is required for stage 5")
                sys.exit(1)
            if not args.cas_results:
                print("Error: --cas-results is required for stage 5")
                sys.exit(1)
            if not args.output_path:
                print("Error: --output-path is required for stage 5")
                sys.exit(1)
            
            if not os.path.exists(args.cas_results):
                print(f"Error: CAS results file not found: {args.cas_results}")
                sys.exit(1)
            
            # CAS 결과 로드
            with open(args.cas_results, 'r', encoding='utf-8') as f:
                cas_data = json.load(f)
            
            from libs.schemas import CASResult
            cas_results = [CASResult(**item) for item in cas_data]
            
            kwargs["manim_code_draft"] = args.manim_code
            kwargs["cas_results"] = cas_results
            kwargs["output_path"] = args.output_path
            
            print(f"🚀 Running Stage 5 (Render)...")
            print(f"📄 Manim code length: {len(args.manim_code)} characters")
            print(f"🧮 CAS results: {len(cas_results)} items")
        
        # 단계 실행
        result = run_stage(stage_num, **kwargs)
        
        print(f"✅ Stage {stage_num} completed successfully!")
        
        if args.verbose:
            print("\n" + "="*50)
            print(f"STAGE {stage_num} RESULT")
            print("="*50)
            if isinstance(result, str):
                print(result)
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except KeyboardInterrupt:
        print(f"\n⚠️ Stage {stage_num} interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Stage {stage_num} failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
