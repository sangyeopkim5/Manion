"""Simple error handler for d_geo_compute stage."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def fix_spec_with_gpt(spec_json: Dict[str, Any], error_msg: str) -> Optional[Dict[str, Any]]:
    """Fix spec.json format errors using GPT."""
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
                {"role": "user", "content": f"Error: {error_msg}\nJSON: {json.dumps(spec_json, ensure_ascii=False)}"}
            ],
            temperature=0.0,
        )
        return json.loads(response.choices[0].message.content or "{}")
    except:
        return None


def retry_with_fix(problem_dir: Path, spec_path: Path, error_msg: str) -> Dict[str, Any]:
    """Retry geo compute with error correction."""
    # Load original spec
    try:
        with spec_path.open("r", encoding="utf-8") as f:
            spec = json.load(f)
    except:
        return {"status": "error", "error": "Cannot load spec.json"}
    
    # Fix with GPT
    fixed_spec = fix_spec_with_gpt(spec, error_msg)
    if not fixed_spec:
        return {"status": "error", "error": "GPT fix failed"}
    
    # Save fixed spec
    with spec_path.open("w", encoding="utf-8") as f:
        json.dump(fixed_spec, f, ensure_ascii=False, indent=2)
    
    # Retry
    try:
        from .planner import solve_in_problem_dir
        result = solve_in_problem_dir(problem_dir, overwrite=True)
        return {"status": "fixed_and_solved", "spec_path": str(spec_path), "result": result}
    except Exception as e:
        return {"status": "error", "error": f"Still failed: {e}"}
