"""Shape tests for the humanised track: rounded corners, wobble, uneven splits."""

import math
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import location_sim as sim  # noqa: E402

SQUARE = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0), (-100.0, -100.0)]


def turn_degrees(points):
    out = []
    for previous, corner, following in zip(points, points[1:-1], points[2:]):
        v1 = (corner[0] - previous[0], corner[1] - previous[1])
        v2 = (following[0] - corner[0], following[1] - corner[1])
        length = math.hypot(*v1) * math.hypot(*v2)
        if length < 1e-9:
            continue
        cosine = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / length))
        out.append(math.degrees(math.acos(cosine)))
    return out


class CornerTest(unittest.TestCase):
    def test_right_angles_become_bends(self):
        rounded = sim.round_corners(SQUARE, radius=9.0, step=1.0)
        self.assertLess(max(turn_degrees(rounded)), 25.0)

    def test_endpoints_survive(self):
        rounded = sim.round_corners(SQUARE, radius=9.0, step=1.0)
        self.assertEqual(rounded[0], SQUARE[0])
        self.assertEqual(rounded[-1], SQUARE[-1])

    def test_short_cut_keeps_length_sane(self):
        rounded = sim.round_corners(SQUARE, radius=9.0, step=1.0)
        before = sim.path_length(SQUARE)
        after = sim.path_length(rounded)
        self.assertGreater(after, before * 0.93)
        self.assertLessEqual(after, before * 1.02)

    def test_straight_line_is_untouched(self):
        line = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
        self.assertAlmostEqual(sim.path_length(sim.round_corners(line, step=1.0)), 200.0, places=3)


class WobbleTest(unittest.TestCase):
    def test_offset_stays_within_the_pavement(self):
        straight = [(float(x), 0.0) for x in range(0, 400, 2)]
        shifted = sim.wobble(straight, amplitude=1.7, seed=3)
        self.assertLessEqual(max(abs(point[1]) for point in shifted), 1.7 + 1e-6)
        self.assertGreater(max(abs(point[1]) for point in shifted), 0.5)

    def test_seed_is_reproducible(self):
        line = [(float(x), 0.0) for x in range(0, 200, 2)]
        self.assertEqual(sim.wobble(line, seed=5), sim.wobble(line, seed=5))
        self.assertNotEqual(sim.wobble(line, seed=5), sim.wobble(line, seed=6))

    def test_offset_is_smooth(self):
        straight = [(float(x), 0.0) for x in range(0, 600, 2)]
        shifted = sim.wobble(straight, amplitude=1.7, seed=9)
        steps = [abs(b[1] - a[1]) for a, b in zip(shifted, shifted[1:])]
        self.assertLess(max(steps), 0.6)


class PaceTest(unittest.TestCase):
    def test_mean_pace_matches_the_plan(self):
        distances = [float(x) for x in range(0, 3000, 2)]
        times = sim.pace_profile(distances, pace=360.0, seed=2)
        self.assertAlmostEqual(times[-1], 3000 / (1000 / 360.0), delta=1.0)

    def test_splits_are_uneven_but_believable(self):
        distances = [float(x) for x in range(0, 3000, 2)]
        times = sim.pace_profile(distances, pace=360.0, seed=2)
        gaps = [(b - a) for a, b in zip(times, times[1:])]
        speeds = [2.0 / gap for gap in gaps if gap > 0]
        self.assertGreater(max(speeds) / min(speeds), 1.04)
        self.assertLess(max(speeds) / min(speeds), 1.45)

    def test_first_metres_are_slower_than_the_middle(self):
        distances = [float(x) for x in range(0, 3000, 2)]
        times = sim.pace_profile(distances, pace=360.0, seed=4)
        start = (times[10] - times[0]) / 20.0
        middle = (times[760] - times[750]) / 20.0
        self.assertGreater(start, middle)


class BuildTrackTest(unittest.TestCase):
    def test_track_is_continuous_and_closed(self):
        points = sim.build_track(SQUARE, pace=360.0, laps=1, loop=True, seed=1)
        self.assertGreater(len(points), 200)
        moments = [point[2] for point in points]
        self.assertEqual(moments, sorted(moments))
        self.assertLess((moments[-1] - moments[0]).total_seconds(), 3600)

    def test_human_false_stays_on_the_centreline(self):
        points = sim.build_track(SQUARE, pace=600.0, laps=1, loop=True, human=False)
        coordinates = [sim.to_map(latitude, longitude) for latitude, longitude, _ in points]
        # Every point sits on one of the square's four edges.
        for x, y in coordinates:
            self.assertTrue(abs(x + 100) < 1e-3 or abs(x - 100) < 1e-3 or abs(y + 100) < 1e-3 or abs(y - 100) < 1e-3)

    def test_stats_report_a_real_average(self):
        points = sim.build_track(SQUARE, pace=330.0, laps=2, loop=True, seed=8)
        stats = sim.track_stats(points)
        pace = stats["seconds"] / (stats["meters"] / 1000)
        self.assertAlmostEqual(pace, 330.0, delta=6.0)
        self.assertGreater(stats["slowest"], stats["fastest"])

    def test_start_time_is_respected(self):
        start = datetime(2026, 11, 12, 6, 30, tzinfo=timezone.utc)
        points = sim.build_track(SQUARE, pace=400.0, start=start, seed=1)
        self.assertEqual(points[0][2], start)


if __name__ == "__main__":
    unittest.main()