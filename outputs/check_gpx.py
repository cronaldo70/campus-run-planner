"""Check the input for a timestamp-paced pymobiledevice3 GPX replay."""

import argparse
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from pymobiledevice3.services.dvt.instruments.location_simulation_base import iter_gpx_track_points


def check_gpx(path: Path) -> tuple[int, float]:
    points = list(iter_gpx_track_points(str(path)))
    if len(points) < 2:
        raise ValueError("The GPX file must have at least two <trkpt> points under <trk>/<trkseg>.")

    previous_time = None
    for index, point in enumerate(points, start=1):
        if not (-90 <= point.latitude <= 90 and -180 <= point.longitude < 180):
            raise ValueError(f"Track point {index} has latitude or longitude outside the GPX range.")
        if point.time is None or point.time.tzinfo is None:
            raise ValueError(f"Track point {index} needs a valid <time> with Z or a UTC offset.")
        if previous_time is not None and point.time <= previous_time:
            raise ValueError(f"Track point {index} must have a later timestamp than the previous point.")
        previous_time = point.time

    return len(points), (points[-1].time - points[0].time).total_seconds()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gpx", type=Path, help="GPX file to check offline")
    args = parser.parse_args()
    try:
        count, seconds = check_gpx(args.gpx)
    except (OSError, ParseError, DefusedXmlException, ValueError) as error:
        parser.exit(1, f"GPX check failed: {error}\n")
    print(f"GPX check passed: {count} track points, {seconds:g} seconds between first and last points.")


if __name__ == "__main__":
    main()
