# c:\Users\PC\Desktop\gptinput\anchor_ir.py
from __future__ import annotations
import os, subprocess, json, tempfile
import numpy as np
import cv2
import shutil
from PIL import Image
from svgpathtools import svg2paths2

def imread_gray_any(path: str):
    """한글/유니코드 경로에서도 안전하게 GRAY 읽기"""
    img = None
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    except Exception:
        img = None
    if img is None:
        try:
            img = np.array(Image.open(path).convert("L"))
        except Exception:
            img = None
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return img

def _is_valid_svg(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(2048).lower()
        return b"<svg" in head
    except Exception:
        return False


def vectorize_to_svg(img_path: str, out_svg: str, method: str = "potrace", threshold: float = 0.60):
    os.makedirs(os.path.dirname(out_svg), exist_ok=True)

    # 1) 이미지 로드(유니코드 안전)
    img = imread_gray_any(img_path)
    if img is None:
        raise RuntimeError(f"Failed to read image: {img_path}")

    # 2) 이진화
    _, bw = cv2.threshold(img, int(threshold*255), 255, cv2.THRESH_BINARY)

    if method.lower() == "potrace":
        # ---- 임시 ASCII 경로 + PGM 사용 ----
        if not shutil.which("potrace"):
            raise RuntimeError("potrace not found. Install via 'choco install potrace' or use --vectorizer inkscape")
        tmpdir = tempfile.mkdtemp(prefix="anchorir_")
        pgm = os.path.join(tmpdir, "in.pgm")
        svg_tmp = os.path.join(tmpdir, "out.svg")

        ok, buf = cv2.imencode(".pgm", bw)
        if not ok:
            raise RuntimeError("cv2.imencode('.pgm') failed")
        buf.tofile(pgm)

        try:
            subprocess.run(["potrace", pgm, "-s", "-o", svg_tmp, "--turdsize", "10", "--alphamax", "1.2"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"potrace failed: {e.stderr.decode(errors='ignore') if e.stderr else e}") from e

        if not os.path.exists(svg_tmp) or not _is_valid_svg(svg_tmp):
            raise RuntimeError(f"potrace produced invalid svg: {svg_tmp}")

        shutil.copyfile(svg_tmp, out_svg)
        return out_svg

    elif method.lower() == "inkscape":
        # (원하면 inkscape 분기도 여기에: select-all; selection-trace-bitmap; export-plain-svg 등)
        raise NotImplementedError("Inkscape branch not patched here.")
    else:
        raise ValueError(f"Unknown vectorizer: {method}")

def _sample_path_even_arclength(path, n=600):
    # arc-length 균등 샘플링(근사)
    import numpy as np
    t_dense = np.linspace(0, 1, 5000)
    pts = np.array([path.point(t) for t in t_dense])
    xy = np.c_[pts.real, pts.imag]
    seg = xy[1:] - xy[:-1]
    d = np.sqrt((seg**2).sum(axis=1))
    s = np.r_[0, d.cumsum()]
    s_target = np.linspace(0, s[-1], n)
    xs = np.interp(s_target, s, xy[:,0])
    ys = np.interp(s_target, s, xy[:,1])
    P = np.c_[xs, ys]
    # 중복점 제거(픽셀 진동 완화)
    keep = [0]
    for i in range(1, len(P)):
        if np.linalg.norm(P[i] - P[keep[-1]]) >= 0.8:
            keep.append(i)
    return P[keep]

def _path_len_px(path) -> float:
    try:
        return float(path.length(error=1e-3))
    except Exception:
        return 0.0


def rdp(P, eps=1.2):
    if P is None or len(P) < 3:
        return P
    def _perp_dist(pt, a, b):
        if (a == b).all():
            return float(np.linalg.norm(pt - a))
        return float(abs(np.cross(b - a, a - pt)) / np.linalg.norm(b - a))
    def _rdp(M):
        dmax = 0.0
        idx = 0
        a, b = M[0], M[-1]
        for i in range(1, len(M) - 1):
            d = _perp_dist(M[i], a, b)
            if d > dmax:
                idx, dmax = i, d
        if dmax > eps:
            rec1 = _rdp(M[: idx + 1])
            rec2 = _rdp(M[idx:])
            return np.vstack((rec1[:-1], rec2))
        else:
            return np.vstack((a, b))
    return _rdp(P)


def svg_to_polylines(
    svg_path: str,
    *,
    sample_step_px: float = 3.0,
    min_bbox_area_px2: float = 80.0,
    min_path_len_px: float = 40.0,
    max_paths: int = 600,
    rdp_eps_px: float = 1.2,
    total_points_cap: int = 50000,
    quantum_px: float = 0.1,
):
    paths, attrs, svg_attr = svg2paths2(svg_path)
    cand = []
    for i, p in enumerate(paths):
        try:
            xmin, xmax, ymin, ymax = p.bbox()
        except Exception:
            continue
        area = max(0.0, (xmax - xmin)) * max(0.0, (ymax - ymin))
        if area < min_bbox_area_px2:
            continue
        L = _path_len_px(p)
        if L < min_path_len_px:
            continue
        cand.append((i, p, L))

    cand.sort(key=lambda x: x[2], reverse=True)
    cand = cand[:max_paths]

    total_pts = 0
    polys = []
    for i, p, L in cand:
        n = int(max(20, min(300, np.ceil(L / max(1e-6, sample_step_px)))))
        try:
            P = _sample_path_even_arclength(p, n)
        except Exception:
            continue
        if P is None or len(P) == 0:
            continue
        P = rdp(P, eps=rdp_eps_px)
        if P is None or len(P) == 0:
            continue
        if quantum_px and quantum_px > 0:
            P = np.round(P / quantum_px, 0) * quantum_px
        polys.append((f"path{i}", P))
        total_pts += len(P)
        if total_pts > total_points_cap:
            break
    try:
        print(f"[anchor] total polylines: {len(polys)}, total points: {sum(len(P) for _, P in polys)}")
    except Exception:
        pass
    return polys, svg_attr

def detect_axes_hints(gray_img):
    H, W = gray_img.shape[:2]
    lines = cv2.HoughLinesP(gray_img, 1, np.pi/180, threshold=120,
                            minLineLength=int(0.6*min(W,H)), maxLineGap=3)
    if lines is None: return []
    lines = lines[:,0,:]
    # 가장 긴 수평/수직 후보 2개 → 간단히 top-2 by length
    lines = sorted(lines, key=lambda L: np.hypot(L[2]-L[0], L[3]-L[1]), reverse=True)[:8]
    hints = []
    for i,(x1,y1,x2,y2) in enumerate(lines):
        hints.append({"id": f"axcand{i}", "line_px": [[int(x1),int(y1)], [int(x2),int(y2)]], "conf": 0.7})
    return hints

def make_affine(frame_w: float, frame_h: float, W: int, H: int, rotate: bool=False):
    sx = frame_w / W
    sy = frame_h / H
    A  = [[sx, 0.0],[0.0, -sy]]
    t  = [-frame_w/2, frame_h/2]
    return A, t

def _svg_size_from_attr(svg_attr):
    vb = svg_attr.get('viewBox') if isinstance(svg_attr, dict) else None
    if vb:
        try:
            parts = vb.replace(',', ' ').split()
            if len(parts) == 4:
                _, _, w, h = map(float, parts)
                return w, h
        except Exception:
            pass
    try:
        w = float(svg_attr.get('width', 0)) if isinstance(svg_attr, dict) else 0
    except Exception:
        w = 0
    try:
        h = float(svg_attr.get('height', 0)) if isinstance(svg_attr, dict) else 0
    except Exception:
        h = 0
    return (w or None), (h or None)

def build_anchor_item(image_path: str,
                      frame_w: float = 14, frame_h: float = 8,
                      dpi: int = 300,
                      vectorizer: str = "potrace",
                      points_per_path: int = 600,
                      crop_bbox=None) -> dict:
    # 0) 입력 래스터 로드 및 필요 시 크롭
    gray_full = imread_gray_any(image_path)
    if gray_full is None:
        raise RuntimeError(f"Failed to read image: {image_path}")

    crop_origin = (0, 0)
    gray = gray_full
    tmpdir_crop = None
    src_for_vectorize = image_path

    if crop_bbox is not None and isinstance(crop_bbox, (list, tuple)) and len(crop_bbox) == 4:
        x0, y0, w_or_x1, h_or_y1 = crop_bbox
        try:
            x0 = int(round(float(x0))); y0 = int(round(float(y0)))
            w_or_x1 = float(w_or_x1); h_or_y1 = float(h_or_y1)
        except Exception:
            x0 = y0 = 0; w_or_x1 = h_or_y1 = 0
        # 지원: [x,y,w,h] 또는 [x0,y0,x1,y1]
        if w_or_x1 > 0 and h_or_y1 > 0 and (w_or_x1 <= gray_full.shape[1] and h_or_y1 <= gray_full.shape[0]) and (w_or_x1 > x0 and h_or_y1 > y0):
            x1 = int(round(w_or_x1)); y1 = int(round(h_or_y1))
            w = x1 - x0; h = y1 - y0
        else:
            w = int(round(w_or_x1)); h = int(round(h_or_y1))
        Hf, Wf = gray_full.shape[:2]
        if w > 0 and h > 0:
            x0 = max(0, min(x0, Wf-1)); y0 = max(0, min(y0, Hf-1))
            x1 = max(0, min(x0 + w, Wf)); y1 = max(0, min(y0 + h, Hf))
            if x1 > x0 and y1 > y0:
                gray = gray_full[y0:y1, x0:x1]
                crop_origin = (x0, y0)
                # 크롭 이미지를 임시 파일에 저장하여 유니코드 안전 경로로 벡터화
                tmpdir_crop = tempfile.mkdtemp(prefix="anchorir_crop_")
                crop_png = os.path.join(tmpdir_crop, "crop.png")
                ok, buf = cv2.imencode(".png", gray)
                if not ok:
                    raise RuntimeError("cv2.imencode('.png') failed for crop")
                buf.tofile(crop_png)
                src_for_vectorize = crop_png

    # 1) SVG 벡터화(크롭된 경로가 있으면 그걸 사용)
    out_svg = os.path.join(os.path.dirname(image_path), "_anchorir_out.svg")
    svg_path = vectorize_to_svg(src_for_vectorize, out_svg, method=vectorizer)

    # 2) SVG → 폴리라인(px)
    polylines, svg_attr = svg_to_polylines(svg_path)

    # 3) 힌트(선택) - 크롭된 좌표계 기준으로 검출
    axes_hints = detect_axes_hints(gray)

    # SVG 크기로 좌표계 정합
    W_svg, H_svg = _svg_size_from_attr(svg_attr)
    H_ras, W_ras = gray.shape[:2]
    sx = (W_svg / W_ras) if (W_svg and W_ras) else 1.0
    sy = (H_svg / H_ras) if (H_svg and H_ras) else 1.0
    for h in axes_hints:
        try:
            (x1, y1), (x2, y2) = h["line_px"]
            h["line_px"] = [[round(x1 * sx, 2), round(y1 * sy, 2)],
                            [round(x2 * sx, 2), round(y2 * sy, 2)]]
        except Exception:
            continue

    # 4) 변환행렬
    H, W = gray.shape[:2]
    use_W = int(W_svg) if W_svg else W
    use_H = int(H_svg) if H_svg else H
    A, t = make_affine(frame_w, frame_h, use_W, use_H)

    # 5) anchors 구성 (분류 없이)
    edges = []
    for pid, P in polylines:
        if len(P) <= 6 and np.linalg.norm(P[0]-P[-1]) > 10:
            edges.append({"id": pid, "kind":"segment_px",
                          "p1_px": P[0].round(2).tolist(), "p2_px": P[-1].round(2).tolist(),
                          "conf": 0.90})
        else:
            edges.append({"id": pid, "kind":"polyline_px",
                          "pts_px": np.round(P,2).tolist(), "conf": 0.90})

    item = {
        "category": "Picture",
        "type": "raster_with_anchors",
        "image": {
            "uri": f"file://{src_for_vectorize}",
            "size_px": [use_W, use_H],
            "dpi": dpi
        },
        "transform": {
            "px_to_manim": { "A": A, "t": t },
            "tolerances": { "pos_px": 1.0, "ang_deg": 1.0, "len_px": 2.0 }
        },
        "anchors": {
            "edges": edges,
            "curves": [],         # 필요하면 분리해서 채움
            "points": [],         # 교점/코너 후보를 추가할 수 있음
            "axes_hints": axes_hints,
            "text_boxes": []      # OCR 붙이고 싶으면 여기에
        }
    }
    return item
