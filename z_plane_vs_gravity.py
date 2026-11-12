#!/usr/bin/env python3
"""z_plane_vs_gravity.py — RANSAC 평면 법선(lib_blobs)과 폰 중력 방향(inference.json 의 imu.up_cam1)의 각도.

책상 같은 수평면이 화면의 대부분을 차지하면 두 벡터는 같은 방향이어야 한다. 각도가 크면
캘리(R_sensor_to_left)·정류(R1)·시차 평면 중 하나가 틀렸다는 뜻이다. 폰 자세를 바꿔도 각도가 일정한지 본다.

  venv_ffs/bin/python z_plane_vs_gravity.py RUN_DIR [RUN_DIR ...]
  venv_ffs/bin/python z_plane_vs_gravity.py --inference A/inference.json --npz A/rgbd/rgbd.npz

RUN_DIR = z_phone_stereo.py --rgbd-viewer --out RUN_DIR 로 만든 폴더 (RUN_DIR/inference.json, RUN_DIR/rgbd/rgbd.npz).
출력: 폴더마다 한 줄 + 마지막 줄 요약. 각도(도)는 두 벡터 사이 각, 법선의 부호는 중력 쪽으로 맞춘다.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_blobs  # noqa: E402


def baseline_m(calib_path):
    st = json.loads(Path(calib_path).read_text())
    return float(st.get("baseline_m") or np.linalg.norm(np.asarray(st["T"], float)))


def plane_normal_cam1(depth, valid, K_rect, R1, baseline):
    """깊이 -> 시차 -> RANSAC 평면 -> 단위 법선 (정류 전 cam1 좌표). 반환 (n, 평면 인라이어 잡음 sigma_px)."""
    f, cx, cy = float(K_rect[0, 0]), float(K_rect[0, 2]), float(K_rect[1, 2])
    ok = valid & np.isfinite(depth) & (depth > 0)
    disp = np.where(ok, f * baseline / np.where(ok, depth, 1.0), 0.0).astype(np.float32)
    fit = lib_blobs.fit_dominant_plane(disp, ok)
    if fit is None:
        return None, None
    (a, b, c), sigma = fit
    # d = a u + b v + c  <->  n ∝ (a, b, (c + a cx + b cy) / f)   (정류된 cam1, 광축 +z)
    n = np.array([a, b, (c + a * cx + b * cy) / f])
    n /= np.linalg.norm(n)
    return np.asarray(R1, float).T @ n, sigma           # 정류 -> 원래 cam1 (imu.up_cam1 이 있는 좌표)


def angle_deg(n, up):
    up = np.asarray(up, float) / np.linalg.norm(up)
    if n @ up < 0:
        n = -n                                           # RANSAC 법선의 부호는 모호하다: 중력 쪽으로 맞춘다
    return float(np.degrees(np.arccos(np.clip(n @ up, -1, 1))))


def compare(inference, npz, calib=None):
    inf = json.loads(Path(inference).read_text())
    up = (inf.get("imu") or {}).get("up_cam1")
    if up is None:
        raise ValueError(f"{inference}: imu.up_cam1 없음 (중력 센서/캘리 R_sensor_to_left 필요)")
    z = np.load(npz)
    if calib is None:
        cand = [Path(npz).with_name("calib_phone_pair.json"), HERE / "calib_phone_pair.json"]
        calib = next((p for p in cand if p.exists()), None)
        if calib is None:
            raise FileNotFoundError("baseline 용 캘리 파일이 없다 (--calib)")
    n, sigma = plane_normal_cam1(z["depth_m"], z["valid"], z["K_rect"], z["R1"], baseline_m(calib))
    if n is None:
        return dict(angle_deg=None, reason="지배 평면 없음 (유효 화소의 30% 이상이 한 평면이어야 한다)")
    stale = None                                        # inference.json 과 rgbd 가 같은 프레임인지 (imu 는 inference.json, 깊이는 rgbd)
    fj = Path(npz).with_name("frame.json")
    if fj.exists() and inf.get("timestamp_ns"):
        t_rgbd = json.loads(fj.read_text()).get("timestamp_ns")
        if t_rgbd and abs(int(inf["timestamp_ns"][0]) - int(t_rgbd[0])) > 2e8:
            stale = f"타임스탬프 불일치 {(int(t_rgbd[0]) - int(inf['timestamp_ns'][0])) / 1e9:+.1f}s — 다른 프레임이라 각도 무의미"
    return dict(stale=stale, angle_deg=angle_deg(n, up), normal_cam1=n.round(4).tolist(), up_cam1=list(up),
                plane_sigma_px=round(sigma, 3), pitch_deg=inf["imu"].get("pitch_deg"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", help="RUN_DIR (inference.json + rgbd/rgbd.npz)")
    ap.add_argument("--inference"); ap.add_argument("--npz"); ap.add_argument("--calib")
    a = ap.parse_args()
    jobs = [(Path(r).name or r, Path(r) / "inference.json", Path(r) / "rgbd" / "rgbd.npz") for r in a.runs]
    if a.inference or a.npz:
        if not (a.inference and a.npz):
            ap.error("--inference 와 --npz 는 함께 줘야 한다")
        jobs.append((Path(a.inference).parent.name, Path(a.inference), Path(a.npz)))
    if not jobs:
        ap.error("RUN_DIR 또는 --inference/--npz 가 필요하다")
    angles = []
    for name, inf, npz in jobs:
        try:
            r = compare(inf, npz, a.calib)
        except (OSError, ValueError, KeyError) as e:
            print(f"{name}: 실패 - {e}"); continue
        if r["angle_deg"] is None:
            print(f"{name}: 판정 불가 - {r['reason']}"); continue
        if r["stale"]:
            print(f"{name}: 제외 - {r['stale']} (참고값 {r['angle_deg']:.2f}°)"); continue
        angles.append(r["angle_deg"])
        print(f"{name}: {r['angle_deg']:.2f}°  (법선 {r['normal_cam1']}, up {r['up_cam1']}, 평면 잡음 {r['plane_sigma_px']}px)")
    if len(angles) > 1:
        print(f"요약: n={len(angles)} 평균 {np.mean(angles):.2f}° 범위 {min(angles):.2f}~{max(angles):.2f}°")


if __name__ == "__main__":
    main()
