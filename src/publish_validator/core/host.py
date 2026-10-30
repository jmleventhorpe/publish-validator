"""The interface between the validator and a DCC (Blender, Maya, Houdini...).

Supporting a new application means subclassing :class:`Host` and implementing
the small set of scene operations below. Everything else (discovery, running,
reporting, config) is shared.

Hosts can add their own helper methods (e.g. ``BlenderHost.meshes()``); checks
limited to that host via ``hosts = {"blender"}`` can use them freely.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from .model import Component


class Host:
    """Base class for application adapters.

    A "node" is whatever the application uses for scene objects: a
    ``bpy.types.Object`` in Blender, a long DAG path in Maya, a ``hou.Node``
    in Houdini. The core never looks inside nodes; it only passes them back to
    the host.
    """

    #: Short identifier used in check ``hosts`` sets and config, e.g. "blender".
    name: str = ""

    # -- Required -------------------------------------------------------------

    def selection(self) -> list[Any]:
        """Currently selected nodes."""
        raise NotImplementedError

    def select(self, targets: Iterable[Any]) -> None:
        """Replace the selection with ``targets`` (nodes and/or Components)."""
        raise NotImplementedError

    def find(self, name: str) -> Any | None:
        """Look a node up by name, or return None."""
        raise NotImplementedError

    def parent(self, node: Any) -> Any | None:
        raise NotImplementedError

    def children(self, node: Any) -> list[Any]:
        raise NotImplementedError

    def get_property(self, node: Any, key: str, default: Any = None) -> Any:
        """Read a custom property / attribute / parm from a node."""
        raise NotImplementedError

    def find_by_property(self, key: str) -> list[Any]:
        """All nodes in the scene that carry the custom property ``key``."""
        raise NotImplementedError

    # -- Optional, with sensible defaults --------------------------------------

    def node_name(self, node: Any) -> str:
        """Short name of a node, as an artist would recognise it."""
        return str(getattr(node, "name", node))

    def display_name(self, target: Any) -> str:
        """Name used for a target in reports and logs."""
        if isinstance(target, Component):
            indices = _compress(target.indices)
            return f"{self.node_name(target.node)}.{target.kind}[{indices}]"
        return self.node_name(target)

    def descendants(self, node: Any) -> Iterator[Any]:
        """Depth-first walk of everything below ``node``."""
        for child in self.children(node):
            yield child
            yield from self.descendants(child)

    def watch_selection(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Call ``callback`` when the selection changes.

        Returns a function that removes the watch. Hosts without selection
        events can keep this no-op default.
        """
        return lambda: None


def _compress(indices: Iterable[int], limit: int = 6) -> str:
    """Render ``[1, 2, 3, 7]`` as ``"1:3,7"`` and truncate long lists."""
    ordered = sorted(set(indices))
    ranges: list[str] = []
    start = prev = None
    for index in ordered:
        if start is None:
            start = prev = index
        elif index == prev + 1:
            prev = index
        else:
            ranges.append(f"{start}" if start == prev else f"{start}:{prev}")
            start = prev = index
    if start is not None:
        ranges.append(f"{start}" if start == prev else f"{start}:{prev}")
    if len(ranges) > limit:
        ranges = [*ranges[:limit], "..."]
    return ",".join(ranges)
