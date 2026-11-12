import json, math, random, sys
from pathlib import Path
OUT = Path(".").resolve().parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))
from road_network import RoadNetwork
DATA = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
plain = RoadNetwork(DATA, avoid=())
smart = RoadNetwork(DATA)
rng = random.Random(11)
nodes = smart.nodes
def probe(net):
    bad = 0; lengths = []
    for _ in range(40):
        a, b = rng.sample(nodes, 2)
        try:
            length, route = net.shortest(net.nearest(a), net.nearest(b))
        except ValueError:
            continue
        lengths.append(length)
        if net.violations(route):
            bad += 1
    return bad, sum(lengths)/len(lengths)
for name, net in (("plain", plain), ("obstacle-aware", smart)):
    bad, mean = probe(net)
    print(f"{name}: {bad}/40 routes cut a building or lake, mean {mean:.0f} m")
print(smart.coverage())
