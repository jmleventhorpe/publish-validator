"""Maya host adapter. STUB: written against the Maya API but not yet tested in Maya.

Nodes are long DAG path strings (``|chair|geo|seat``), so they stay valid
through renames of unrelated nodes and need no PyMEL.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import maya.api.OpenMaya as om
from maya import cmds

from ...core.host import Host
from ...core.model import Component

_COMPONENT_NAMES = {"vertex": "vtx", "edge": "e", "face": "f"}


class MayaHost(Host):
    name = "maya"

    def selection(self) -> list[str]:
        return cmds.ls(selection=True, long=True, objectsOnly=True) or []

    def select(self, targets: Iterable[Any]) -> None:
        names: list[str] = []
        for target in targets:
            if isinstance(target, Component):
                kind = _COMPONENT_NAMES[target.kind]
                names += [f"{target.node}.{kind}[{i}]" for i in target.indices]
            else:
                names.append(str(target))
        existing = [n for n in names if cmds.objExists(n)]
        if existing:
            cmds.select(existing, replace=True)
        else:
            cmds.select(clear=True)

    def find(self, name: str) -> str | None:
        matches = cmds.ls(name, long=True) or []
        return matches[0] if len(matches) == 1 else None

    def parent(self, node: str) -> str | None:
        parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
        return parents[0] if parents else None

    def children(self, node: str) -> list[str]:
        return cmds.listRelatives(node, children=True, fullPath=True, type="transform") or []

    def get_property(self, node: str, key: str, default: Any = None) -> Any:
        if not cmds.attributeQuery(key, node=node, exists=True):
            return default
        return cmds.getAttr(f"{node}.{key}")

    def find_by_property(self, key: str) -> list[str]:
        return cmds.ls(f"*.{key}", objectsOnly=True, long=True, recursive=True) or []

    def node_name(self, node: Any) -> str:
        if isinstance(node, Component):
            node = node.node
        return str(node).rsplit("|", 1)[-1]

    def watch_selection(self, callback: Callable[[], None]) -> Callable[[], None]:
        callback_id = om.MEventMessage.addEventCallback("SelectionChanged", lambda *_: callback())
        return lambda: om.MMessage.removeCallback(callback_id)

    # -- Maya helpers for checks ---------------------------------------------------

    def meshes(self, root: str) -> list[str]:
        """Non-intermediate mesh shapes below ``root``."""
        shapes = cmds.listRelatives(root, allDescendents=True, fullPath=True, type="mesh") or []
        return [s for s in shapes if not cmds.getAttr(f"{s}.intermediateObject")]
