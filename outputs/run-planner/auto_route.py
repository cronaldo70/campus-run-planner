"""Plan one open run: start where the phone is, punch every checkpoint, finish anywhere.

The loop planner repeats a ring, which is the shape a machine draws. A real
student walks out of the dorm, takes the checkpoints in whatever order is
closest, and stops near home. That is a shortest Hamiltonian *path* on the road
network (start fixed, end free), followed by a natural tail leg whenever the
total is still under the required distance.
"""

from __future__ import annotations

import math
import random
from heapq import heappop, heappush

Point = tuple[float, float]
INF = float("inf")

# The app accepts a punch within this radius of the checkpoint.
PUNCH_RADIUS = 50.0


def _costs_from(net, position) -> dict[int, float]:
    """Dijkstra over the weighted network, seeded from a snapped position."""
    costs = {node: math.dist(position.point, net.nodes[node]) for node in position.edge}
    heap = [(cost, node) for node, cost in costs.items()]
    heap.sort()
    while heap:
        cost, node = heappop(heap)
        if cost > costs.get(node, INF):
            continue
        for neighbour, _length, weight in net.neighbors[node]:
            candidate = cost + weight
            if candidate < costs.get(neighbour, INF):
                costs[neighbour] = candidate
                heappush(heap, (candidate, neighbour))
    return costs


def _matrix(net, positions) -> list[list[float]]:
    size = len(positions)
    table = [[0.0] * size for _ in range(size)]
    for row in range(size):
        costs = _costs_from(net, positions[row])
        for column in range(row + 1, size):
            target = positions[column]
            if target.edge == positions[row].edge:
                best = math.dist(positions[row].point, target.point)
            else:
                best = min((costs.get(node, INF) + math.dist(target.point, net.nodes[node])
                            for node in target.edge), default=INF)
            table[row][column] = table[column][row] = best
    return table


def best_order(table: list[list[float]]) -> list[int]:
    """Shortest path from node 0 through every node, ending anywhere (Held-Karp)."""
    count = len(table)
    if count <= 2:
        return list(range(count))
    others = list(range(1, count))
    size = len(others)
    full = 1 << size
    dp = [[INF] * size for _ in range(full)]
    parent = [[-1] * size for _ in range(full)]
    for index, node in enumerate(others):
        dp[1 << index][index] = table[0][node]
    for mask in range(full):
        row = dp[mask]
        for last in range(size):
            current = row[last]
            if current == INF:
                continue
            for nxt in range(size):
                bit = 1 << nxt
                if mask & bit:
                    continue
                candidate = current + table[others[last]][others[nxt]]
                target = mask | bit
                if candidate < dp[target][nxt]:
                    dp[target][nxt] = candidate
                    parent[target][nxt] = last
    best_mask = full - 1
    end, best = -1, INF
    for last in range(size):
        if dp[best_mask][last] < best:
            best, end = dp[best_mask][last], last
    order = []
    mask, node = best_mask, end
    while node != -1:
        order.append(others[node])
        previous = parent[mask][node]
        mask ^= 1 << node
        node = previous
    order.reverse()
    return [0] + order


def _route_metres(route: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(route, route[1:]))


def _distance_to_route(point: Point, route: list[Point]) -> float:
    best = INF
    for a, b in zip(route, route[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        span = dx * dx + dy * dy
        if span <= 1e-9:
            best = min(best, math.dist(point, a))
            continue
        t = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / span))
        best = min(best, math.dist(point, (a[0] + dx * t, a[1] + dy * t)))
    return best


def _node_position(net, node: int):
    """A RoadPosition sitting exactly on a network node."""
    from road_network import RoadPosition

    for edge in net.edges:
        if node in edge:
            return RoadPosition(edge, net.nodes[node], 0.0)
    raise ValueError(f"路点 {node} 没有相邻的边。")


def plan(net, start: Point, checkpoints: list[Point], *, minimum: float = 2500.0,
         punch: float = PUNCH_RADIUS, seed=None) -> dict:
    """Return the route, its length, the checkpoint order and any residual warning."""
    if not checkpoints:
        raise ValueError("还没有打卡点：先读取手机画面或在地图上点选。")
    # A label often sits in the middle of a building. What you actually punch
    # from is the pavement next to the pin, so aim straight at the access point
    # instead of walking to the centroid.
    aims = [net.nearest(point).point for point in checkpoints]
    positions = [net.nearest(start)] + [net.nearest(point) for point in aims]
    table = _matrix(net, positions)
    order = best_order(table)
    route: list[Point] = [start]
    legs = []
    for previous, current in zip(order, order[1:]):
        length, segment = net.shortest(positions[previous], positions[current])
        route.extend(segment[1:])
        legs.append(length)
    metres = _route_metres(route)
    required = len(route)

    additions = 0
    rng = random.Random(seed)
    candidates = list(range(0, len(net.nodes), max(1, len(net.nodes) // 90)))
    while metres < minimum and additions < 4:
        remaining = minimum - metres
        end = net.nearest(route[-1])
        costs = _costs_from(net, end)
        scored = []
        for node in candidates:
            cost = costs.get(node, INF)
            if cost == INF or cost < 60:
                continue
            if _distance_to_route(net.nodes[node], route) < 80:
                continue
            # Prefer a tail leg that lands near the needed distance, and mix in
            # some variety so two runs are never the same shape.
            scored.append((abs(cost - remaining) + rng.uniform(0, 60), cost, node))
        if not scored:
            break
        scored.sort()
        _score, cost, node = scored[0]
        length, segment = net.shortest(end, _node_position(net, node))
        route.extend(segment[1:])
        metres = _route_metres(route)
        legs.append(length)
        additions += 1

    # A tail leg is picked from coarse candidates, so it can overshoot by
    # hundreds of metres. Cut it back to the first vertex that reaches the
    # minimum, keeping every vertex that serves a checkpoint untouched.
    if metres > minimum + 200.0 and len(route) > required:
        distances = [0.0]
        for previous, current in zip(route, route[1:]):
            distances.append(distances[-1] + math.dist(previous, current))
        for index in range(required, len(route)):
            if distances[index] >= minimum:
                route = route[:index + 1]
                metres = distances[index]
                break

    # What the runner actually punches from is the pavement next to the pin: the
    # label itself often sits on a building centroid, tens of metres from any path.
    access = []
    covering = []
    for index, point in enumerate(checkpoints, start=1):
        snapped = net.nearest(point).point
        reached = _distance_to_route(snapped, route)
        offset = math.dist(point, snapped)
        access.append((reached, offset))
        if reached > 5.0:
            covering.append(f"第 {index} 个打卡点没有真正经过，最近处还差 {reached:.0f} 米")
        elif offset > 45.0:
            covering.append(f"第 {index} 个打卡点在图上的位置离道路 {offset:.0f} 米（多半在楼里），"
                            f"App 的打卡点一般设在楼门口，出发前确认一下")
    return {
        "route": route,
        "metres": metres,
        "order": order,
        "legs": legs,
        "tail_legs": additions,
        "access": access,
        "warnings": covering,
    }


def describe(net, start: Point, checkpoints: list[Point], result: dict, names: list[str] | None = None) -> str:
    labels = names or [f"打卡点 {index}" for index in range(1, len(checkpoints) + 1)]
    order = result["order"][1:]
    walk = " → ".join(["起点"] + [labels[index - 1] for index in order] + ["终点"])
    note = f"开放式路线 {result['metres'] / 1000:.2f} 公里，起点当前位置"
    if result["tail_legs"]:
        note += f"（补里程 {result['tail_legs']} 段）"
    lines = [walk, note]
    violations = net.violations(result["route"])
    if violations:
        lines.append("⚠ " + "、".join(f"{kind} {metres:.0f} 米" for kind, metres in violations) + " 穿行")
    lines.extend("⚠ " + warning for warning in result["warnings"])
    return "\n".join(lines)