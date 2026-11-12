import json
import math
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent.parent
SOURCE = "https://api.openstreetmap.org/api/0.6/map?bbox=117.1698,31.7578,117.1893,31.7805"
LAT, LON = 31.769, 117.179
METERS_PER_DEGREE = 111195
X_FACTOR = METERS_PER_DEGREE * math.cos(math.radians(LAT))
BLOCKED = {"motorway", "motorway_link", "trunk", "trunk_link", "construction", "proposed", "raceway"}
MAJOR = {"primary", "primary_link", "secondary", "tertiary", "trunk", "trunk_link"}
LABELS = {
    "文典阁", "榴园餐厅", "榴园", "西门", "南门", "磬苑广场", "磬苑体育馆", "南篮球场",
    "校医院", "磬苑宾馆", "翡翠湖", "博学北楼", "博学南楼", "桔园餐厅", "笃行北楼",
}


def project(lat, lon):
    return [round((lon - LON) * X_FACTOR, 2), round((lat - LAT) * METERS_PER_DEGREE, 2)]


def prepare():
    root = ElementTree.parse(ROOT / "work" / "campus.osm").getroot()
    positions = {
        node.attrib["id"]: project(float(node.attrib["lat"]), float(node.attrib["lon"]))
        for node in root.findall("node")
    }
    node_indices, nodes, roads, areas, labels = {}, [], [], [], []

    for way in root.findall("way"):
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
        refs = [nd.attrib["ref"] for nd in way.findall("nd")]
        if len(refs) < 2 or any(ref not in positions for ref in refs):
            continue
        points = [positions[ref] for ref in refs]
        name = tags.get("name:zh", tags.get("name", ""))
        highway = tags.get("highway")
        if highway and tags.get("area") != "yes":
            ids = []
            for ref in refs:
                if ref not in node_indices:
                    node_indices[ref] = len(nodes)
                    nodes.append(positions[ref])
                ids.append(node_indices[ref])
            foot = tags.get("foot")
            allowed = highway not in BLOCKED and foot not in {"no", "private"} and (
                tags.get("access") not in {"no", "private"} or foot in {"yes", "designated", "permissive"}
            )
            style = "major" if highway in MAJOR else "path" if highway in {"footway", "pedestrian", "steps", "path"} else "road"
            roads.append([style, allowed, ids])
        if refs[0] == refs[-1] and len(refs) >= 4:
            if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
                areas.append(["water", points])
            elif tags.get("leisure") in {"pitch", "track", "stadium"}:
                areas.append(["sport", points])
            elif tags.get("leisure") == "park" or tags.get("landuse") in {"grass", "forest", "recreation_ground"}:
                areas.append(["green", points])
            elif "building" in tags:
                areas.append(["building", points])
        if name in LABELS and not any(label[0] == name for label in labels):
            core = points[:-1] if refs[0] == refs[-1] else points
            labels.append([name, [round(sum(values) / len(values), 2) for values in zip(*core)]])

    data = {
        "source": SOURCE,
        "attribution": "© OpenStreetMap contributors",
        "license": "https://opendatacommons.org/licenses/odbl/1-0/",
        "bounds": [*project(31.7578, 117.1698), *project(31.7805, 117.1893)],
        "nodes": nodes, "roads": roads, "areas": areas, "labels": labels,
    }
    output = ROOT / "outputs" / "run-planner"
    output.mkdir(exist_ok=True)
    (output / "campus_map.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(nodes)} nodes, {len(roads)} roads, {len(areas)} areas; labels: {[label[0] for label in labels]}")


if __name__ == "__main__":
    prepare()
