"""Calibrated live phone pairs -> existing FFS/seg/bbox depth implementation.

Camera-specific calibration is mandatory. Laptop/phone calibration must never be
silently reused for two phone lenses. This module does not fabricate calibration.
"""
import json
from pathlib import Path
import time

import cv2
import numpy as np

from lib_phone_stereo import LENS_OFFSET_SPAN_MS


def load_phone_calibration(path, logical, physical, size):
    """(st, swap). swap=True 면 캘리의 (왼,오른) 이 --physical 의 첫 둘과 반대 — 수신 쌍을 뒤집어 쓴다."""
    st = json.loads(Path(path).read_text())
    want = [str(p) for p in physical[:2]]
    got = (st.get("phone") or {}).get("physical")
    if (st.get("phone") or {}).get("logical") != str(logical) or got not in (want, want[::-1]):
        raise ValueError(f"Calibration phone={st.get('phone')} does not match --logical {logical} --physical {want} "
                         f"(z_phone_calib.py 로 만든 json 의 phone.physical 과 같은 두 렌즈여야 함)")
    swap = got == want[::-1]
    if st.get("image_size") != list(size):
        raise ValueError("Calibration image_size does not match the phone output")
    for key in ("K1", "K2", "dist1", "dist2", "R", "T"):
        if key not in st or not np.isfinite(np.asarray(st[key], dtype=float)).all():
            raise ValueError(f"Missing/nonfinite calibration field: {key}")
    return st, swap


def gravity_frame(st, imu):
    """중력 센서(기기 프레임, 위쪽을 가리키는 반작용 벡터) -> cam1(왼쪽 렌즈, 정류 전) 기준 Z-up 세계 프레임.

    반환 dict(R_cam1_to_world(3x3), up_cam1, pitch_deg, roll_deg, ...) 또는 None (센서/캘리 회전 없음).
      z_world = 위(−중력), x_world = 카메라 x축의 수평 투영(오른쪽), y_world = z × x (수평 전방).
      pitch = 광축이 수평면에서 들린 각(+위), roll = 영상 가로축이 수평에서 기운 각.
    Android TYPE_GRAVITY 는 정지 시 가속도계와 같아 화면을 위로 두면 z=+9.81, 즉 벡터가 '위' 를 가리킨다.
    """
    g = (imu or {}).get("gravity")
    Rs = st.get("R_sensor_to_left")
    if not g or Rs is None:
        return None
    up = np.asarray(Rs, float) @ np.asarray(g["values"], float)
    n = np.linalg.norm(up)
    if not 8.0 < n < 11.5:                      # 자유낙하/흔들림 중이면 신뢰 불가
        return None
    up /= n
    x_cam, z_cam = np.array([1.0, 0, 0]), np.array([0, 0, 1.0])
    xw = x_cam - (x_cam @ up) * up
    if np.linalg.norm(xw) < 0.2:                # 카메라가 거의 수직으로 위/아래를 볼 때는 y축으로 기준
        xw = np.array([0, 1.0, 0]) - (np.array([0, 1.0, 0]) @ up) * up
    xw /= np.linalg.norm(xw); yw = np.cross(up, xw)
    R = np.vstack([xw, yw, up])
    return dict(R_cam1_to_world=R, up_cam1=up.round(5).tolist(), gravity_sensor=g["values"], dt_ms=g.get("dt_ms"),
                pitch_deg=float(np.degrees(np.arcsin(np.clip(z_cam @ up, -1, 1)))),
                roll_deg=float(np.degrees(np.arcsin(np.clip(x_cam @ up, -1, 1)))),
                frame="x=camera right (horizontal), y=forward (horizontal), z=up; origin=left lens")


def depth_colormap(depth, valid, zmin=0.3, zmax=3.0):
    """깊이맵 → 색: 가까움=빨강, 멂=파랑 (JET 역방향), 로그 스케일(스테레오 정밀도가 Z² 로 나빠지므로). 무효=검정. 오른쪽에 눈금 막대."""
    z = np.where(valid, depth, np.nan).astype(np.float32)
    t = (np.log(np.clip(z, zmin, zmax)) - np.log(zmin)) / (np.log(zmax) - np.log(zmin))     # 0=가까움 .. 1=멂
    u8 = np.clip((1.0 - np.nan_to_num(t, nan=1.0)) * 255, 0, 255).astype(np.uint8)         # JET: 0 파랑 .. 255 빨강
    img = cv2.applyColorMap(u8, cv2.COLORMAP_JET)
    img[~valid] = 0
    H, W = img.shape[:2]
    bar = cv2.applyColorMap(np.linspace(255, 0, H - 40, dtype=np.uint8).reshape(-1, 1).repeat(22, 1), cv2.COLORMAP_JET)  # 위 빨강(가까움)
    panel = np.zeros((H, 70, 3), np.uint8); panel[20:H - 20, 6:28] = bar
    for frac, label in ((0.0, f"{zmin:g}m"), (0.5, f"{np.sqrt(zmin * zmax):.2g}m"), (1.0, f"{zmax:g}m")):
        y = int(20 + frac * (H - 41))
        cv2.putText(panel, label, (31, y + 5), cv2.FONT_HERSHEY_SIMPLEX, .42, (255, 255, 255), 1)
    out = np.hstack([img, panel])
    cv2.putText(out, "depth  red=near  blue=far", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2)
    return out


def rotation_between(st, win, tL, tR):
    """왼쪽 노출 tL, 오른쪽 노출 tR (ns) 사이 폰 회전 -> 렌즈 사이 회전에 곱할 Rg (카메라 프레임). 구간·표본이 없으면 단위행렬.

    X_L(t_R) = Rg X_L(t_L) (평행이동 무시). 기기 프레임 자이로 적분을 Rs 로 카메라 프레임에 옮긴다. tL > tR 이면 역방향.
    """
    Rs = st.get("R_sensor_to_left")
    if Rs is None or tL == tR:
        return np.eye(3)
    import lib_phone_motion as pm
    Rg_dev = pm.gyro_integrated_rotation(win, min(tL, tR), max(tL, tR))          # X_dev(later) = Rg_dev X_dev(earlier)
    if Rg_dev is None:
        return np.eye(3)
    if tL > tR:
        Rg_dev = Rg_dev.T
    Rs = np.asarray(Rs, float)
    return Rs @ Rg_dev @ Rs.T


def skew_rotation(st, imu):
    """두 렌즈 노출 시각 사이 폰 회전(자이로 적분) → 이 쌍에 쓸 R' = R · Rg.

    왼쪽(초광각) 노출 t_L, 오른쪽(광각) 노출 t_R. 세계점의 왼쪽 카메라 좌표는 X_L(t_R) = Rg X_L(t_L) (평행이동 무시),
    스테레오 식 X_R = R X_L(t_R) + T 에 넣으면 X_R = (R Rg) X_L(t_L) + T. Rg 는 기기 프레임 자이로 적분을 Rs 로 카메라 프레임에 옮긴 것.
    반환 (Rg, deg) 또는 (I, 0).
    """
    win = (imu or {}).get("gyro_window") or []
    ts = (imu or {}).get("exposure_ts_ns")
    Rs = st.get("R_sensor_to_left")
    if len(win) < 2 or not ts or Rs is None or ts[0] == ts[1]:
        return np.eye(3), 0.0
    Rg = rotation_between(st, win, int(ts[0]), int(ts[1]))
    return Rg, float(np.degrees(np.arccos(np.clip((np.trace(Rg) - 1) / 2, -1, 1))))


OBSERVABLE_RAD_S = 0.05      # 영상 가로축·광축 둘레 각속도가 이 이상이어야 노출 차가 세로 어긋남(dy)으로 보인다 (70 ms 에 f=438px 로 ≥ 1.5 px)


def lens_offset_observable(st, imu):
    """이 순간의 자이로가 렌즈 노출 차를 추정할 만큼 세로 어긋남을 만드나. yaw(세로축 둘레)는 dy 를 만들지 않아 관측 불가."""
    g, Rs = (imu or {}).get("gyroscope"), st.get("R_sensor_to_left")
    if not g or Rs is None:
        return False
    w = np.asarray(Rs, float) @ np.asarray(g["values"][:3], float)
    return bool(np.hypot(w[0], w[2]) >= OBSERVABLE_RAD_S)


def estimate_lens_offset(st, win, t_ns, nL, nR, f_px, span_ms=None):
    """HAL 이 두 렌즈에 같은 시각을 보고해도 실제 노출은 어긋나 있다(S25 실측 약 70~78 ms). 그 차 Δt = t_R − t_L (ms, 부호 있음)를
    영상과 자이로로 추정한다. 렌즈 사이 회전을 R·Rg(Δt) 로 두고 대응점의 Sampson 에피폴라 오차(Cauchy 로버스트 합)를 Δt 에 대해
    최소화한다 (5 ms 격자 -> 1 ms). Δt 는 센서 두 개가 자유 주행하며 위상이 초당 ~4 ms 흘러 천천히 변한다.

    nL, nR : 원영상 대응점을 각 렌즈의 K·dist 로 정규화한 좌표. win : 기기 프레임 자이로 [(ts_ns, [wx, wy, wz]), …].
    반환 (dt_ms, cost(Δt=0), cost(Δt)). 실데이터: 폰을 0.13 rad/s 로 움직이던 쌍 dy 4.40 -> 0.49 px.
    """
    import lib_stereo as ls
    span = LENS_OFFSET_SPAN_MS if span_ms is None else span_ms
    R0, T0 = np.asarray(st["R"], float), np.asarray(st["T"], float)

    def cost(dt_ms):
        Rg = rotation_between(st, win, int(t_ns), int(t_ns) + int(dt_ms * 1e6))
        return float(np.sum(np.log1p((ls.epipolar_sampson(nL, nR, R0 @ Rg, T0) * f_px) ** 2)))
    best = min(np.arange(-span, span + 1, 5.0), key=cost)
    best = min(np.arange(best - 4, best + 5, 1.0), key=cost)
    return float(best), cost(0.0), cost(best)


def motion_px(imu, f_px, extra_ms=0.0):
    """노출 + 롤링셔터 읽기 동안 폰 회전으로 상이 움직인 양(px) = |ω|·(노출 + 롤링셔터 skew + extra)·f. 센서 없으면 None.

    frame_timing 값 = [물리별 오프셋 ms…, 노출 ms, 프레임 주기 ms, 롤링셔터 skew ms] (lib_phone_stereo.SENSOR_FRAME_TIMING).
    extra_ms : 보상되지 않은 두 렌즈 노출 차 (시각이 같게 보고돼 차를 아직 모르면 프레임 주기, 추정 뒤엔 추정 오차).
    """
    g, ft = (imu or {}).get("gyroscope"), (imu or {}).get("frame_timing")
    if not g or not ft or len(ft["values"]) < 3:
        return None
    w = float(np.linalg.norm(np.asarray(g["values"][:3], float)))
    return w * (float(ft["values"][-3]) + float(ft["values"][-1]) + extra_ms) * 1e-3 * f_px


EPI_FAIL_PX = 3.0     # 이 이상이면 다른 폰 캘리 등 명백한 오류 -> 중단 (1~3px 는 경고만)

class PhoneDepth:
    def __init__(self, a):
        import lib_rectify as lr
        st, self.swap = load_phone_calibration(a.calib_stereo, a.logical, a.physical, a.size)
        cal = [dict(K=np.array(st[f"K{i}"]), dist=np.array(st[f"dist{i}"]), image_size=st["image_size"])
               for i in (1, 2)]
        self.rp = lr.rectify_maps(*cal, np.array(st["R"]), np.array(st["T"]))
        self.cal, self.rp0 = cal, self.rp
        self.a, self.st = a, st
        # 캘리를 만든 번들의 초점 고정값과 다르면 광각 fx 가 달라져 dy·시차가 어긋난다
        self.focus_warning = None
        if st.get("focus_m") is not None and abs(float(st["focus_m"]) - float(getattr(a, "focus_m", st["focus_m"]))) > 1e-6:
            self.focus_warning = f"focus_mismatch:calib {st['focus_m']}m vs run {a.focus_m}m"
        self.model = None
        self.ep, self.ep_samples, self.ep_need = None, [], 3      # 정류 판정: 질감 있는 쌍 3개 중앙값 (check_rectification)
        self.lens_dt_ms = None                                     # 추정한 두 렌즈 실제 노출 차 (시각이 같게 보고될 때만 쓴다)
        self.rgbd_snapshot = None

    def _unknown_timing_rotation(self, fL, fR, imu):
        """HAL 이 두 렌즈에 같은 시각을 보고하는 상태 (S25 가 재시작 뒤 그렇게 보고: phys2=0 phys5=0, 실제론 ~70 ms 어긋남).

        자이로가 영상 세로 어긋남을 만들 만큼 클 때(lens_offset_observable) 대응점으로 Δt 를 새로 추정해 0.5 씩 섞어 이어 쓰고,
        작을 땐 이전 추정을 그대로 쓴다 (노출 차는 천천히 변하고, 자이로가 작으면 어차피 보상량이 작다). 반환 (Rg, deg, 추정했나).
        """
        g = (imu or {}).get("gyroscope")
        if not g or self.st.get("R_sensor_to_left") is None:
            return np.eye(3), 0.0, False
        import lib_stereo as ls
        t = int(imu["exposure_ts_ns"][0])
        span = int(LENS_OFFSET_SPAN_MS * 1e6)
        win = imu.get("gyro_window") or []
        if len(win) < 2:                                           # 오프라인 번들 등: 그 순간 자이로를 창 전체에 (상수 각속도 근사)
            win = [(t - span, list(g["values"][:3])), (t + span, list(g["values"][:3]))]
        estimated = False
        if lens_offset_observable(self.st, imu):
            pL, pR, _ = ls._match_sift(cv2.cvtColor(fL.bgr, cv2.COLOR_BGR2GRAY), cv2.cvtColor(fR.bgr, cv2.COLOR_BGR2GRAY), None, 0.75)
            if len(pL) >= 30:
                nL = ls._to_normalized(pL, np.asarray(self.st["K1"], float), np.asarray(self.st["dist1"], float))
                nR = ls._to_normalized(pR, np.asarray(self.st["K2"], float), np.asarray(self.st["dist2"], float))
                dt, _, _ = estimate_lens_offset(self.st, win, t, nL, nR, float(self.st["K1"][0][0]))
                self.lens_dt_ms = dt if self.lens_dt_ms is None else 0.5 * (self.lens_dt_ms + dt)
                estimated = True
        if self.lens_dt_ms is None:
            return np.eye(3), 0.0, False
        Rg = rotation_between(self.st, win, t, t + int(self.lens_dt_ms * 1e6))
        return Rg, float(np.degrees(np.arccos(np.clip((np.trace(Rg) - 1) / 2, -1, 1)))), estimated

    def check_rectification(self, left, right, motion_px=None):
        """정류 dy 검사. 질감 있는 쌍 ep_need 개의 중앙값으로 한 번 판정하고, 판정 후에는 다시 보지 않는다.

        - 질감 없는 쌍(unavailable)은 세지 않는다: 첫 쌍만 보던 때는 첫 쌍이 단색이면 검사가 영영 안 돌아
          다른 폰의 캘리(dy 27px)로도 depth 를 계속 냈다.
        - 한 쌍으로 판정하지 않는다: 손에 든 폰의 첫 쌍이 살짝 흔들려 dy 1.06px 로 라이브 전체가 멈췄다
          (같은 실행의 마지막 쌍은 0.74px, 정지 장면 0.25~0.55px). 틀린 캘리는 모든 쌍이 크게 넘으므로 중앙값으로도 잡힌다.
        - 움직이는 쌍은 세지 않는다: motion_px(노출+롤링셔터 동안 회전에 의한 상 이동, px)가 합격선(EPI_GATE_PX) 이상이면
          그 쌍의 dy 는 캘리가 아니라 흔들림을 잰다 (실측: 폰을 3.3 rad/s 로 돌리던 쌍 dy 4.77/2.59px 로 라이브가 멈췄다).
        판정 전에는 status="pending" (객체에 rectification_unverified 경고).
        """
        if self.ep is not None and self.ep["status"] == "ok":
            return
        import lib_rectify as lr
        import z_object_depth as od
        if motion_px is not None and motion_px >= od.EPI_GATE_PX:
            self.ep = self.ep or dict(status="unavailable", reason="moving")
            return
        ep = lr.epipolar_check(left, right)
        if ep["status"] != "ok":
            self.ep = self.ep or ep
            return
        self.ep_samples.append(ep)
        if len(self.ep_samples) < self.ep_need:
            self.ep = dict(ep, status="pending", n_pairs=len(self.ep_samples))
            return
        dy = float(np.median([e["dy_med"] for e in self.ep_samples]))
        inl = float(np.median([e["inlier_frac"] for e in self.ep_samples]))
        self.ep = dict(ep, dy_med=dy, inlier_frac=inl, n_pairs=len(self.ep_samples),
                       dy_med_pairs=[round(e["dy_med"], 3) for e in self.ep_samples])
        if dy >= EPI_FAIL_PX or inl < od.EPI_INLIER_FRAC:
            raise ValueError(f"Phone rectification failed: {self.ep}")
        if dy >= od.EPI_GATE_PX:       # 1~3px 로 일관되게 어긋남: 캘리가 틀린 게 아니라 초점·노출차·온도 등 작은 편차. 멈추지 않고 경고
            self.ep["marginal"] = True

    def __call__(self, pair, imu=None):
        import lib_ffs
        import lib_detect as ld
        import lib_rectify as lr
        import z_object_depth as od
        a, rp = self.a, self.rp
        t0 = time.perf_counter()
        fL, fR = (pair[1], pair[0]) if self.swap else (pair[0], pair[1])      # 캘리의 (왼,오른) 순서로
        if self.swap and imu and imu.get("exposure_ts_ns"):
            imu = dict(imu, exposure_ts_ns=list(reversed(imu["exposure_ts_ns"])))
        if imu and imu.get("per_frame"):
            # Pose validation must use the calibrated LEFT lens's exposure time,
            # even when CLI stream order is reversed.
            per_frame = imu["per_frame"]
            sensors = per_frame[1 if self.swap else 0]
            imu = {k: v for k, v in imu.items() if k in ("gyro_window", "exposure_ts_ns", "exposure_skew_ms")}
            imu.update(sensors)
        # 동기 어긋남(두 노출 시각 차) 동안의 폰 회전을 자이로로 보상: 0.02° 넘으면 이 쌍만 정류 테이블을 다시 만든다 (~10ms)
        Rg, skew_deg = skew_rotation(self.st, imu)
        ts = (imu or {}).get("exposure_ts_ns")
        unknown_timing = bool(ts) and ts[0] == ts[1]                # 두 렌즈 실제 노출은 같을 수 없다 -> 시각을 모른다는 뜻
        offset_estimated = False
        if unknown_timing:
            Rg, skew_deg, offset_estimated = self._unknown_timing_rotation(fL, fR, imu)
        if skew_deg > 0.02:
            rp = lr.rectify_maps(*self.cal, np.asarray(self.st["R"]) @ Rg, np.asarray(self.st["T"]))
        else:
            rp = self.rp0
        self.rp = rp
        left, right = lr.rectify_pair(fL.bgr, fR.bgr, rp)
        ft = ((imu or {}).get("frame_timing") or {}).get("values")
        period = float(ft[-2]) if ft and len(ft) >= 3 else 66.67
        extra_ms = (0.0 if not unknown_timing else (8.0 if self.lens_dt_ms is not None else period))     # 추정 오차 / 차를 아직 모름(최악 = 한 프레임 주기)
        self.check_rectification(left, right, motion_px(imu, rp["f"], extra_ms))
        if self.model is None:
            self.model = lib_ffs.load(valid_iters=a.iters)
        disp = lib_ffs.infer(self.model, cv2.cvtColor(left, cv2.COLOR_BGR2RGB),
                             cv2.cvtColor(right, cv2.COLOR_BGR2RGB), valid_iters=a.iters, scale=a.scale)
        valid, depth = od.valid_mask(disp, rp, (0.1, 20.0))
        points = lr.depth_to_points_cam1(np.where(valid, depth, np.nan).astype(np.float32), rp)
        mode = a.yolo if a.yolo != "none" else "both"
        dets = ld.detect_yolo(left, model=ld.DEFAULT_MODEL if mode == "bbox" else ld.DEFAULT_SEG_MODEL, device="0")
        if getattr(a, "blobs", True):      # YOLO 가 모르는 물체(큐브 등): 평면 위로 튀어나온 덩어리
            import lib_blobs
            dets = dets + lib_blobs.detect_blobs(disp, valid, depth, rp["f"], existing=dets)
        gf = gravity_frame(self.st, imu)
        overlays, results = [], {}
        for method in (["seg", "bbox"] if mode == "both" else [mode]):
            rows = []
            for i, d in enumerate(dets):
                rec = od._empty(d["label"], i+1, d, method)
                if self.st.get("scale_status") != "metric":
                    rec["warnings"].append("scale_not_validated:" + str(self.st.get("scale_status")))
                if self.ep["status"] != "ok":
                    rec["warnings"].append("rectification_unverified")
                elif self.ep.get("marginal"):
                    rec["warnings"].append(f"rectification_marginal:dy{self.ep['dy_med']:.2f}px")
                if self.focus_warning:
                    rec["warnings"].append(self.focus_warning)
                if method == "seg":
                    region = d["mask"]
                    if region is None:
                        rec["status"] = "no_mask"
                        rows.append(rec)
                        continue
                else:
                    region = np.zeros(depth.shape, np.uint8)
                    x, y, w, h = d["box"]
                    region[max(0,y):max(0,y+h), max(0,x):max(0,x+w)] = 255
                rec = od.aggregate(rec, region, valid, depth, points, rp=rp, outline=method=="seg")
                if gf and rec.get("center_cam1_m") is not None:
                    w = gf["R_cam1_to_world"] @ np.asarray(rec["center_cam1_m"], float)
                    rec["center_world_m"] = w.round(4).tolist()          # 중력 정렬: z = 카메라 기준 높이(+위)
                    rec["height_rel_camera_m"] = round(float(w[2]), 4)
                else:
                    rec["center_world_m"] = None; rec["height_rel_camera_m"] = None
                rows.append(rec)
            results[method] = rows
            vis = od.draw_overlay(left, dets, rows, method)
            cv2.putText(vis, f"{method} depth - {self.st.get('scale_status', 'unverified')}", (12,24),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (0,220,255), 2)
            overlays.append(vis)
        zr = getattr(a, "depth_range", None) or (0.3, 3.0)
        overlays.append(depth_colormap(depth, valid, float(zr[0]), float(zr[1])))
        report = dict(timestamp_ns=[fL.timestamp_ns, fR.timestamp_ns], physical_lr=self.st["phone"]["physical"],
                      exposure_skew_ms=(fR.timestamp_ns - fL.timestamp_ns) / 1e6, gyro_skew_compensation_deg=round(skew_deg, 4), motion_px=motion_px(imu, rp["f"], extra_ms),
                      lens_timing=("unknown" if unknown_timing else "reported"),
                      lens_offset_ms=(None if self.lens_dt_ms is None else round(self.lens_dt_ms, 1)), lens_offset_estimated=offset_estimated,
                      mode=mode, device="cuda:0",
                      imu={k: v for k, v in (gf or {}).items() if k != "R_cam1_to_world"} if gf else dict(available=False),
                      imu_raw={k: v for k, v in (imu or {}).items() if k != "gravity"},
                      ms=(time.perf_counter()-t0)*1000, epipolar=self.ep, objects=results,
                      calibration=str(a.calib_stereo), scale_status=self.st.get("scale_status", "unverified"))
        if getattr(a, "rgbd_viewer", False):
            self.rgbd_snapshot = dict(rgb=left, rgb_overlay=overlays[0], depth=depth, valid=valid, points=points,
                depth_color=depth_colormap(depth, valid, float(zr[0]), float(zr[1]))[:, :left.shape[1]],
                depth_range=tuple(float(v) for v in zr), K_rect=rp["P1"][:, :3].copy(), R1=rp["R1"].copy(),
                timestamp_ns=[int(fL.timestamp_ns), int(fR.timestamp_ns)],
                skew_ms=report["exposure_skew_ms"], scale_status=self.st.get("scale_status", "unverified"),
                imu=od._clean({k: v for k, v in (imu or {}).items()
                              if k in ("gyroscope", "gravity", "linear_acceleration", "game_rotation_vector")}))
        return np.hstack(overlays), od._clean(report)
