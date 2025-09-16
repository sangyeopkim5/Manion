# manion_postproc/postproc.py
import os, json
from dataclasses import dataclass
from .run_manim import run_manim_once

@dataclass
class Config:
    max_loops: int = 3
    manim_quality: str = "-ql"
    timeout_sec: int = 30

def postprocess_and_render(problem_name: str, llm, cfg: Config):
    """
    problem_name: 예) "problem_001"
    ManimcodeOutput/problem_001/problem_001.py 읽기 → LLM 수정 → 렌더링 → 저장
    """
    base_dir = os.path.join("ManimcodeOutput", problem_name)
    os.makedirs(base_dir, exist_ok=True)

    input_path = os.path.join(base_dir, f"{problem_name}.py")
    output_code_path = os.path.join(base_dir, "final_manimcode.py")
    output_video_path = os.path.join(base_dir, f"{problem_name}.mp4")
    proof_path = os.path.join(base_dir, "proof.json")

    # 1️⃣ 최초 코드 읽기
    with open(input_path, "r", encoding="utf-8") as f:
        code = f.read()

    proof = {"problem": problem_name, "steps": []}

    # 2️⃣ LLM으로 최초 수정
    code = llm.propose_patch(code, error_log="")
    proof["steps"].append({"stage": "initial_llm_fix", "ok": True})

    with open(output_code_path, "w", encoding="utf-8") as f:
        f.write(code)

    # 3️⃣ 루프 돌며 렌더링 시도
    for i in range(cfg.max_loops):
        ok, logs = run_manim_once(
            code,
            quality=cfg.manim_quality,
            timeout=cfg.timeout_sec,
            output_dir=base_dir
        )
        proof["steps"].append({"stage": f"render_{i+1}", "ok": ok, "log_excerpt": logs[-400:]})

        if ok:
            # 성공하면 고품질 렌더
            run_manim_once(
                code, quality="-qh", timeout=cfg.timeout_sec, output_dir=base_dir
            )
            scene_path = os.path.join(base_dir, "scene.mp4")
            if os.path.exists(scene_path):
                os.rename(scene_path, output_video_path)
            proof["result"] = "success"
            _save_proof(proof_path, proof)
            return output_code_path, output_video_path, proof

        # 실패 시 → 다시 LLM 수정
        code = llm.propose_patch(code, error_log=logs)
        with open(output_code_path, "w", encoding="utf-8") as f:
            f.write(code)

    proof["result"] = "failed"
    proof["final_error"] = logs[-2000:]
    _save_proof(proof_path, proof)
    return output_code_path, None, proof

def _save_proof(path: str, data: dict):
    """proof를 JSON으로 저장"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] proof 저장 실패: {e}")
