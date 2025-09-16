from __future__ import annotations
import numpy as np
from manim import *

from .geom_utils import unit

def _ang(v):
    return float(np.arctan2(v[1], v[0]))

def _ccw_delta(a,b):
    d = (b - a) % (2*np.pi)
    return d

def inner_order(V,P,Q):
    aP = _ang(P - V); aQ = _ang(Q - V)
    d = _ccw_delta(aP, aQ)
    if d <= np.pi:
        return P, Q
    else:
        return Q, P

def make_angle_inner(V, P, Q, radius=0.5, color=YELLOW):
    P1, P2 = inner_order(V,P,Q)
    l1 = Line(V, P1, stroke_width=3, color=color).set_opacity(0.7)
    l2 = Line(V, P2, stroke_width=3, color=color).set_opacity(0.7)
    arc = Angle(l1, l2, radius=radius, color=color)  # Line1→Line2 반시계
    return l1,l2,arc

def make_angle_outer(V,P,Q, radius=0.5, color=YELLOW):
    P1, P2 = inner_order(V,P,Q)
    l1 = Line(V, P1, stroke_width=3, color=color).set_opacity(0.7)
    l2 = Line(V, P2, stroke_width=3, color=color).set_opacity(0.7)
    arc = Angle(l1, l2, radius=radius, color=color, other_angle=True)
    return l1,l2,arc

def measured_inner_deg(V,P,Q):
    aP=_ang(P-V); aQ=_ang(Q-V)
    d = _ccw_delta(aP, aQ)
    return np.degrees(d if d<=np.pi else 2*np.pi-d)

def label_dual(apex, arc, given_deg, measured_deg, scale=0.9):
    t = MathTex(rf"{given_deg:.0f}^\circ / {measured_deg:.1f}^\circ").scale(scale)
    return t.move_to(arc.point_from_proportion(0.55))
