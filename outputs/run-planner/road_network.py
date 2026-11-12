"""Route between selected positions on the bundled pedestrian road network.

Besides plain shortest paths this module knows where the campus water and
buildings are: edges that cut through a building or a lake are heavily
penalised, so the planner walks around them whenever a footpath exists.
"""

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import dist, hypot, inf


Point = tuple[float, float]
Polygon = list[Point]

# Extra cost multiplier for an edge that geometrically crosses one of these.
SOLID_KINDS = ("water", "building")
PENALTY = 40.0
# How far a point may be nudged onto the next clean path when the closest one
# cuts through a building (metres of effective distance).
SNAP_PENALTY = 30.0
# Mild preference for footpaths over the car loop around campus.
STYLE_WEIGHT = {"path": 1.0, "road": 1.06, "major": 1.22}
# Edges whose midpoint falls outside the campus rectangle are priced up: walking
# out of the run zone earns no credit in the app and looks obviously staged.
OUTSIDE_PENALTY = 8.0


@dataclass(frozen=True)
class RoadPosition:
    edge: tuple[int, int]
    point: Point
    offset: float


@dataclass(frozen=True)
class Obstacle:
    kind: str
    points: Polygon
    box: tuple[float, float, float, float] = field(default_factory=tuple)

    def contains(self, point: Point) -> bool:
        min_x, min_y, max_x, max_y = self.box
        x, y = point
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return False
        hit = False
        polygon = self.points
        for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
            if (y1 > y) != (y2 > y):
                if x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
                    hit = not hit
        return hit

    def crossed_by(self, a: Point, b: Point) -> bool:
        min_x, min_y, max_x, max_y = self.box
        if max(a[0], b[0]) < min_x or min(a[0], b[0]) > max_x:
            return False
        if max(a[1], b[1]) < min_y or min(a[1], b[1]) > max_y:
            return False
        if self.contains(a) or self.contains(b):
            return True
        polygon = self.points
        for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
            if _segments_meet(a, b, (x1, y1), (x2, y2)):
                return True
        return False


def _segments_meet(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    dx1, dy1 = p2[0] - p1[0], p2[1] - p1[1]
    dx2, dy2 = p4[0] - p3[0], p4[1] - p3[1]
    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) < 1e-12:
        return False
    t = ((p3[0] - p1[0]) * dy2 - (p3[1] - p1[1]) * dx2) / denominator
    u = ((p3[0] - p1[0]) * dy1 - (p3[1] - p1[1]) * dx1) / denominator
    return 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0


def _box(points: Polygon) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def read_obstacles(data: dict, kinds=SOLID_KINDS) -> list[Obstacle]:
    obstacles = []
    for kind, points in data.get("areas", []):
        if kind in kinds and len(points) >= 3:
            obstacles.append(Obstacle(kind, [tuple(point) for point in points], _box(points)))
    return obstacles


class RoadNetwork:
    def __init__(self, data: dict, *, avoid=SOLID_KINDS, penalty: float = PENALTY,
                 container=None, outside_penalty: float = OUTSIDE_PENALTY):
        self.nodes = [tuple(point) for point in data["nodes"]]
        self.penalty = penalty
        self.obstacles = read_obstacles(data, avoid) if avoid else []
        # The map carries arterial roads that run kilometres off campus; a route
        # that wanders out there is outside the run zone and gets no credit.
        # Everything whose midpoint leaves the campus rectangle is priced up.
        if container is None:
            bounds = data.get("bounds")
            if bounds:
                low_x, low_y, high_x, high_y = bounds
                inset = 25.0
                container = (low_x + inset, low_y + inset, high_x - inset, high_y - inset)
        self.container = container
        self.outside_penalty = outside_penalty
        styles: dict[tuple[int, int], str] = {}
        self.edges = set()
        for style, walkable, ids in data["roads"]:
            if not walkable:
                continue
            for a, b in zip(ids, ids[1:]):
                if self.nodes[a] == self.nodes[b]:
                    continue
                edge = (a, b) if a < b else (b, a)
                self.edges.add(edge)
                # A way that revisits an edge keeps its best (walkable) style.
                if edge not in styles or STYLE_WEIGHT.get(style, 1.0) < STYLE_WEIGHT.get(styles[edge], 1.0):
                    styles[edge] = style
        self.edges = sorted(self.edges)
        self.solid: set[tuple[int, int]] = set()
        self.outside: set[tuple[int, int]] = set()
        self.neighbors: list[list[tuple[int, float, float]]] = [[] for _ in self.nodes]
        self.weight: dict[tuple[int, int], float] = {}
        for edge in self.edges:
            a, b = edge
            length = dist(self.nodes[a], self.nodes[b])
            weight = length * STYLE_WEIGHT.get(styles.get(edge, "road"), 1.06)
            kind = self.crossing(self.nodes[a], self.nodes[b])
            if kind:
                self.solid.add(edge)
                weight *= penalty
            if not self.inside(((self.nodes[a][0] + self.nodes[b][0]) * 0.5,
                                (self.nodes[a][1] + self.nodes[b][1]) * 0.5)):
                self.outside.add(edge)
                weight *= outside_penalty
            self.weight[edge] = weight
            self.neighbors[a].append((b, length, weight))
            self.neighbors[b].append((a, length, weight))

    def inside(self, point: Point) -> bool:
        if not self.container:
            return True
        low_x, low_y, high_x, high_y = self.container
        return low_x <= point[0] <= high_x and low_y <= point[1] <= high_y

    def crossing(self, a: Point, b: Point) -> str | None:
        for obstacle in self.obstacles:
            if obstacle.crossed_by(a, b):
                return obstacle.kind
        return None

    def nearest(self, point: Point) -> RoadPosition:
        best = None
        best_score = inf
        for edge in self.edges:
            a, b = (self.nodes[node] for node in edge)
            dx, dy = b[0] - a[0], b[1] - a[1]
            fraction = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)
            fraction = max(0.0, min(fraction, 1.0))
            projection = (a[0] + dx * fraction, a[1] + dy * fraction)
            offset = hypot(point[0] - projection[0], point[1] - projection[1])
            # Prefer a pavement that does not cut through a building, even if a
            # slightly further one is the geometric winner.
            score = offset + (SNAP_PENALTY if edge in self.solid else 0.0)
            if score < best_score:
                best_score = score
                best = RoadPosition(edge, projection, offset)
        if best is None:
            raise ValueError("地图没有可规划的道路。")
        return best

    def shortest(self, start: RoadPosition, end: RoadPosition) -> tuple[float, list[Point]]:
        best = dist(start.point, end.point) if start.edge == end.edge else inf
        finish = None
        previous: dict[int, int] = {}
        costs = {node: dist(start.point, self.nodes[node]) for node in start.edge}
        goals = {node: dist(end.point, self.nodes[node]) for node in end.edge}
        queue = sorted((cost, node) for node, cost in costs.items())

        while queue:
            cost, node = heappop(queue)
            if cost > costs.get(node, inf):
                continue
            if node in goals and cost + goals[node] < best:
                best, finish = cost + goals[node], node
            if cost >= best:
                continue
            for neighbor, _length, weight in self.neighbors[node]:
                candidate = cost + weight
                if candidate < costs.get(neighbor, inf):
                    costs[neighbor] = candidate
                    previous[neighbor] = node
                    heappush(queue, (candidate, neighbor))

        if finish is None and best == inf:
            raise ValueError("选中的位置之间没有连通的步行路网，请改选附近的道路。")
        if finish is None:
            return best, [start.point, end.point]
        chain = []
        node = finish
        while node is not None:
            chain.append(self.nodes[node])
            node = previous.get(node)
        path = [start.point, *reversed(chain), end.point]
        cleaned = [path[0]]
        for point in path[1:]:
            if dist(cleaned[-1], point) > 1e-6:
                cleaned.append(point)
        return sum(dist(a, b) for a, b in zip(cleaned, cleaned[1:])), cleaned

    def through(self, points: list[RoadPosition]) -> tuple[float, list[Point], list[float]]:
        total, route, distances = 0.0, [points[0].point], []
        for start, end in zip(points, points[1:]):
            length, segment = self.shortest(start, end)
            total += length
            route.extend(segment[1:])
            distances.append(total)
        return total, route, distances

    def violations(self, route: list[Point]) -> list[tuple[str, float]]:
        """Report how much of ``route`` still cuts through water or a building."""
        found: dict[str, float] = {}
        for a, b in zip(route, route[1:]):
            kind = self.crossing(a, b)
            if kind:
                found[kind] = found.get(kind, 0.0) + dist(a, b)
        return sorted(found.items())

    def outside_metres(self, route: list[Point]) -> float:
        """How much of ``route`` lies outside the campus rectangle."""
        total = 0.0
        for a, b in zip(route, route[1:]):
            midpoint = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            if not self.inside(midpoint):
                total += dist(a, b)
        return total

    def coverage(self) -> str:
        total = sum(dist(self.nodes[a], self.nodes[b]) for a, b in self.edges)
        blocked = sum(dist(self.nodes[a], self.nodes[b]) for a, b in self.edges
                      if self.weight.get((a, b), 0) > dist(self.nodes[a], self.nodes[b]) * 1.5)
        return f"{len(self.nodes)} 个路点 / {len(self.edges)} 段 / {total / 1000:.1f} 公里，其中 {blocked / 1000:.2f} 公里绕行"