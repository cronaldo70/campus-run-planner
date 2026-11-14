"""Test snap_clear: verify water points get snapped back to road."""
import sys, json

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import real_run_sim as bridge
import location_sim as sim
from pedestrian_routes import Network

d = json.load(open("outputs/real-run-planner/campus.json", encoding="utf-8"))
site = bridge.Site(d)
bridge.set_site(site)
net = Network(d, campus_only=True)

# Round-trip
lat, lon = 31.769, 117.179
x, y = sim.to_map(lat, lon)
lat2, lon2 = sim.to_wgs84((x, y))
print(f"round-trip: err={abs(lat - lat2) + abs(lon - lon2):.8f}")

# --- Test water detection on a few samples ---
for pt in [(500, -300), (600, 100), (400, 100), (1000, 800)]:
    inside = site.inside(pt)
    kind = site.blocked(pt)
    rd = site.road(pt)
    print(f"  {pt}: inside={inside}, blocked={kind!r}, road_dist={rd:.1f}m")

# --- Build a realistic route and check ---
print("\n--- Manual route ---")
route = [
    (-220.0, -28.0),
    (-187.0, -29.0),
    (-160.0, 50.0),
    (30.0, 200.0),
    (150.0, 400.0),
    (300.0, 600.0),
]
pts, stats = bridge.build(route, pace=300)
before = sum(1 for p in pts if site.blocked(sim.to_map(p[0], p[1])))
print(f"BEFORE snap: {before} water pts")
print(f"snapped: {stats.get('water_snapped', 0)}")
after = sum(1 for p in pts if site.blocked(sim.to_map(p[0], p[1])))
print(f"AFTER  snap: {after} water pts")
print(f"meters: {stats['meters']:.1f}, points: {len(pts)}")

# --- Planned route from real checkpoints ---
print("\n--- Real planned route ---")
labels = d["labels"]
start_pt = (-187.7, -29.0)
start = net.nearest(start_pt)

# Find two checkpoints with known coords
cp_coords = []
cp_names = []
for name in ["文典阁西门", "体育馆大门"]:
    if name in labels:
        cp_coords.append(tuple(labels[name]))
        cp_names.append(name)
print(f"checkpoints: {cp_names} -> {cp_coords}")

try:
    path, info = net.plan(start, cp_coords, via=[], finish=None, minimum=2500)
    print(
        f"plan: {info['metres']:.0f}m, path_pts={len(path)}, outside={info.get('outside', 0)}m"
    )
    pts2, stats2 = bridge.build(path, pace=300, minimum=2500)
    before2 = sum(1 for p in pts2 if site.blocked(sim.to_map(p[0], p[1])))
    print(f"BEFORE snap: {before2} water pts")
    print(f"snapped: {stats2.get('water_snapped', 0)}")
    after2 = sum(1 for p in pts2 if site.blocked(sim.to_map(p[0], p[1])))
    print(f"AFTER  snap: {after2} water pts")
    print(f"meters: {stats2['meters']:.1f}, shortfall: {stats2.get('shortfall', 0):.1f}")

    # Also check: are any raw graph edges crossing water? (should be 0)
    water_blocked = sum(
        1 for seg in net.segments.values() if seg.reason == "水域"
    )
    print(f"raw graph edges blocked by water: {water_blocked}")

    # Show which edges are blocked and near the lake
    print("\nSample blocked edges:")
    count = 0
    for edge, seg in net.segments.items():
        if seg.reason and count < 5:
            a, b = net.nodes[edge[0]], net.nodes[edge[1]]
            print(f"  {edge}: {seg.reason} ({a[0]:.0f},{a[1]:.0f})-({b[0]:.0f},{b[1]:.0f})")
            count += 1
except Exception as e:
    import traceback

    traceback.print_exc()
    print(f"plan failed: {e}")

print("\nOK" if after == 0 and after2 == 0 else "\nFAIL: still water points")