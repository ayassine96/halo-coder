#!/usr/bin/env python3
"""Dependency resolver — topological sort with depends_on/blocks + cycle detection.

SRS OR-R3: A spec with depends_on shall not transition to in_progress until
all dependencies reach implemented or merged.
SRS OR-R4: A spec with blocks shall prevent the blocked spec from entering ready
until the blocker reaches implemented.
"""

from collections import defaultdict, deque


class CycleError(Exception):
    pass


class DependencyResolver:
    """Manage spec dependency ordering."""

    def __init__(self, specs):
        """specs: dict of spec_id → Spec objects."""
        self.specs = specs

    def is_ready(self, spec_id):
        """Check if a spec's dependencies are satisfied (OR-R3).

        Returns True if all depends_on specs are implemented or merged.
        """
        spec = self.specs.get(spec_id)
        if not spec:
            return False
        from halo.common.models import SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED
        for dep_id in spec.depends_on:
            dep = self.specs.get(dep_id)
            if not dep:
                return False
            if dep.status not in (SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED):
                return False
        return True

    def is_unblocked(self, spec_id):
        """Check if a spec is not blocked by any other spec (OR-R4).

        A spec is unblocked if no other spec lists it in its blocks
        that hasn't reached implemented.
        """
        spec = self.specs.get(spec_id)
        if not spec:
            return False
        from halo.common.models import SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED
        for other_id, other in self.specs.items():
            if spec_id in other.blocks:
                if other.status not in (SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED):
                    return False
        return True

    def can_start(self, spec_id):
        """A spec can start if it's ready AND unblocked."""
        return self.is_ready(spec_id) and self.is_unblocked(spec_id)

    def topological_sort(self):
        """Return specs in dependency order. Raises CycleError on cycles."""
        in_degree = defaultdict(int)
        graph = defaultdict(list)

        for spec_id, spec in self.specs.items():
            in_degree.setdefault(spec_id, 0)
            for dep_id in spec.depends_on:
                if dep_id in self.specs:
                    graph[dep_id].append(spec_id)
                    in_degree[spec_id] += 1

        queue = deque(sorted(s for s, d in in_degree.items() if d == 0))
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in sorted(graph[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.specs):
            cyclic = set(self.specs.keys()) - set(result)
            raise CycleError(f"Cycle detected involving: {cyclic}")

        return result

    def get_runnable_specs(self):
        """Return specs that can start now (ready deps + no blockers)."""
        from halo.common.models import SPEC_STATUS_READY
        runnable = []
        for spec_id, spec in self.specs.items():
            if spec.status == SPEC_STATUS_READY and self.can_start(spec_id):
                runnable.append(spec_id)
        return sorted(runnable)

    def get_parallel_groups(self):
        """Group specs into parallelizable batches (no dependency conflicts)."""
        topo = self.topological_sort()
        groups = []
        remaining = set(topo)
        processed = set()

        while remaining:
            batch = []
            for spec_id in sorted(remaining):
                spec = self.specs[spec_id]
                deps_met = all(
                    dep in processed or dep not in self.specs
                    for dep in spec.depends_on
                )
                blockers_done = all(
                    other_id in processed
                    for other_id, other in self.specs.items()
                    if spec_id in other.blocks and other_id in self.specs
                )
                if deps_met and blockers_done:
                    batch.append(spec_id)

            if not batch:
                raise CycleError("Cannot make progress — possible cycle or missing deps")

            groups.append(batch)
            for s in batch:
                remaining.discard(s)
                processed.add(s)

        return groups