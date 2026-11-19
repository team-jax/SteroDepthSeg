#!/usr/bin/env python3
"""z_gravity_align.py — 중력 센서로 폰 센서 프레임 → 왼쪽 렌즈 회전(R_sensor_to_left)을 캘리와 맞춘다.

수평한 책상면(= 중력 반대 방향이 법선)을 여러 자세에서 보면, 자세마다
    평면 법선 n_i (cam1, 스테레오 깊이에서)   ≈   R · g_i (센서 중력 단위벡터 g_i)
이어야 한다. 이 R 을 Kabsch(SVD)로 구해 calib 의 R_sensor_to_left 후보로 쓴다.
roll/pitch(중력과 수직한 두 축)는 맞출 수 있지만 중력 축 둘레(yaw)는 중력으로 알 수 없다 — 자세가 서로 달라야 풀린다.

  venv_ffs/bin/python z_gravity_align.py RUN1 RUN2 RUN3 [...] [--calib calib_phone_pair.json] [--out calib_phone_pair_gravity.json]

RUN = z_phone_stereo.py --rgbd-viewer --out RUN (RUN/inference.json + RUN/rgbd/rgbd.npz), 폰을 고정하고 6초 이상. (README "평면 법선 vs 중력 방향")
출력: 자세별 맞추기 전/후 각도, 한 자세를 빼고 맞춘 뒤 그 자세를 평가한 오차(leave-one-out), 보정 회전 크기.
--out 에 새 캘리 파일(R_sensor_to_left 만 교체, history 기록)을 쓴다. 기존 캘리는 덮어쓰지 않는다.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import z_plane_vs_gravity as pg  # noqa: E402

MIN_POSES = 3
MAX_PLANE_SIGMA_PX = 0.3      # 평면 잡음이 이보다 크면 그 자세는 평면이 아니다
MIN_SPREAD_DEG = 10.0         # 자세들의 중력 방향이 이 정도는 퍼져 있어야 풀린다


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def kabsch(G, N):
    """sum |R g_i - n_i|^2 을 최소화하는 회전 R (3x3, det=+1)."""
    H = np.asarray(G, float).T @ np.asarray(N, float)       # sum g_i n_i^T
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1, 1, d]) @ U.T


def ang(a, b):
    return float(np.degrees(np.arccos(np.clip(unit(a) @ unit(b), -1, 1))))


def rot_deg(R):
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))


def spread_deg(G):
    """자세들 중력 방향의 최대 벌어짐(도)."""
    return max(ang(a, b) for a in G for b in G)


def align(G, N, Rs0):
    """반환 dict: Rs(새 회전), before/after/loo (자세별 각도, 도), delta_deg."""
    G, N = [unit(g) for g in G], [unit(n) for n in N]
    Rs = kabsch(G, N)
    loo = []
    for i in range(len(G)):
        idx = [j for j in range(len(G)) if j != i]
        loo.append(ang(kabsch([G[j] for j in idx], [N[j] for j in idx]) @ G[i], N[i]))
    return dict(Rs=Rs, before=[ang(Rs0 @ g, n) for g, n in zip(G, N)], after=[ang(Rs @ g, n) for g, n in zip(G, N)],
                loo=loo, delta_deg=rot_deg(Rs @ np.asarray(Rs0, float).T), spread_deg=spread_deg(G))


def pose_vectors(run, calib):
    """(g_sensor 단위, n_cam1 단위(중력 쪽 부호), 사유) — 쓸 수 없으면 (None, None, 이유)."""
    run = Path(run)
    inf = json.loads((run / "inference.json").read_text())
    imu = inf.get("imu") or {}
    g = imu.get("gravity_sensor")
    if g is None:
        return None, None, "imu.gravity_sensor 없음"
    gn = np.linalg.norm(g)
    if not 8.0 < gn < 11.5:
        return None, None, f"|g|={gn:.2f} (흔들림/자유낙하)"
    r = pg.compare(run / "inference.json", run / "rgbd" / "rgbd.npz", calib)
    if r.get("stale"):
        return None, None, r["stale"]
    if r["angle_deg"] is None:
        return None, None, r["reason"]
    if r["plane_sigma_px"] > MAX_PLANE_SIGMA_PX:
        return None, None, f"평면 잡음 {r['plane_sigma_px']}px (수평 책상면이 아님)"
    n = unit(r["normal_cam1"])
    if n @ unit(imu["up_cam1"]) < 0:
        n = -n
    return unit(g), n, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--calib", default=str(HERE / "calib_phone_pair.json"))
    ap.add_argument("--out", default=str(HERE / "calib_phone_pair_gravity.json"))
    a = ap.parse_args()
    st = json.loads(Path(a.calib).read_text())
    Rs0 = np.asarray(st["R_sensor_to_left"], float)
    G, N, names = [], [], []
    for run in a.runs:
        try:
            g, n, why = pose_vectors(run, a.calib)
        except (OSError, ValueError, KeyError) as e:
            g, n, why = None, None, str(e)
        if why:
            print(f"{Path(run).name}: 제외 - {why}"); continue
        G.append(g); N.append(n); names.append(Path(run).name)
    if len(G) < MIN_POSES:
        sys.exit(f"쓸 수 있는 자세 {len(G)}개 < {MIN_POSES}. 평면이 화면 대부분인 자세를 더 찍을 것")
    sp = spread_deg(G)
    if sp < MIN_SPREAD_DEG:
        sys.exit(f"자세들의 중력 방향이 {sp:.1f}° 밖에 안 벌어졌다 (< {MIN_SPREAD_DEG}°). 기울기를 크게 다르게 찍을 것")
    r = align(G, N, Rs0)
    print(f"자세 {len(G)}개, 중력 방향 벌어짐 {r['spread_deg']:.1f}°")
    print(f"{'자세':12s} {'맞추기 전':>9s} {'맞춘 뒤':>8s} {'LOO 오차':>9s}")
    for nm, b, af, lo in zip(names, r["before"], r["after"], r["loo"]):
        print(f"{nm:12s} {b:8.2f}° {af:7.2f}° {lo:8.2f}°")
    print(f"평균: 전 {np.mean(r['before']):.2f}° -> 후 {np.mean(r['after']):.2f}°, LOO {np.mean(r['loo']):.2f}°  "
          f"(R_sensor_to_left 보정 {r['delta_deg']:.2f}°)")
    if np.mean(r["loo"]) >= np.mean(r["before"]):
        print("[주의] 한 자세를 빼고 맞춘 오차(LOO)가 개선되지 않았다 — 보정이 새 자세에 일반화되지 않는다. 저장하지 않는다.")
        return
    new = dict(st)
    new["R_sensor_to_left"] = r["Rs"].tolist()
    new.setdefault("history", [])
    new["history"] = list(new["history"]) + [dict(step="gravity_align", poses=names, before_deg=round(float(np.mean(r["before"])), 3),
                                                 after_deg=round(float(np.mean(r["after"])), 3), loo_deg=round(float(np.mean(r["loo"])), 3),
                                                 delta_deg=round(r["delta_deg"], 3), from_calib=Path(a.calib).name)]
    Path(a.out).write_text(json.dumps(new, indent=2))
    print(f"저장: {a.out}  (기존 {Path(a.calib).name} 은 그대로. 확인 뒤 이 파일을 쓰려면 --calib-stereo 로 지정)")


if __name__ == "__main__":
    main()
