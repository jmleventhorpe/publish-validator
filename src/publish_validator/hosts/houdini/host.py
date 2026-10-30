"""Houdini host adapter. STUB: written against the hou API but not yet tested in Houdini.

Nodes are ``hou.Node`` objects. Custom properties are spare parms.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import hou

from ...core.host import Host
from ...core.model import Component


class HoudiniHost(Host):
    name = "houdini"

    def selection(self) -> list[hou.Node]:
        return list(hou.selectedNodes())

    def select(self, targets: Iterable[Any]) -> None:
        hou.clearAllSelected()
        for target in targets:
            node = target.node if isinstance(target, Component) else target
            if isinstance(node, hou.Node):
                node.setSelected(True)

    def find(self, name: str) -> hou.Node | None:
        return hou.node(name)  # Houdini node paths, e.g. "/stage/chair"

    def parent(self, node: hou.Node) -> hou.Node | None:
        return node.parent()

    def children(self, node: hou.Node) -> list[hou.Node]:
        return list(node.children())

    def get_property(self, node: hou.Node, key: str, default: Any = None) -> Any:
        parm = node.parm(key)
        return parm.eval() if parm is not None else default

    def find_by_property(self, key: str) -> list[hou.Node]:
        return [n for n in hou.node("/").allSubChildren() if n.parm(key) is not None]

    def node_name(self, node: Any) -> str:
        if isinstance(node, Component):
            node = node.node
        return node.name() if isinstance(node, hou.Node) else str(node)

    def display_name(self, target: Any) -> str:
        if isinstance(target, hou.Node):
            return target.path()
        return super().display_name(target)

    def watch_selection(self, callback: Callable[[], None]) -> Callable[[], None]:
        if not hou.isUIAvailable():
            return lambda: None

        def on_select(_selection):
            callback()

        hou.ui.addSelectionCallback(on_select)
        return lambda: hou.ui.removeSelectionCallback(on_select)
