"""The one answer to "what may run at the same time" for a bulk apply.

The bulk path (`POST /bulk/stream-apply`) used to start its settings in client
order and let the pool decide the overlap, with no idea that two settings can
share something. Measured on 2026-10-06: `network:dns_over_https` ran before
`network:dns_security` had switched the resolvers it needs, and two settings on
one NIC (both restart the adapter) ran together, one reading the link while the
other had it down.

A setting says what it shares in two places on `SettingExecutor`, never here:
`apply_after` (ids that must finish first) and `resource_key` (what it holds
while it writes). The planner is pure: it reads those and returns lanes.

A lane is a list of settings that must run one after another, in order. Settings
in different lanes share nothing and are free to overlap, so the caller's own
concurrency limit (four for the stream) is the only cap. Lanes are the connected components of "shares a resource
or is ordered after", because a lane is the smallest unit that can be run
serially without ever blocking on another lane.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Sequence

from fpstune.settings.base import SettingExecutor


class BulkPlanError(ValueError):
    """The declared ordering cannot be honoured: an unknown id or a cycle."""


def _order(items: Sequence[SettingExecutor], edges: dict[int, set[int]]) -> list[int]:
    """Indices of `items` in dependency order, input order breaking ties.

    `edges[i]` is the set of indices that must come before `i`. A cycle leaves its
    members out, so the result is shorter than `items`.
    """
    waiting = {i: len(edges.get(i, ())) for i in range(len(items))}
    dependents: dict[int, list[int]] = {}
    for i, before in edges.items():
        for b in before:
            dependents.setdefault(b, []).append(i)
    ready = [i for i, n in waiting.items() if n == 0]
    heapq.heapify(ready)
    ordered: list[int] = []
    while ready:
        i = heapq.heappop(ready)
        ordered.append(i)
        for d in dependents.get(i, ()):
            waiting[d] -= 1
            if waiting[d] == 0:
                heapq.heappush(ready, d)
    return ordered


def _dependency_edges(items: Sequence[SettingExecutor]) -> dict[int, set[int]]:
    """For each index, the indices of the items it must wait for.

    An `apply_after` id that is not among `items` adds no edge: it was not asked
    for in this run, so there is nothing to wait for.
    """
    positions: dict[str, list[int]] = {}
    for i, item in enumerate(items):
        positions.setdefault(item.id, []).append(i)
    edges: dict[int, set[int]] = {}
    for i, item in enumerate(items):
        for dep in item.apply_after:
            for j in positions.get(dep, ()):
                edges.setdefault(i, set()).add(j)
    return edges


def plan_lanes[S: SettingExecutor](settings: Sequence[S]) -> list[list[S]]:
    """Split `settings` into lanes: serial inside a lane, concurrent between lanes.

    Two settings land in one lane when they share a `resource_key`, or when one is
    `apply_after` the other (both present in `settings`), directly or through
    others. Inside a lane the order is the dependency order, and the order the
    caller gave wherever no dependency decides it. Lanes are ordered by their
    first member's position, so an unrelated run keeps the client's order.

    Raises `BulkPlanError` on a dependency cycle among `settings`.
    """
    count = len(settings)
    parent = list(range(count))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    edges = _dependency_edges(settings)
    for i, before in edges.items():
        for j in before:
            join(i, j)

    holder: dict[str, int] = {}
    for i, item in enumerate(settings):
        key = item.resource_key
        if key is None:
            continue
        if key in holder:
            join(i, holder[key])
        else:
            holder[key] = i

    ordered = _order(settings, edges)
    if len(ordered) != count:
        stuck = sorted({settings[i].id for i in set(range(count)) - set(ordered)})
        raise BulkPlanError(f"apply_after forms a cycle among: {', '.join(stuck)}")

    lanes: dict[int, list[S]] = {}
    for i in ordered:
        lanes.setdefault(find(i), []).append(settings[i])
    return [lanes[root] for root in sorted(lanes)]


def validate_declarations(settings: Iterable[SettingExecutor]) -> None:
    """Fail loudly on a bad `apply_after`: an id nothing registers, or a cycle.

    Run once when the registry is built, over every setting it holds, so a typo or
    a loop is a start-up error that names the row rather than a bulk run that
    silently skips the wait.
    """
    items = list(settings)
    known = {item.id for item in items}
    for item in items:
        for dep in item.apply_after:
            if dep not in known:
                raise BulkPlanError(f"{item.id} is declared apply_after unknown setting {dep!r}")
    ordered = _order(items, _dependency_edges(items))
    if len(ordered) != len(items):
        stuck = sorted({items[i].id for i in set(range(len(items))) - set(ordered)})
        raise BulkPlanError(f"apply_after forms a cycle among: {', '.join(stuck)}")
