import unittest

import cv2
import numpy as np

import z_gravity_align as ga


def rot(axis, deg):
    return cv2.Rodrigues(np.radians(deg) * np.asarray(axis, float) / np.linalg.norm(axis))[0]


class GravityAlignTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.Rtrue = rot([1, 2, 3], 90) @ rot([0, 0, 1], 5)          # 센서 -> cam1 진짜 회전
        self.Rwrong = rot([0.3, 1, 0.2], 3.0) @ self.Rtrue          # 캘리가 3° 틀림
        self.G = [ga.unit(v) for v in ([0, 0, 1], [0.5, 0, 0.85], [0, 0.6, 0.8], [-0.4, 0.3, 0.86])]
        self.N = [ga.unit(self.Rtrue @ g + rng.normal(0, 0.003, 3)) for g in self.G]     # 평면 법선 (잡음 ~0.17°)

    def test_recovers_rotation_and_generalises(self):
        r = ga.align(self.G, self.N, self.Rwrong)
        self.assertGreater(np.mean(r["before"]), 2.0)
        self.assertLess(np.mean(r["after"]), 0.5)
        self.assertLess(np.mean(r["loo"]), 0.6)                      # 빼놓은 자세도 맞는다
        self.assertAlmostEqual(np.linalg.det(r["Rs"]), 1.0)

    def test_spread_detects_same_pose(self):
        self.assertLess(ga.spread_deg([self.G[0]] * 3), 1e-6)
        self.assertGreater(ga.spread_deg(self.G), 30)


if __name__ == "__main__":
    unittest.main()
