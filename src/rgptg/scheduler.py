from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .models import NodeStatus, ThoughtNode


class DAGScheduler:
    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers

    def run(
        self,
        nodes: list[ThoughtNode],
        worker: Callable[[ThoughtNode, dict[str, str]], str],
    ) -> list[ThoughtNode]:
        active = {node.id: node for node in nodes if node.status != NodeStatus.PRUNED}
        completed: dict[str, str] = {}
        while len(completed) < len(active):
            ready = [
                node
                for node in active.values()
                if node.id not in completed
                and all(dep not in active or dep in completed for dep in node.depends_on)
            ]
            if not ready:
                waiting = sorted(set(active) - set(completed))
                raise ValueError(f"Dependency cycle or missing dependency among: {waiting}")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(worker, node, completed.copy()): node for node in ready}
                for future in as_completed(futures):
                    node = futures[future]
                    node.content = future.result()
                    node.status = NodeStatus.DONE
                    completed[node.id] = node.content
        return nodes
