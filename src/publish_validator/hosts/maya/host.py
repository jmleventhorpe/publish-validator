"""Maya host. NOT TESTED IN MAYA YET.

Nodes are long DAG paths ("|chair|geo|seat"), so no PyMEL is needed.
"""

from maya import cmds

from ...core.host import Host
from ...core.results import Component

COMPONENT_NAMES = {"vertex": "vtx", "edge": "e", "face": "f"}


class MayaHost(Host):
    name = "maya"

    def selection(self):
        return cmds.ls(selection=True, long=True, objectsOnly=True) or []

    def select(self, targets):
        names = []
        for target in targets:
            if isinstance(target, Component):
                kind = COMPONENT_NAMES[target.kind]
                names += [f"{target.node}.{kind}[{index}]" for index in target.indices]
            else:
                names.append(target)
        names = [name for name in names if cmds.objExists(name)]
        if names:
            cmds.select(names, replace=True)
        else:
            cmds.select(clear=True)

    def find(self, name):
        matches = cmds.ls(name, long=True) or []
        return matches[0] if len(matches) == 1 else None

    def parent(self, node):
        parents = cmds.listRelatives(node, parent=True, fullPath=True)
        return parents[0] if parents else None

    def children(self, node):
        return cmds.listRelatives(node, children=True, fullPath=True, type="transform") or []

    def get_property(self, node, key, default=None):
        if not cmds.attributeQuery(key, node=node, exists=True):
            return default
        return cmds.getAttr(f"{node}.{key}")

    def find_by_property(self, key):
        return cmds.ls(f"*.{key}", objectsOnly=True, long=True, recursive=True) or []

    def node_name(self, node):
        if isinstance(node, Component):
            node = node.node
        return node.split("|")[-1]

    # Helpers for Maya checks.

    def meshes(self, root):
        """Mesh shapes below the root, without intermediate (history) shapes."""
        shapes = cmds.listRelatives(root, allDescendents=True, fullPath=True, type="mesh") or []
        return [shape for shape in shapes if not cmds.getAttr(f"{shape}.intermediateObject")]
