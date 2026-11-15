"""Dump every named feature in campus.osm with its local-metre centroid, so we can
add missing 步道乐跑 checkpoint names (e.g. 人文楼东侧) to campus.json."""
import math
import xml.etree.ElementTree as ET

LAT, LON = 31.769, 117.179
MPD = 111195.0
XF = MPD * math.cos(math.radians(LAT))


def project(lat, lon):
    return ((lon - LON) * XF, (lat - LAT) * MPD)


tree = ET.parse("work/campus.osm")
root = tree.getroot()

# collect node coords
nodes = {}
for node in root.findall("node"):
    tags = {t.get("k"): t.get("v") for t in node.findall("tag")}
    nodes[node.get("id")] = (float(node.get("lat")), float(node.get("lon")), tags)

named_nodes = [(nid, v) for nid, v in nodes.items() if v[2].get("name")]

rows = []

# named nodes
for nid, (lat, lon, tags) in named_nodes:
    x, y = project(lat, lon)
    rows.append(("node", tags["name"], x, y, 0.0, tags.get("amenity") or tags.get("building") or ""))

# named ways
for way in root.findall("way"):
    tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
    name = tags.get("name")
    if not name:
        continue
    pts = []
    for nd in way.findall("nd"):
        ref = nd.get("ref")
        if ref in nodes:
            lat, lon, _ = nodes[ref]
            pts.append(project(lat, lon))
    if not pts:
        continue
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    rows.append(("way", name, cx, cy, span, tags.get("building") or tags.get("leisure") or tags.get("amenity") or ""))

rows.sort(key=lambda r: r[1])

with open("work/osm_names.txt", "w", encoding="utf-8") as f:
    f.write(f"named features: {len(rows)}\n\n")
    for kind, name, x, y, span, typ in rows:
        f.write(f"{kind:4s} {name:20s} ({x:8.1f},{y:8.1f}) span={span:6.1f} {typ}\n")

print(f"named features: {len(rows)}")

# highlight likely checkpoints
hits = [r for r in rows if any(k in r[1] for k in ("人文", "图书", "行政", "实验", "活动中心", "教学", "食堂", "体育", "剧场", "礼堂"))]
print(f"\nlikely checkpoint features: {len(hits)}")
for kind, name, x, y, span, typ in hits:
    print(f"  {name} ({x:.1f},{y:.1f}) span={span:.1f} {typ}")