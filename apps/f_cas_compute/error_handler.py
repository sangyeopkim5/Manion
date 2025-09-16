"""Simple error handler for f_cas_compute stage."""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def fix_cas_jobs_with_gpt(cas_jobs: List[Dict[str, Any]], error_msg: str) -> Optional[List[Dict[str, Any]]]:
    """Fix cas_jobs.json format errors using GPT."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    
    # Load system prompt
    prompt_path = Path(__file__).parent / "error_system_prompt.txt"
    system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "Fix JSON format errors only."
    
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Error: {error_msg}\nJSON: {json.dumps(cas_jobs, ensure_ascii=False)}"}
            ],
            temperature=0.0,
        )
        result = json.loads(response.choices[0].message.content or "[]")
        return result if isinstance(result, list) else None
    except:
        return None


def retry_with_fix(problem_dir: Path, cas_jobs_path: Path, output_path: Path, error_msg: str) -> Dict[str, Any]:
    """Retry CAS compute with error correction."""
    # Load original jobs
    try:
        with cas_jobs_path.open("r", encoding="utf-8") as f:
            jobs = json.load(f)
    except:
        return {"status": "error", "error": "Cannot load cas_jobs.json"}
    
    # Fix with GPT
    fixed_jobs = fix_cas_jobs_with_gpt(jobs, error_msg)
    if not fixed_jobs:
        return {"status": "error", "error": "GPT fix failed"}
    
    # Save fixed jobs
    with cas_jobs_path.open("w", encoding="utf-8") as f:
        json.dump(fixed_jobs, f, ensure_ascii=False, indent=2)
    
    # Update codegen_output.py
    codegen_path = problem_dir / "codegen_output.py"
    if codegen_path.exists():
        content = codegen_path.read_text(encoding="utf-8")
        pattern = r"(---CAS-JOBS---\s*\n)(.*?)(?=\n---|\Z)"
        if re.search(pattern, content, re.DOTALL):
            new_content = re.sub(pattern, r"\1" + json.dumps(fixed_jobs, ensure_ascii=False, indent=2) + "\n", content, flags=re.DOTALL)
        else:
            new_content = content + f"\n---CAS-JOBS---\n{json.dumps(fixed_jobs, ensure_ascii=False, indent=2)}\n"
        codegen_path.write_text(new_content, encoding="utf-8")
    
    # Retry
    try:
        from .compute import run_cas_compute
        result = run_cas_compute(problem_dir, cas_jobs_path=cas_jobs_path, output_path=output_path, overwrite=True)
        return {"status": "fixed_and_computed", "jobs_path": str(cas_jobs_path), "result": result}
    except Exception as e:
        return {"status": "error", "error": f"Still failed: {e}"}
