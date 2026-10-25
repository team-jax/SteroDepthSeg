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


if __name__ == "__main__":
    unittest.main()
