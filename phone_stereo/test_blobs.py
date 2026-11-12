import unittest

import numpy as np

import lib_blobs as lb

H, W, F, B = 480, 640, 424.0, 0.0166


def scene(cube=True, sliver=False, seed=0):
    v = np.arange(H)[:, None] * np.ones((1, W))
    Z = 0.5 + 0.0004 * (v - 240)                       # 기울어진 책상
    if cube:
        Z[200:250, 300:352] -= 0.05                    # 5cm 큐브
    d = F * B / Z + np.random.default_rng(seed).normal(0, 0.15, (H, W))
    valid = np.ones((H, W), bool)
    if sliver:                                         # 화면 모서리의 얇은 가장자리 아티팩트 (실측에서 blob 으로 잡혔다)
        d[400:480, 0:12] += 3.0
    return d.astype(np.float32), valid, (F * B / d).astype(np.float32)


class BlobTests(unittest.TestCase):
    def test_finds_cube_and_nothing_without_it(self):
        r = lb.detect_blobs(*scene(), F)
        self.assertEqual([d["box"] for d in r], [(300, 200, 52, 50)])
        self.assertEqual(lb.detect_blobs(*scene(cube=False), F), [])

    def test_ignores_border_artifacts(self):
        d, v, z = scene(cube=False, sliver=True)
        self.assertEqual(lb.detect_blobs(d, v, z, F), [])


if __name__ == "__main__":
    unittest.main()
