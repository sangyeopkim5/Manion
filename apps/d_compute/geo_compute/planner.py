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
