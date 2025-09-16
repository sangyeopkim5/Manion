from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import toml


def _load_postproc_conf() -> Dict[str, Any]:
    try:
        cfg = toml.load("configs/openai.toml").get("postproc", {})
    except Exception:
        cfg = {}

    override = os.environ.get("POSTPROC_ENABLED_OVERRIDE")
    if override == "1":
        enabled = True
    elif override == "0":
        enabled = False
    else:
        enabled = cfg.get("enabled", False)

    return {
        "enabled": enabled,
        "model": cfg.get("model", ""),
        "base_url": cfg.get("base_url", ""),
        "api_key": cfg.get("api_key", "EMPTY"),
        "temperature": float(cfg.get("temperature", 0.2)),
        "max_loops": int(cfg.get("max_loops", 3)),
        "quality": cfg.get("quality", "-ql"),
        "timeout_sec": int(cfg.get("timeout_sec", 30)),
    }


def run_postproc_stage(problem_name: str) -> Optional[Dict[str, Any]]:
    conf = _load_postproc_conf()
    if not conf["enabled"]:
        return None

    try:
        from libs.postproc.postproc import postprocess_and_render, Config as PostCfg
        from libs.postproc.llm_openai import OpenAICompatLLM
    except Exception:
        return None

    base_dir = Path("ManimcodeOutput") / problem_name
    input_py = base_dir / f"{problem_name}.py"
    if not input_py.exists():
        return None

    llm = OpenAICompatLLM(
        base_url=conf["base_url"],
        api_key=conf["api_key"],
        model=conf["model"],
        system_prompt_path=None,
        temperature=conf["temperature"],
    )
    code_path, video_path, proof = postprocess_and_render(
        problem_name,
        llm,
        PostCfg(
            max_loops=conf["max_loops"],
            manim_quality=conf["quality"],
            timeout_sec=conf["timeout_sec"],
        ),
    )
    return {"code_path": code_path, "video_path": video_path, "proof": proof}
