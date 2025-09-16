from __future__ import annotations

import numpy as np

EPS = 1e-9


def v3(x, y, z=0.0):
    return np.array([float(x), float(y), float(z)], dtype=float)


def unit(v):
    n = np.linalg.norm(v[:2]) + 1e-12
    return np.array([v[0] / n, v[1] / n, 0.0])


def rotate(v, ang_rad):
    c, s = np.cos(ang_rad), np.sin(ang_rad)
    R = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return (R @ np.array(v).reshape(3, 1)).ravel()


def orient2d(a, b, c):
    ax, ay = a[:2]
    bx, by = b[:2]
    cx, cy = c[:2]
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)  # >0:CCW


def on_seg(a, b, p):
    ax, ay = a[:2]
    bx, by = b[:2]
    px, py = p[:2]
    return (min(ax, bx) - EPS <= px <= max(ax, bx) + EPS) and (
        min(ay, by) - EPS <= py <= max(ay, by) + EPS
    )


def seg_x(p1, p2, p3, p4):
    o1 = orient2d(p1, p2, p3)
    o2 = orient2d(p1, p2, p4)
    o3 = orient2d(p3, p4, p1)
    o4 = orient2d(p3, p4, p2)
    if (o1 * o2 < -EPS) and (o3 * o4 < -EPS):
        return True
    if abs(o1) <= EPS and on_seg(p1, p2, p3):
        return True
    if abs(o2) <= EPS and on_seg(p1, p2, p4):
        return True
    if abs(o3) <= EPS and on_seg(p3, p4, p1):
        return True
    if abs(o4) <= EPS and on_seg(p3, p4, p2):
        return True
    return False


def area_signed(poly):
    P = np.array(poly, float)
    x = P[:, 0]
    y = P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def ensure_ccw(*pts):
    return pts if area_signed(pts) > 0 else (pts[0], pts[3], pts[2], pts[1])


def diag_cross_inside(A, B, C, D):
    return seg_x(A, C, B, D)


def fit_into_box(pts, box_min, box_max, margin=0.2):
    P = np.array(pts, float)
    pmin = P[:, :2].min(axis=0)
    pmax = P[:, :2].max(axis=0)
    size = pmax - pmin
    box = (box_max - box_min)[:2] - margin * 2
    s = float(min(box[0] / max(size[0], EPS), box[1] / max(size[1], EPS)))
    o = box_min[:2] + margin
    out = []
    for p in pts:
        q = np.array(p, float)
        q[:2] = (q[:2] - pmin) * s + o
        out.append(q)
    return out, s
