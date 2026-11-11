"""클래스 무관 객체 검출: 시차 맵에서 "지배 평면(책상·바닥·벽)보다 튀어나온 덩어리"를 찾는다.

YOLO(COCO 80종)가 모르는 물체(예: 5cm 큐브)를 YOLO 검출과 같은 dict(box/label/conf/mask)로 돌려준다.
책상처럼 큰 평면이 화면 대부분을 차지할 때 잘 동작한다. 평면이 없는 장면에서는 거짓 검출이 늘 수 있다.
"""
import cv2
import numpy as np

LABEL = "blob"


def fit_dominant_plane(disp, valid, iters=300, tol=0.6, stride=4, seed=0):
    """시차 평면 d = a*u + b*v + c 를 RANSAC 으로 맞춘다. 반환: (abc, 인라이어 잔차 MAD) 또는 None."""
    H, W = disp.shape
    vs, us = np.mgrid[0:H:stride, 0:W:stride]
    m = valid[::stride, ::stride]
    u, v, d = us[m].astype(float), vs[m].astype(float), disp[::stride, ::stride][m].astype(float)
    if len(d) < 200:
        return None
    rng = np.random.default_rng(seed)
    A = np.column_stack([u, v, np.ones_like(u)])
    best, best_n = None, 0
    for _ in range(iters):
        idx = rng.choice(len(d), 3, replace=False)
        try:
            abc = np.linalg.solve(A[idx], d[idx])
        except np.linalg.LinAlgError:
            continue
        n = int((np.abs(A @ abc - d) < tol).sum())
        if n > best_n:
            best, best_n = abc, n
    if best is None or best_n < 0.3 * len(d):
        return None                                   # 지배 평면 없음
    for _ in range(2):                                # 인라이어로 최소제곱 재맞춤
        inl = np.abs(A @ best - d) < tol
        best = np.linalg.lstsq(A[inl], d[inl], rcond=None)[0]
    res = (A @ best - d)[np.abs(A @ best - d) < tol]
    return best, float(np.median(np.abs(res - np.median(res))) * 1.4826)


def detect_blobs(disp, valid, depth, f_px, existing=(), min_px=120, size_m=(0.015, 0.5),
                 min_height_px=1.0, max_n=6, max_frac=0.1):
    """평면보다 가까이 튀어나온 연결 덩어리. existing = YOLO 검출 목록(이미 설명된 영역은 제외)."""
    H, W = disp.shape
    fit = fit_dominant_plane(disp, valid)
    if fit is None:
        return []
    (a, b, c), sigma = fit
    u = np.arange(W, dtype=np.float32)[None, :]
    v = np.arange(H, dtype=np.float32)[:, None]
    resid = np.where(valid, disp - (a * u + b * v + c), 0.0)
    thr = max(min_height_px, 3.0 * sigma)
    m = (resid > thr).astype(np.uint8)
    for det in existing:                              # YOLO 가 이미 잡은 영역은 뺀다
        x, y, w, h = det["box"]
        reg = det["mask"] if det.get("mask") is not None else None
        if reg is not None:
            m[cv2.dilate((reg > 0).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0] = 0
        else:
            m[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_px or area > max_frac * H * W:
            continue
        reg = lab == i
        z = float(np.median(depth[reg & valid]))
        if not np.isfinite(z):
            continue
        wm, hm = w * z / f_px, h * z / f_px
        if not (size_m[0] <= min(wm, hm) and max(wm, hm) <= size_m[1]):
            continue
        if area / float(w * h) < 0.3:                 # 속이 비거나 가는 띠(가장자리 잡음) 제외
            continue
        out.append({"box": (int(x), int(y), int(w), int(h)), "label": LABEL,
                    "conf": 1.0, "mask": reg.astype(np.uint8) * 255, "_area": int(area)})
    out.sort(key=lambda d: -d["_area"])
    for d in out:
        d.pop("_area")
    return out[:max_n]
