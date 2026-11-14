"""Obstacle-aware campus routes for walking and running in person."""

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import permutations
from math import dist, inf


EPS = 1e-8
# 步道乐跑 用的是高德底图：校内人行小径（OSM 的 path）它不画，贴着这种小径跑出来的轨迹
# 在手机上看起来就是在草地/绿化带上直线斜穿。给 path 加权，让规划优先走大路，只有绕路
# 超过 3 倍才会用小径；吸附标点时小径也要比大路近一倍才优先。
PATH_PENALTY = 6.0
PATH_NEAREST = 2.0


def at(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def projection(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    return max(0, min(1, t))


def intersections(a, b, c, d):
    if (max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0])
            or max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1])):
        return []
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    x, y = c[0] - a[0], c[1] - a[1]
    cross = rx * sy - ry * sx
    if abs(cross) <= EPS:
        if abs(x * ry - y * rx) > EPS:
            return []
        length2 = rx * rx + ry * ry
        t = (x * rx + y * ry) / length2
        u = t + (sx * rx + sy * ry) / length2
        low, high = max(0, min(t, u)), min(1, max(t, u))
        return [low, high] if low <= high else []
    t = (x * sy - y * sx) / cross
    u = (x * ry - y * rx) / cross
    return [max(0, min(1, t))] if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS else []


class Ring:
    def __init__(self, points):
        self.edges = [(a, b) for a, b in zip(points, points[1:]) if a != b]
        x, y = zip(*points)
        self.box = min(x), min(y), max(x), max(y)

    def overlaps(self, a, b):
        x0, y0, x1, y1 = self.box
        return max(a[0], b[0]) >= x0 and min(a[0], b[0]) <= x1 and max(a[1], b[1]) >= y0 and min(a[1], b[1]) <= y1

    def contains(self, p, boundary=False):
        if not self.overlaps(p, p):
            return False
        x, y = p
        inside = False
        for a, b in self.edges:
            if dist(p, at(a, b, projection(p, a, b))) <= EPS:
                return boundary
            if (a[1] > y) != (b[1] > y) and x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
                inside = not inside
        return inside

    def cuts(self, a, b):
        if self.overlaps(a, b):
            return [t for c, d in self.edges for t in intersections(a, b, c, d)]
        return []


def pieces(a, b, rings):
    cuts = sorted({0, 1, *(t for ring in rings for t in ring.cuts(a, b))})
    return [at(a, b, (t + u) / 2) for t, u in zip(cuts, cuts[1:]) if u - t > EPS]


@dataclass(frozen=True)
class Segment:
    style: str
    bridge: bool
    reason: str


@dataclass(frozen=True)
class Position:
    edge: tuple[str, str]
    point: tuple[float, float]
    offset: float


class Network:
    def __init__(self, data, *, campus_only=True):
        self.nodes = {key: tuple(point) for key, point in data["nodes"].items()}
        self.segments = {}
        self.neighbors = {key: [] for key in self.nodes}
        self.weights = {}
        self.closed = set()
        campus = [Ring(ring) for ring in data["campus"]]
        buildings, water = [], []
        for kind, outer, holes in data["areas"]:
            if kind in {"building", "water"}:
                (buildings if kind == "building" else water).append((Ring(outer), [Ring(h) for h in holes]))
        walls = [(c, d) for line in data["walls"] for c, d in zip(line, line[1:]) if c != d]
        waterways = [(c, d) for line in data.get("waterways", []) for c, d in zip(line, line[1:]) if c != d]
        gates = data["gates"]
        closed_nodes = set(data["closed_nodes"])

        def intersects_area(a, b, areas):
            return any(outer.overlaps(a, b) and any(
                outer.contains(p) and not any(hole.contains(p, boundary=True) for hole in holes)
                for p in pieces(a, b, [outer, *holes])
            ) for outer, holes in areas)

        for ids, style, allowed, bridge in data["roads"]:
            for u, v in zip(ids, ids[1:]):
                a, b = self.nodes[u], self.nodes[v]
                if a == b:
                    continue
                edge = tuple(sorted((u, v)))
                reason = ""
                if not allowed or u in closed_nodes or v in closed_nodes:
                    reason = "行人限制"
                elif campus_only and any(not any(ring.contains(p, boundary=True) for ring in campus)
                                         for p in pieces(a, b, campus)):
                    reason = "校区边界外"
                elif intersects_area(a, b, buildings):
                    reason = "建筑"
                elif not bridge and (intersects_area(a, b, water)
                                     or any(intersections(a, b, c, d) for c, d in waterways)):
                    reason = "水域"
                elif any(not any(dist(at(a, b, t), gate) <= 1 for gate in gates)
                         for c, d in walls for t in intersections(a, b, c, d)):
                    reason = "围栏或墙"
                if edge not in self.segments or (self.segments[edge].reason and not reason):
                    self.segments[edge] = Segment(style, bridge, reason)

        for (u, v), segment in self.segments.items():
            if not segment.reason:
                length = dist(self.nodes[u], self.nodes[v])
                self.neighbors[u].append((v, length))
                self.neighbors[v].append((u, length))
                self.weights[(u, v)] = 1.0 if segment.style == "road" else PATH_PENALTY

    def nearest(self, point, *, for_closure=False):
        point = tuple(point)
        best = None
        for edge, segment in self.segments.items():
            if not for_closure and (segment.reason or edge in self.closed):
                continue
            a, b = (self.nodes[key] for key in edge)
            snap = at(a, b, projection(point, a, b))
            offset = dist(point, snap)
            # A footpath must be twice as close for the marker to land on it, so the
            # route starts on a road the phone's basemap actually draws.
            rank = offset * (1.0 if segment.style == "road" else PATH_NEAREST)
            if best is None or rank < best[0]:
                best = (rank, Position(edge, snap, offset))
        return best[1] if best else None

    def route(self, start, end):
        for position in (start, end):
            if position.edge in self.closed or self.segments[position.edge].reason:
                raise ValueError("所选标点所在路段不可通行。请重新选择标点。")
        best = dist(start.point, end.point) if start.edge == end.edge else inf
        goals = {key: dist(end.point, self.nodes[key]) for key in end.edge}
        costs = {key: dist(start.point, self.nodes[key]) for key in start.edge}
        queue = sorted((cost, key) for key, cost in costs.items())
        parents = {}
        finish = None
        while queue:
            cost, node = heappop(queue)
            if cost >= best:
                break
            if cost != costs[node]:
                continue
            if node in goals and cost + goals[node] < best:
                best, finish = cost + goals[node], node
            for neighbor, length in self.neighbors[node]:
                edge = tuple(sorted((node, neighbor)))
                if edge in self.closed:
                    continue
                candidate = cost + length * self.weights.get(edge, 1.0)
                if candidate < costs.get(neighbor, inf):
                    costs[neighbor] = candidate
                    parents[neighbor] = node
                    heappush(queue, (candidate, neighbor))
        if best == inf:
            raise ValueError("标点之间没有连通的可走路段。请核对入口或调整途经点。")
        path = [end.point]
        edges = {start.edge} if finish is None else set()
        if finish is not None and end.point != self.nodes[finish]:
            edges.add(end.edge)
        first = finish
        while finish is not None:
            path.append(self.nodes[finish])
            first = finish
            parent = parents.get(finish)
            if parent is not None:
                edges.add(tuple(sorted((parent, finish))))
            finish = parent
        if first is not None and start.point != self.nodes[first]:
            edges.add(start.edge)
        path.append(start.point)
        # best is a weighted cost (footpaths cost 3x); report the real ground distance.
        metres = sum(dist(a, b) for a, b in zip(path, path[1:]))
        return metres, path[::-1], edges

    def plan(self, start, checkpoints, via, finish, *, minimum=None):
        """Visit checkpoints in either order and use existing roads for an optional longer finish."""
        result = []
        for order in permutations(range(len(checkpoints))):
            points = [start, *(checkpoints[i] for i in order), *via]
            if finish is not None:
                points.append(finish)
            legs = [self.route(a, b) for a, b in zip(points, points[1:])]
            result.append((sum(length for length, _, _ in legs), legs, order, points[-1]))
        meters, legs, order, last = min(result, key=lambda item: item[0])
        path = [start.point, *(p for _, leg, _ in legs for p in leg[1:])]
        if finish is None and minimum is not None and meters < minimum:
            used = set().union(*(edges for _, _, edges in legs))
            extra = self.extension(last, minimum - meters, used)
            meters += sum(dist(a, b) for a, b in zip(extra, extra[1:]))
            path.extend(extra[1:])
        return meters, path, order

    def _walk(self, sources, goals, *, penalty_edges=(), penalty=1.0):
        """Dijkstra from many starting nodes to any goal node: (cost, node path).

        ``penalty_edges`` keeps its edges usable but expensive, so the search can
        always find a way out of a dead end instead of failing outright.
        """
        heavy = set(penalty_edges)
        costs = dict(sources)
        parents = {}
        queue = sorted((cost, node) for node, cost in costs.items())
        best, finish = inf, None
        while queue:
            cost, node = heappop(queue)
            if cost != costs[node]:
                continue
            if node in goals and cost < best:
                best, finish = cost, node
            for neighbor, length in self.neighbors[node]:
                edge = tuple(sorted((node, neighbor)))
                if edge in self.closed:
                    continue
                candidate = cost + length * self.weights.get(edge, 1.0) * (penalty if edge in heavy else 1.0)
                if candidate < costs.get(neighbor, inf):
                    costs[neighbor] = candidate
                    parents[neighbor] = node
                    heappush(queue, (candidate, neighbor))
        if finish is None:
            return inf, []
        path = [finish]
        while path[-1] in parents:
            path.append(parents[path[-1]])
        return best, path[::-1]

    def extension(self, start, target, used):
        """Tail of about ``target`` metres that comes home by another road.

        A plain out-and-back makes the runner U-turn mid-path, which is the most
        obvious robot tell on a recorded track, so the tail is built as a loop:
        out along fresh edges, back along different ones. Only a dead end falls
        back to turning around, and that corner gets rounded by the track builder.
        """
        if target <= 1.0:
            return [start.point]
        home = set(start.edge)
        approach = {node: dist(start.point, self.nodes[node]) for node in start.edge}
        candidates = sorted((abs(dist(start.point, point) - target / 2), key)
                            for key, point in self.nodes.items() if key not in home)
        best = None
        for _, node in candidates[:48]:
            _, out_path = self._walk(approach, {node}, penalty_edges=used, penalty=3.0)
            if len(out_path) < 2:
                continue
            out_edges = {tuple(sorted((a, b))) for a, b in zip(out_path, out_path[1:])}
            _, back_path = self._walk({node: 0.0}, home, penalty_edges=used | out_edges, penalty=6.0)
            if len(back_path) < 2:
                continue
            loop = [start.point, *(self.nodes[n] for n in out_path), *(self.nodes[n] for n in back_path[1:]), start.point]
            length = sum(dist(a, b) for a, b in zip(loop, loop[1:]))
            if length < target * 0.75:
                continue
            back_edges = {tuple(sorted((a, b))) for a, b in zip(back_path, back_path[1:])}
            shared = len(out_edges & back_edges)
            score = abs(length - target) + 12.0 * shared
            if back_path[-1] == out_path[0]:
                # returning through the same junction retraces the first bit
                score += 2.0 * dist(start.point, self.nodes[out_path[0]])
            if best is None or score < best[0]:
                best = (score, loop)
            if score < 5:
                break
        if best is None:
            return self.turn_around(start, target, used)
        loop = best[1]
        remaining = target
        for index, (a, b) in enumerate(zip(loop, loop[1:])):
            length = dist(a, b)
            if length >= remaining:
                return [*loop[:index + 1], at(a, b, remaining / length)]
            remaining -= length
        return loop

    def turn_around(self, start, target, used):
        """Fallback tail: run out along the least used roads and stop."""
        edge = start.edge
        lengths = {node: dist(start.point, self.nodes[node]) for node in edge}
        costs = {node: length * (4 if edge in used else 1) for node, length in lengths.items()}
        queue = sorted((cost, node) for node, cost in costs.items())
        parents = {}
        farthest = edge[0]
        finish = None
        while queue:
            cost, node = heappop(queue)
            if cost != costs[node]:
                continue
            if lengths[node] > lengths[farthest]:
                farthest = node
            if lengths[node] >= target:
                finish = node
                break
            for neighbor, length in self.neighbors[node]:
                segment = tuple(sorted((node, neighbor)))
                if segment in self.closed:
                    continue
                candidate = cost + length * (4 if segment in used else 1)
                if candidate < costs.get(neighbor, inf):
                    costs[neighbor] = candidate
                    lengths[neighbor] = lengths[node] + length
                    parents[neighbor] = node
                    heappush(queue, (candidate, neighbor))
        path = []
        node = finish or farthest
        while node is not None:
            path.append(self.nodes[node])
            node = parents.get(node)
        path = [start.point, *reversed(path)]
        remaining = target
        for index, (a, b) in enumerate(zip(path, path[1:])):
            length = dist(a, b)
            if length >= remaining:
                return [*path[:index + 1], at(a, b, remaining / length)]
            remaining -= length
        return path
