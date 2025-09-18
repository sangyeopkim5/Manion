from __future__ import annotations
import json, os, numpy as np

from .geom_utils import v3, rotate, fit_into_box
from .templates import solve_quad_diaglen_ang, solve_square_with_ADE

def load_spec(path:str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def plan_and_solve(spec:dict):
    """간단 디스패처: type에 따라 템플릿 호출."""
    t = spec["type"]
    if t=="quad_diag2len2ang":
        A = v3(*spec["seed"]["A"]); D = v3(*spec["seed"]["D"])
        sol = solve_quad_diaglen_ang(A,D, spec["angles"]["DAC"], spec["angles"]["ADB"],
                                     spec["lengths"]["AC"], spec["lengths"]["BD"])
        if sol is None: raise RuntimeError("조건을 만족하는 사각형을 못 찾음")
        return sol
    if t=="square_with_ADE":
        return solve_square_with_ADE(spec["lengths"]["side"], spec["angles"]["ADE"])
    raise NotImplementedError(f"unknown spec.type={t}")

def scale_into_box(points:dict, box):
    box_min = np.array(box["min"]+[0.0])
    box_max = np.array(box["max"]+[0.0])
    order = list(points.keys())
    arr, s = fit_into_box([points[k] for k in order], box_min, box_max, margin=box.get("margin",0.2))
    return {k:arr[i] for i,k in enumerate(order)}, s


def solve_all_specs_in_problem_dir(problem_dir, overwrite=True):
    """Solve all geometric problems (spec_0.json, spec_1.json, ...) in a problem directory.
    
    Args:
        problem_dir: Path to the problem directory
        overwrite: Whether to overwrite existing results
        
    Returns:
        List of dictionaries containing solution status and metadata for each spec
    """
    from pathlib import Path
    import glob
    
    problem_dir = Path(problem_dir)
    results = []
    
    # Find all spec_*.json files
    spec_files = sorted(glob.glob(str(problem_dir / "spec_*.json")))
    
    if not spec_files:
        return [{
            "status": "error",
            "error": f"No spec_*.json files found in {problem_dir}"
        }]
    
    print(f"[d_geo_compute] Found {len(spec_files)} spec files to process")
    
    for spec_file in spec_files:
        spec_path = Path(spec_file)
        image_index = int(spec_path.stem.split('_')[1])  # spec_0.json -> 0
        result_path = problem_dir / f"geo_result_{image_index}.json"
        
        print(f"[d_geo_compute] Processing {spec_path.name} -> {result_path.name}")
        
        # Check if result already exists and overwrite is False
        if not overwrite and result_path.exists():
            try:
                with result_path.open("r", encoding="utf-8") as f:
                    existing_result = json.load(f)
                results.append({
                    "status": "skipped",
                    "reason": "Result already exists and overwrite=False",
                    "spec_path": str(spec_path),
                    "result_path": str(result_path),
                    "image_index": image_index,
                    "existing_result": existing_result
                })
                continue
            except Exception as e:
                # If we can't read existing result, proceed with solving
                pass
        
        # Load and solve the specification
        try:
            spec = load_spec(str(spec_path))
            points = plan_and_solve(spec)
            
            # Scale points into the specified box if present
            if "box" in spec:
                scaled_points, scale_factor = scale_into_box(points, spec["box"])
                result = {
                    "status": "solved",
                    "spec_path": str(spec_path),
                    "result_path": str(result_path),
                    "image_index": image_index,
                    "points": {k: v.tolist() if hasattr(v, 'tolist') else v for k, v in scaled_points.items()},
                    "scale_factor": float(scale_factor),
                    "box": spec["box"]
                }
            else:
                result = {
                    "status": "solved",
                    "spec_path": str(spec_path),
                    "result_path": str(result_path),
                    "image_index": image_index,
                    "points": {k: v.tolist() if hasattr(v, 'tolist') else v for k, v in points.items()},
                    "scale_factor": 1.0
                }
            
            # Save result to file
            with result_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            results.append(result)
            print(f"[d_geo_compute] Successfully solved {spec_path.name}")
            
        except Exception as e:
            error_result = {
                "status": "error",
                "error": str(e),
                "spec_path": str(spec_path),
                "result_path": str(result_path),
                "image_index": image_index
            }
            results.append(error_result)
            print(f"[d_geo_compute] Failed to solve {spec_path.name}: {e}")
    
    return results

def solve_in_problem_dir(problem_dir, overwrite=True):
    """Solve geometric problems in a problem directory.
    
    Args:
        problem_dir: Path to the problem directory
        overwrite: Whether to overwrite existing results
        
    Returns:
        Dictionary containing solution status and metadata
    """
    from pathlib import Path
    
    problem_dir = Path(problem_dir)
    spec_path = problem_dir / "spec.json"
    result_path = problem_dir / "geo_result.json"
    
    # Check if spec.json exists
    if not spec_path.exists():
        return {
            "status": "error",
            "error": f"spec.json not found in {problem_dir}",
            "spec_path": str(spec_path)
        }
    
    # Check if result already exists and overwrite is False
    if not overwrite and result_path.exists():
        try:
            with result_path.open("r", encoding="utf-8") as f:
                existing_result = json.load(f)
            return {
                "status": "skipped",
                "reason": "Result already exists and overwrite=False",
                "spec_path": str(spec_path),
                "result_path": str(result_path),
                "existing_result": existing_result
            }
        except Exception as e:
            # If we can't read existing result, proceed with solving
            pass
    
    # Load and solve the specification
    try:
        spec = load_spec(str(spec_path))
        points = plan_and_solve(spec)
        
        # Scale points into the specified box if present
        if "box" in spec:
            scaled_points, scale_factor = scale_into_box(points, spec["box"])
            result = {
                "status": "solved",
                "points": scaled_points,
                "scale_factor": scale_factor,
                "original_points": points
            }
        else:
            result = {
                "status": "solved", 
                "points": points,
                "scale_factor": 1.0
            }
            
    except Exception as e:
        result = {
            "status": "error",
            "error": str(e),
            "points": {},
            "scale_factor": 1.0
        }
    
    # Save result to file
    try:
        with result_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        result["result_path"] = str(result_path)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Failed to save result: {str(e)}"
    
    result["spec_path"] = str(spec_path)
    return result


def solve_spec(spec: dict) -> dict:
    """Solve a single geometric specification.
    
    Args:
        spec: Geometric specification dictionary
        
    Returns:
        Dictionary containing solved points and metadata
    """
    try:
        # Use planner to solve the specification
        points = plan_and_solve(spec)
        
        # Scale points into the specified box if present
        if "box" in spec:
            scaled_points, scale_factor = scale_into_box(points, spec["box"])
            return {
                "status": "solved",
                "points": scaled_points,
                "scale_factor": scale_factor,
                "original_points": points
            }
        else:
            return {
                "status": "solved", 
                "points": points,
                "scale_factor": 1.0
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "points": {},
            "scale_factor": 1.0
        }


def solve_spec_file(spec_path: str) -> dict:
    """Solve a geometric specification from a file.
    
    Args:
        spec_path: Path to the specification JSON file
        
    Returns:
        Dictionary containing solved points and metadata
    """
    try:
        spec = load_spec(spec_path)
        return solve_spec(spec)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to load or solve spec from {spec_path}: {str(e)}",
            "points": {},
            "scale_factor": 1.0
        }