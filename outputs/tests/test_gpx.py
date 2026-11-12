import tempfile
import unittest
from pathlib import Path
from xml.etree.ElementTree import ParseError

from check_gpx import check_gpx


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_route.gpx"


class CheckGpxTest(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.input = Path(temp_dir.name) / "input.gpx"
        self.demo = DEMO.read_text(encoding="utf-8")

    def check_text(self, gpx):
        self.input.write_text(gpx, encoding="utf-8")
        return check_gpx(self.input)

    def test_demo(self):
        self.assertEqual(check_gpx(DEMO), (4, 24))

    def test_empty_track(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.check_text("<gpx><trk><trkseg/></trk></gpx>")

    def test_single_point(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.check_text('<gpx><trk><trkseg><trkpt lat="0" lon="0"/></trkseg></trk></gpx>')

    def test_route_points_only(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.check_text('<gpx><rte><rtept lat="0" lon="0"/><rtept lat="1" lon="1"/></rte></gpx>')

    def test_unordered_or_duplicate_timestamps(self):
        for timestamp in ("2025-12-31T23:59:59Z", "2026-01-01T01:00:00+01:00"):
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(ValueError, "later timestamp"):
                self.check_text(self.demo.replace("2026-01-01T00:00:08Z", timestamp))

    def test_valid_utc_offset(self):
        self.assertEqual(self.check_text(self.demo.replace("00:00:08Z", "01:00:08+01:00")), (4, 24))

    def test_bad_or_missing_timestamp(self):
        for time in ("", "<time>bad date</time>", "<time>2026-01-01T00:00:08</time>"):
            with self.subTest(time=time), self.assertRaisesRegex(ValueError, "valid <time>"):
                self.check_text(self.demo.replace("<time>2026-01-01T00:00:08Z</time>", time))

    def test_out_of_range_or_nonfinite_coordinates(self):
        for lat, lon in (("91", "0"), ("0", "-181"), ("0", "180"), ("NaN", "0"), ("0", "inf")):
            with self.subTest(lat=lat, lon=lon), self.assertRaisesRegex(ValueError, "outside the GPX range"):
                self.check_text(self.demo.replace('lat="37.77490" lon="-122.41940"', f'lat="{lat}" lon="{lon}"'))

    def test_missing_coordinate(self):
        with self.assertRaisesRegex(ValueError, "valid lat/lon"):
            self.check_text(self.demo.replace('lat="37.77490" ', ""))

    def test_malformed_xml(self):
        with self.assertRaises(ParseError):
            self.check_text("<gpx>")


if __name__ == "__main__":
    unittest.main()
