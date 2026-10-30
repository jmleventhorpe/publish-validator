"""Houdini host. NOT TESTED IN HOUDINI YET.

Nodes are hou.Node objects. Custom properties are spare parms.
"""

import hou

from ...core.host import Host
from ...core.results import Component


class HoudiniHost(Host):
    name = "houdini"

    def selection(self):
        return list(hou.selectedNodes())

    def select(self, targets):
        hou.clearAllSelected()
        for target in targets:
            node = target.node if isinstance(target, Component) else target
            node.setSelected(True)

    def find(self, name):
        return hou.node(name)  # a node path, e.g. "/stage/chair"

    def parent(self, node):
        return node.parent()

    def children(self, node):
        return list(node.children())

    def get_property(self, node, key, default=None):
        parm = node.parm(key)
        return parm.eval() if parm is not None else default

    def find_by_property(self, key):
        return [node for node in hou.node("/").allSubChildren() if node.parm(key) is not None]

    def node_name(self, node):
        if isinstance(node, Component):
            node = node.node
        return node.name()
