import unittest

import cv2
import numpy as np

from lib_phone_depth import PhoneDepth


def textured(seed=1, h=240, w=320):
    r = np.random.default_rng(seed)
    t = cv2.resize(r.random((30, 40)).astype(np.float32), (w + 40, h + 40), interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(cv2.normalize(t, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def pair(seed, dy):
    """시차 8px + 세로 어긋남 dy px 인 쌍."""
    t = textured(seed)
    return t[20:260, 28:348], t[20 + dy:260 + dy, 20:340]


def checker(need=3):
    d = PhoneDepth.__new__(PhoneDepth)     # 캘리 파일·GPU 없이 정류 검사만
    d.ep, d.ep_samples, d.ep_need = None, [], need
    return d


class RectificationCheckTests(unittest.TestCase):
    def test_textureless_pairs_are_not_counted_and_bad_rectification_raises(self):
        d = checker()
        blank = np.full((240, 320, 3), 128, np.uint8)
        d.check_rectification(blank, blank)
        self.assertEqual(d.ep["status"], "unavailable")
        d.check_rectification(*pair(1, 12))                       # 다른 폰 캘리처럼 세로 12px
        d.check_rectification(*pair(2, 12))
        self.assertEqual(d.ep["status"], "pending")
        with self.assertRaises(ValueError):
            d.check_rectification(*pair(3, 12))

    def test_one_shaky_pair_does_not_stop_the_run(self):
        d = checker()
        d.check_rectification(*pair(1, 2))                        # 흔들린 첫 쌍 (dy 2px)
        d.check_rectification(*pair(2, 0))
        d.check_rectification(*pair(3, 0))
        self.assertEqual(d.ep["status"], "ok")
        self.assertEqual(d.ep["n_pairs"], 3)

    def test_marginal_dy_warns_but_does_not_stop(self):
        d = checker()
        for s in (1, 2, 3):
            d.check_rectification(*pair(s, 1))                    # 일관되게 1px: 중단하지 않고 marginal
        self.assertEqual(d.ep["status"], "ok")
        self.assertTrue(d.ep.get("marginal"))

    def test_moving_pairs_are_not_counted(self):
        d = checker()
        for s in (1, 2, 3):
            d.check_rectification(*pair(s, 12), motion_px=20.0)     # 3.3 rad/s 로 돌리던 쌍: 세지 않음 (예외 없음)
        self.assertEqual(d.ep_samples, [])
        for s in (4, 5, 6):
            d.check_rectification(*pair(s, 0), motion_px=0.5)      # 손에 든 정도(0.09 rad/s)는 센다
        self.assertEqual(d.ep["status"], "ok")

    def test_motion_px_formula(self):
        from lib_phone_depth import motion_px
        imu = dict(gyroscope=dict(values=[0, 3.3, 0]), frame_timing=dict(values=[0.0, 60.8, 8.3337, 66.6667, 11.0865]))
        self.assertAlmostEqual(motion_px(imu, 312.0), 3.3 * (8.3337 + 11.0865) * 1e-3 * 312.0, places=6)
        self.assertIsNone(motion_px({}, 312.0))

    def test_verdict_is_kept_and_offline_judges_one_pair(self):
        d = checker(need=1)
        d.check_rectification(*pair(2, 0))
        self.assertEqual(d.ep["status"], "ok")
        blank = np.full((240, 320, 3), 128, np.uint8)
        d.check_rectification(blank, blank)                        # 판정 후에는 다시 보지 않는다
        self.assertEqual(d.ep["status"], "ok")
        with self.assertRaises(ValueError):
            checker(need=1).check_rectification(*pair(1, 12))


class LensOffsetTests(unittest.TestCase):
    """HAL 이 두 렌즈에 같은 시각을 보고할 때의 노출 차 추정. 정답 데이터는 추정기와 독립된 소각 회전 모델(Rodrigues)로 만든다."""
    @classmethod
    def setUpClass(cls):
        import json
        from pathlib import Path
        from lib_phone_depth import estimate_lens_offset, lens_offset_observable, rotation_between
        cls.fns = (estimate_lens_offset, lens_offset_observable, rotation_between)
        cls.st = json.loads((Path(__file__).resolve().parent.parent / "calib_phone_pair.json").read_text())

    def scene(self, w_dev, dt_ms, noise_px=0.2, seed=0):
        st, t = self.st, 10**12
        R0, T0 = np.asarray(st["R"], float), np.asarray(st["T"], float)
        Rs = np.asarray(st["R_sensor_to_left"], float)
        rng = np.random.default_rng(seed)
        X = np.column_stack([rng.uniform(-0.8, 0.8, 300), rng.uniform(-0.6, 0.6, 300), rng.uniform(0.5, 3.0, 300)])
        Rg = Rs @ cv2.Rodrigues(-np.asarray(w_dev, float) * dt_ms * 1e-3)[0] @ Rs.T      # X_L(t_R) = Rg X_L(t_L), 상수 각속도
        nL = X[:, :2] / X[:, 2:3]
        Y = (R0 @ (Rg @ X.T)).T + T0
        nR = Y[:, :2] / Y[:, 2:3]
        f = float(st["K1"][0][0])
        nL = nL + rng.normal(0, noise_px / f, nL.shape); nR = nR + rng.normal(0, noise_px / f, nR.shape)
        win = [(t - 10**8, list(w_dev)), (t + 10**8, list(w_dev))]
        return win, t, nL, nR, f

    def test_recovers_offset_for_several_true_values(self):
        est = self.fns[0]
        for dt in (78.0, 55.0, -40.0, 20.0):
            win, t, nL, nR, f = self.scene([0.02, 0.15, 0.04], dt)
            got, c0, c1 = est(self.st, win, t, nL, nR, f)
            self.assertLess(abs(got - dt), 3.0, msg=f"true {dt} got {got}")
            self.assertLess(c1, c0)

    def test_observability_needs_roll_or_pitch_not_yaw(self):
        obs = self.fns[1]
        Rs = np.asarray(self.st["R_sensor_to_left"], float)
        yaw_cam = np.array([0.0, 0.3, 0.0])                      # 카메라 y 축(세로) 둘레 = dy 를 만들지 않는다
        pitch_cam = np.array([0.15, 0.0, 0.0])
        for w_cam, expect in ((yaw_cam, False), (pitch_cam, True), (np.zeros(3), False)):
            self.assertEqual(obs(self.st, dict(gyroscope=dict(values=list(Rs.T @ w_cam)))), expect, msg=str(w_cam))
        self.assertFalse(obs(self.st, {}))

    def test_motion_px_adds_unresolved_offset(self):
        from lib_phone_depth import motion_px
        imu = dict(gyroscope=dict(values=[0, 0.1, 0]), frame_timing=dict(values=[0.0, 0.0, 8.3337, 66.6667, 14.9166]))
        self.assertAlmostEqual(motion_px(imu, 438.0, 66.6667) - motion_px(imu, 438.0), 0.1 * 66.6667e-3 * 438.0, places=6)


if __name__ == "__main__":
    unittest.main()
