"""Regenerate campus.json's label table from every named OSM feature inside campus.

步道乐跑 picks its checkpoints from a wide pool (人文楼东侧, 行政楼, 艺术楼, 理工C楼,
蕙园3栋 …).  The hand-picked 15 labels in campus.json cover only a fraction of them,
so anything else came back as "read but unmapped".

This script:
  * parses work/campus.osm, keeps named *area* features (buildings, dorms, sports,
    canteens, gates …) and drops roads / railways / huge land parcels;
  * keeps only features inside the campus ring (with a small margin);
  * emits the centroid plus 东/西/南/北侧 (and 东门/西门/南门/北门) variants for
    anything big enough to have sides;
  * snaps each candidate to the nearest walkable road so the runner can actually
    reach it, dropping points that are too far from any road;
  * merges with the existing labels (existing names win) and rewrites campus.json.
"""

from __future__ import annotations

import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OSM = ROOT / "work" / "campus.osm"
TARGET = ROOT / "outputs" / "real-run-planner" / "campus.json"

LAT, LON = 31.769, 117.179
MPD = 111195.0
XF = MPD * math.cos(math.radians(LAT))

# Feature kinds worth turning into a checkpoint.  Anything else (roads, rails,
# waterways, land parcels) is skipped.
AREA_TYPES = {
    "university", "college", "school", "kindergarten", "dormitory", "house",
    "yes", "hospital", "pitch", "cafe", "hotel", "public_bath", "pavilion",
    "sports_centre", "stadium", "canteen", "library", "office", "retail",
}
SKIP_NAMES = {
    "安大磬苑校区", "中国（安徽）自由贸易试验区合肥片区", "世茂翡翠首府", "东湖高新合肥创新中心",
    "禹洲·翡翠湖郡", "绿城翡翠湖玫瑰园(南区)", "翡翠云璟", "高校三创园",
    "翡翠湖迎宾馆", "九龙路", "集贤路", "集贤路辅路", "容成路", "姜家湖路",
    "城东湖路", "紫云路", "翡翠路", "繁华大道", "幸福大街", "独秀大道", "环翠路",
    "至坚路", "至诚大道", "汤口路", "九龙", "九龙园", "京港高速线", "合肥轨道交通3号线",
    "金源热电厂专用线", "肥西-众兴", "古埂河", "鹅池",
}
MAX_SPAN = 420.0          # metres; anything longer is a road or a land parcel
SIDE_MIN_SPAN = 25.0      # only emit 东侧/西侧/… for buildings this wide
SNAP_LIMIT = 70.0         # a checkpoint farther than this from any road is useless

DIRECTIONS = ("东", "西", "南", "北")


def project(lat, lon):
    return ((lon - LON) * XF, (lat - LAT) * MPD)


def ring_contains(points, p, boundary=True):
    """Ray casting, same convention as pedestrian_routes.Ring.contains."""
    x, y = p
    inside = False
    for a, b in zip(points, points[1:]):
        if (a[1] > y) != (b[1] > y) and x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
            inside = not inside
    return inside


def load_features():
    tree = ET.parse(OSM)
    root = tree.getroot()
    nodes = {}
    for node in root.findall("node"):
        nodes[node.get("id")] = (float(node.get("lat")), float(node.get("lon")))

    features = []
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        name = (tags.get("name") or "").strip()
        if not name or name in SKIP_NAMES:
            continue
        kind = tags.get("building") or tags.get("amenity") or tags.get("leisure") or ""
        if kind not in AREA_TYPES:
            continue
        pts = []
        for nd in way.findall("nd"):
            ref = nd.get("ref")
            if ref in nodes:
                lat, lon = nodes[ref]
                pts.append(project(lat, lon))
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys))
        if span > MAX_SPAN:
            continue
        features.append({"name": name, "points": pts, "span": span, "kind": kind})
    return features


def candidates(feature):
    """Centroid plus direction variants, as local-metre points."""
    pts = feature["points"]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    out = [(feature["name"], (cx, cy))]
    if feature["span"] >= SIDE_MIN_SPAN:
        east, west = max(xs), min(xs)
        north, south = max(ys), min(ys)
        out += [
            (f"{feature['name']}东侧", (east, cy)),
            (f"{feature['name']}西侧", (west, cy)),
            (f"{feature['name']}南侧", (cx, south)),
            (f"{feature['name']}北侧", (cx, north)),
            (f"{feature['name']}东门", (east, cy)),
            (f"{feature['name']}西门", (west, cy)),
            (f"{feature['name']}南门", (cx, south)),
            (f"{feature['name']}北门", (cx, north)),
        ]
    return out


def nearest_clear(network, rings, point, limit):
    """Nearest walkable edge position that is not inside a building or the water."""
    best = None
    for edge, segment in network.segments.items():
        if segment.reason or edge in network.closed:
            continue
        a, b = network.nodes[edge[0]], network.nodes[edge[1]]
        ax, ay = a
        dx, dy = b[0] - ax, b[1] - ay
        d2 = dx * dx + dy * dy
        t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / d2))
        snapped = (ax + dx * t, ay + dy * t)
        offset = math.dist(point, snapped)
        if offset > limit:
            continue
        if any(ring_contains(ring, snapped) for ring in rings):
            continue
        if best is None or offset < best[0]:
            best = (offset, snapped)
    return best


def main():
    import sys

    sys.path.insert(0, str(ROOT / "outputs" / "real-run-planner"))
    from pedestrian_routes import Network  # noqa: E402

    data = json.loads(TARGET.read_text(encoding="utf-8"))
    network = Network(data, campus_only=True)
    campus = data["campus"]
    blockers = [outer for kind, outer, holes in data["areas"] if kind in {"building", "water"}]

    features = load_features()
    print(f"named area features: {len(features)}")

    labels: dict[str, tuple[float, float]] = {}
    skipped_outside = skipped_far = 0
    for feature in features:
        for name, point in candidates(feature):
            if not any(ring_contains(ring, point) for ring in campus):
                skipped_outside += 1
                continue
            found = nearest_clear(network, blockers, point, SNAP_LIMIT)
            if found is None:
                skipped_far += 1
                continue
            labels.setdefault(name, found[1])

    existing = {name: tuple(point) for name, point in data["labels"]}
    added = {name: pt for name, pt in labels.items() if name not in existing}
    merged = dict(existing)
    merged.update(added)

    print(f"existing labels: {len(existing)}")
    print(f"generated (snapped): {len(labels)}  added: {len(added)}")
    print(f"skipped outside campus: {skipped_outside}, too far from road: {skipped_far}")

    backup = TARGET.with_suffix(".json.bak")
    shutil.copy2(TARGET, backup)
    data["labels"] = sorted(
        ([name, [round(x, 2), round(y, 2)]] for name, (x, y) in merged.items()),
        key=lambda item: item[0],
    )
    TARGET.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes), backup at {backup.name}")

    # Show what a few interesting names resolved to.
    for probe in ("人文楼", "人文楼东侧", "行政楼", "艺术楼", "理工C楼", "蕙园3栋", "文典阁西门"):
        point = merged.get(probe)
        print(f"  {probe}: {'missing' if point is None else f'({point[0]:.1f}, {point[1]:.1f})'}")


if __name__ == "__main__":
    main()