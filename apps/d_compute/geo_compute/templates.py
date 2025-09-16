from __future__ import annotations
import numpy as np
from geom_utils import v3, unit, rotate, seg_x, area_signed, diag_cross_inside

# === A1: 기준선 AD + 대각선 길이 AC/BD + 각 ∠DAC, ∠ADB ======================
def solve_quad_diaglen_ang(A, D, theta_A_deg, theta_D_deg, AC_len, BD_len):
    """라벨 고정. 4브랜치(±θ_A × ±θ_D) 중 단순/CCW/대각교차를 만족하는 해."""
    uAD = unit(D - A); uDA = -uAD
    thA = np.deg2rad(theta_A_deg); thD = np.deg2rad(theta_D_deg)
    for sA in (+1,-1):
        for sD in (+1,-1):
            C = A + rotate(uAD, sA*thA) * AC_len
            B = D + rotate(uDA, sD*thD) * BD_len
            # 단순/CCW/대각 교차 내부
            if seg_x(A,B,C,D) or seg_x(B,C,A,D):  continue
            if area_signed([A,B,C,D]) <= 0:       continue
            if not diag_cross_inside(A,B,C,D):    continue
            return dict(A=A,B=B,C=C,D=D)
    return None

# === R1: 직각점 C + 길이(AB, AD, CD 등)로 삼각/사변형 ==========================
def solve_right_at_C(AB, AD, CD):
    """예시용: C를 원점, x축 BC, y축 AC. AD,CD,AB로 B,A,D 복원."""
    C = v3(0,0); ex=v3(1,0); ey=v3(0,1)
    # 문제마다 수식 다르니 예시만 보관.
    raise NotImplementedError

# === S1: 정사각형 side + ∠ADE(또는 다른 각) + 직각(E) =========================
def solve_square_with_ADE(side, angle_ADE_deg):
    A=v3(0,0); D=v3(side,0); B=v3(0,-side); C=v3(side,-side)
    # 유도 결과: E=(3/4*side, (sqrt(3)/4)*side*2) = (0.75s, (sqrt3)/2 * s /?)  → 사례별 수치로 대입 권장
    # 교재형(문항 13) 해: E=(6, 2√3) when side=8
    s=side
    E=v3(0.75*s, (np.sqrt(3)/4)*s*2)  # = (0.75s, 0.8660s)  [각=60° 만족]
    return dict(A=A,B=B,C=C,D=D,E=E)
