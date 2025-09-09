import json
import sys
import os
import shutil
from pathlib import Path
from typing import List

from libs.schemas import ProblemDoc, CASJob
from apps.codegen.codegen import generate_manim
from apps.cas.compute import run_cas
from apps.render.fill import fill_placeholders
from apps.graphsampling.builder import build_outputschema


def run_pipeline(doc: ProblemDoc) -> str:
    """Run the end-to-end pipeline locally.

    The function generates Manim code from ``doc`` using the codegen module,
    optionally executes CAS jobs, and fills placeholders. When the code
    generation step produces no CAS jobs, the intermediate code is returned
    unchanged without calling the CAS or render steps.
    """

    # Step 0: Graphsampling stage — persist inputs and build outputschema
    output_root = Path("ManimcodeOutput")
    output_root.mkdir(exist_ok=True)
    problem_name = Path(doc.image_path).stem if doc.image_path else "local"
    problem_dir = output_root / problem_name
    problem_dir.mkdir(exist_ok=True)

    # Save OCR JSON and copy image if available
    input_json_path = problem_dir / "input.json"
    with open(input_json_path, "w", encoding="utf-8") as f:
        json.dump([i.dict() for i in doc.items], f, ensure_ascii=False, indent=2)

    if doc.image_path and os.path.isfile(doc.image_path):
        dst_image_path = problem_dir / Path(doc.image_path).name
        try:
            shutil.copy(doc.image_path, dst_image_path)
        except Exception:
            pass

    outputschema_path = problem_dir / "outputschema.json"
    build_outputschema(str(problem_dir), str(outputschema_path), args=None)

    # Proceed to codegen
    cg = generate_manim(doc)

    # If there are no CAS jobs we can return the draft code immediately.
    if not cg.cas_jobs:
        return cg.manim_code_draft

    jobs: List[CASJob] = [CASJob(**j) for j in cg.cas_jobs]
    cas_res = run_cas(jobs)
    final = fill_placeholders(cg.manim_code_draft, cas_res)
    return final.manim_code_final


if __name__ == "__main__":
    img = sys.argv[1]
    js = sys.argv[2]
    items = json.load(open(js, "r", encoding="utf-8"))
    doc = ProblemDoc(items=items, image_path=img)
    code = run_pipeline(doc)
    print(code.strip())
