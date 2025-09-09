from __future__ import annotations
from typing import List, Sequence, Any


def _bbox(item: Any) -> Sequence[float]:
    if hasattr(item, "bbox"):
        return item.bbox
    return item["bbox"]


def reading_order(items: List[Any]) -> List[Any]:
    if not items:
        return []
    centers = []
    heights = []
    for it in items:
        x1, y1, x2, y2 = _bbox(it)
        centers.append((y1 + y2) / 2)
        heights.append(y2 - y1)
    avg_h = sum(heights) / len(heights)
    tol = avg_h * 0.7
    row_centers: List[float] = []
    assigned: List[tuple[Any, int]] = []
    for it, yc in sorted(zip(items, centers), key=lambda t: t[1]):
        for idx, rc in enumerate(row_centers):
            if abs(yc - rc) <= tol:
                row_centers[idx] = (rc + yc) / 2
                assigned.append((it, idx))
                break
        else:
            row_centers.append(yc)
            assigned.append((it, len(row_centers) - 1))

    def _area(it: Any) -> float:
        x1, y1, x2, y2 = _bbox(it)
        return (x2 - x1) * (y2 - y1)

    def _x1(it: Any) -> float:
        return _bbox(it)[0]

    def _y1(it: Any) -> float:
        return _bbox(it)[1]

    ordered = sorted(
        assigned,
        key=lambda t: (t[1], _x1(t[0]), _y1(t[0]), _area(t[0]))
    )
    return [it for it, _ in ordered]
