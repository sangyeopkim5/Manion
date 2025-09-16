from __future__ import annotations
import os, json, numpy as np
from manim import *

from .angle_rules import make_angle_inner, measured_inner_deg, label_dual
from .planner import load_spec, plan_and_solve, scale_into_box

# --- NEW: 방향 해석기 (DIR 제거용) ---
DIR_MAP = {
    "UP": UP, "DOWN": DOWN, "LEFT": LEFT, "RIGHT": RIGHT,
    "UL": UL, "UR": UR, "DL": DL, "DR": DR,
    "CENTER": ORIGIN, "ORIGIN": ORIGIN,
}
def resolve_dir(val):
    """point_labels 값이 문자열/리스트/튜플/넘파이여도 안전하게 방향 벡터로 변환."""
    if isinstance(val, str):
        return DIR_MAP.get(val.upper(), UP)
    if isinstance(val, (list, tuple, np.ndarray)):
        arr = np.array(val, dtype=float).reshape(-1)
        if arr.size == 2:
            return np.array([arr[0], arr[1], 0.0], dtype=float)
        if arr.size == 3:
            return arr.astype(float)
    return UP  # 기본값

class GeometryScene(Scene):
    def construct(self):
        # 1) 스펙(JSON) 경로
        spec_path = os.environ.get("GEOM_SPEC","").strip()
        if not spec_path:
            raise RuntimeError("환경변수 GEOM_SPEC에 스펙 JSON 경로를 넣어 주세요.")
        spec = load_spec(spec_path)

        # 2) 좌표 산출(템플릿/플래너)
        pts = plan_and_solve(spec)
        # 3) 박스 스케일
        pts, _ = scale_into_box(pts, spec["box"])

        # 4) 테두리(ABCD CCW 기준) → 보조선/대각선
        order = spec.get("border_order", ["A","B","C","D"])
        border = Polygon(*[pts[k] for k in order], color=BLUE)
        self.play(Create(border))

        # extras: 선/각/라벨
        for ex in spec.get("extras", []):
            if ex["type"]=="seg":
                p,q = pts[ex["from"]], pts[ex["to"]]
                self.play(Create(Line(p,q, color=WHITE, stroke_width=3)))
            if ex["type"]=="len_label":
                p,q = pts[ex["from"]], pts[ex["to"]]
                text = MathTex(ex["text"]).scale(0.8).move_to((p+q)/2 + np.array(ex.get("offset",[0,0,0])))
                self.play(FadeIn(text))
            if ex["type"]=="angle":
                V = pts[ex["apex"]]; P=pts[ex]["p"]; Q=pts[ex]["q"]  # ← dict 키 안전
                l1,l2,arc = make_angle_inner(V,P,Q, radius=ex.get("radius",0.55), color=YELLOW)
                given = float(ex["deg"]); meas = measured_inner_deg(V,P,Q)
                lbl = label_dual(V, arc, given, meas, scale=0.9)
                self.play(Create(l1),Create(l2),Create(arc),Write(lbl))

        # 5) 점 라벨 (DIR 제거 → resolve_dir 사용)
        def L(t,p,where): self.add(Text(t, font_size=28).next_to(Dot(p), where, buff=0.12))
        for name, where in spec.get("point_labels", {}).items():
            L(name, pts[name], resolve_dir(where))
        self.wait()
