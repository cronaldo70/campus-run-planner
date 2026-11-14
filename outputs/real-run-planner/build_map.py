"""Build the offline pedestrian map from an OpenStreetMap .osm extract."""

import argparse
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET


SOURCE = "https://api.openstreetmap.org/api/0.6/map?bbox=117.1698,31.7578,117.1893,31.7805"
WALKWAYS = {"footway", "path", "pedestrian", "steps", "living_street", "residential",
            "service", "unclassified", "track", "tertiary", "cycleway"}
OPEN = {"yes", "designated", "permissive"}
CLOSED = {"no", "private", "customers", "delivery", "permit", "use_sidepath"}


def tags(element):
    return {item.attrib["k"]: item.attrib["v"] for item in element.findall("tag")}


def project(lat, lon):
    return [round((lon - 117.179) * 111195 * math.cos(math.radians(31.769)), 2),
            round((lat - 31.769) * 111195, 2)]


def walkable(info):
    highway = info.get("highway")
    foot = info.get("foot")
    return (info.get("area") != "yes" and info.get("indoor") != "yes" and foot not in CLOSED
            and (highway in WALKWAYS or highway == "secondary" and foot in OPEN)
            and (foot in OPEN or info.get("access") not in CLOSED))


def area_kind(info):
    if info.get("natural") == "water" or info.get("waterway") == "riverbank":
        return "water"
    if info.get("building") not in (None, "no", "roof"):
        return "building"
    if info.get("leisure") in {"pitch", "track", "stadium"}:
        return "sport"
    if info.get("leisure") == "park" or info.get("landuse") in {"grass", "forest", "recreation_ground"}:
        return "green"
    return None


def rings(parts):
    pending = [list(part) for part in parts]
    result = []
    while pending:
        chain = pending.pop()
        while chain[0] != chain[-1]:
            for index, part in enumerate(pending):
                if part[0] == chain[-1] or part[-1] == chain[-1]:
                    chain.extend((part if part[0] == chain[-1] else part[::-1])[1:])
                    pending.pop(index)
                    break
            else:
                break
        if len(chain) >= 4 and chain[0] == chain[-1]:
            result.append(chain)
    return result


def within(point, ring):
    x, y = point
    return sum((a[1] > y) != (b[1] > y) and x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
               for a, b in zip(ring, ring[1:])) % 2 == 1


def build(source):
    root = ET.parse(source).getroot()
    nodes = {item.attrib["id"]: item for item in root.findall("node")}
    coords = {key: project(float(item.attrib["lat"]), float(item.attrib["lon"])) for key, item in nodes.items()}
    ways = {item.attrib["id"]: ([node.attrib["ref"] for node in item.findall("nd")], tags(item))
            for item in root.findall("way")}
    roads, walls, waterways, areas, labels, campus = [], [], [], [], [], []
    closed_nodes = []
    gates = []
    for key, node in nodes.items():
        info = tags(node)
        barrier = info.get("barrier")
        if info.get("foot") in CLOSED or (info.get("foot") not in OPEN and
                (info.get("access") in CLOSED or info.get("locked") == "yes"
                 or barrier in {"wall", "fence", "hedge", "block"})):
            closed_nodes.append(key)
        elif barrier in {"gate", "lift_gate", "kissing_gate", "entrance"} or info.get("entrance") == "yes":
            gates.append(coords[key])

    relation_members = set()
    for relation in root.findall("relation"):
        info = tags(relation)
        is_campus = info.get("amenity") == "university" and info.get("name") == "安徽大学(磬苑校区)"
        kind = area_kind(info)
        if not (is_campus or kind in {"building", "water"}):
            continue
        by_role = {"outer": [], "inner": []}
        members = []
        for member in relation.findall("member"):
            ref, role = member.get("ref"), member.get("role") or "outer"
            if member.get("type") == "way" and ref in ways and role in by_role:
                refs, _ = ways[ref]
                if len(refs) >= 2 and all(key in coords for key in refs):
                    by_role[role].append(refs)
                    members.append(ref)
        outer = [[coords[key] for key in ring] for ring in rings(by_role["outer"])]
        inner = [[coords[key] for key in ring] for ring in rings(by_role["inner"])]
        if is_campus:
            campus.extend(outer)
        elif outer:
            relation_members.update(members)
            for ring in outer:
                areas.append([kind, ring, [hole for hole in inner if within(hole[0], ring)]])

    for ref, (ids, info) in ways.items():
        if len(ids) < 2 or any(key not in coords for key in ids):
            continue
        points = [coords[key] for key in ids]
        if info.get("highway") and info.get("area") != "yes":
            bridge = info.get("bridge") in {"yes", "viaduct", "boardwalk", "movable", "cantilever", "covered", "trestle"}
            style = "path" if info["highway"] in {"footway", "path", "pedestrian", "steps"} else "road"
            roads.append([ids, style, walkable(info), bridge])
        if info.get("barrier") in {"fence", "wall", "hedge", "retaining_wall"}:
            walls.append(points)
        if info.get("waterway") in {"river", "stream", "canal"} and info.get("tunnel") != "culvert":
            waterways.append(points)
        kind = area_kind(info)
        if kind and ref not in relation_members and len(ids) >= 4 and ids[0] == ids[-1]:
            areas.append([kind, points, []])
        name = info.get("name:zh", info.get("name", ""))
        if name in {"文典阁", "笃行北楼", "榴园餐厅", "南篮球场", "磬苑体育馆", "蕙园1栋", "蕙园5栋",
                    "桔园餐厅", "博学北楼", "博学南楼", "磬苑广场", "西门"}:
            labels.append([name, [sum(values) / len(values) for values in zip(*points)]])

    # OSM marks the buildings but does not give the event's entrance pins.
    by_name = dict(labels)
    if "蕙园1栋" in by_name and "蕙园5栋" in by_name:
        labels.append(["蕙园", [(a + b) / 2 for a, b in zip(by_name["蕙园1栋"], by_name["蕙园5栋"])]])
    for ids, info in ways.values():
        if info.get("name") == "文典阁" and all(key in coords for key in ids):
            west = min(coords[key][0] for key in ids)
            low, high = min(coords[key][1] for key in ids), max(coords[key][1] for key in ids)
            labels.append(["文典阁西门", [west - 8, (low + high) / 2]])
        if info.get("name") == "南篮球场" and all(key in coords for key in ids):
            south = min(coords[key][1] for key in ids)
            low, high = min(coords[key][0] for key in ids), max(coords[key][0] for key in ids)
            labels.append(["篮球场南门", [(low + high) / 2, south - 5]])

    if not campus:
        raise ValueError("OSM extract does not contain a closed boundary for the Qingyuan campus.")
    bounds = root.find("bounds").attrib
    used = {key for ids, *_ in roads for key in ids}
    return {"source": SOURCE, "license": "https://opendatacommons.org/licenses/odbl/1-0/",
            "bounds": [*project(float(bounds["minlat"]), float(bounds["minlon"])),
                       *project(float(bounds["maxlat"]), float(bounds["maxlon"]))],
            "nodes": {key: coords[key] for key in sorted(used)}, "roads": roads, "areas": areas,
            "campus": campus, "walls": walls, "waterways": waterways, "gates": gates,
            "closed_nodes": closed_nodes, "labels": labels}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("osm", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(args.osm), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
