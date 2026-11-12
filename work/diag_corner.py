import json, math, sys
from pathlib import Path
ROOT = Path(".").resolve()
OUT = ROOT.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))
import location_sim as sim
from road_network import RoadNetwork
DATA = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
net = RoadNetwork(DATA)
labels = {n: p for n, p in DATA["labels"]}
pos = [net.nearest(labels[n]) for n in ["笃行北楼", "文典阁", "磬苑广场"]]
pos.append(pos[0])
total, route, _ = net.through(pos)
body = sim.round_corners(route, radius=9.0, step=1.0)
print("route", len(route), "body", len(body), "closed", math.dist(body[0], body[-1]))
def angles(pts):
    out = []
    for i in range(1, len(pts)-1):
        v1 = (pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1])
        v2 = (pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < 1e-6 or l2 < 1e-6:
            out.append((i, None, l1, l2)); continue
        c = max(-1, min(1, (v1[0]*v2[0]+v1[1]*v2[1])/(l1*l2)))
        out.append((i, math.degrees(math.acos(c)), l1, l2))
    return out
a = angles(body)
worst = sorted(a, key=lambda r: -(r[1] or 0))[:6]
for i, ang, l1, l2 in worst:
    print(f"  body[{i}] angle {ang:.0f} seg {l1:.2f}/{l2:.2f} at {tuple(round(v,1) for v in body[i])}")
track = sim.build_track(route, pace=360, laps=1, loop=True, seed=7)
tr = [sim.to_map(lat, lon) for lat, lon, _ in track]
a2 = angles(tr)
print("track worst:", [(i, round(ang or 0), round(l1,2), round(l2,2)) for i, ang, l1, l2 in sorted(a2, key=lambda r: -(r[1] or 0))[:6]])
print("track pts", len(tr), "min seg", min(math.dist(p, q) for p, q in zip(tr, tr[1:])))
