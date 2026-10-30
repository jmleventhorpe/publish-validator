"""The Host base class: how the validator talks to an application.

To support a new application, subclass Host and fill in the methods that raise
NotImplementedError. A "node" is whatever the application uses for scene
objects: a bpy Object in Blender, a DAG path in Maya, a hou.Node in Houdini.

Hosts can add their own helpers (BlenderHost.meshes() for example). Checks that
only run in that host can use them.
"""

from .results import Component


class Host:
    name = ""  # e.g. "blender". Checks use it in their `hosts` list.

    def selection(self):
        """The selected nodes."""
        raise NotImplementedError

    def select(self, targets):
        """Replace the selection with these nodes and/or Components."""
        raise NotImplementedError

    def find(self, name):
        """The node with this name, or None."""
        raise NotImplementedError

    def parent(self, node):
        raise NotImplementedError

    def children(self, node):
        raise NotImplementedError

    def get_property(self, node, key, default=None):
        """A custom property (attribute, parm...) stored on a node."""
        raise NotImplementedError

    def find_by_property(self, key):
        """Every node in the scene that has this custom property."""
        raise NotImplementedError

    def node_name(self, node):
        return str(getattr(node, "name", node))

    def display_name(self, target):
        """How a target is written in reports, e.g. "seat" or "seat.face[0, 4]"."""
        if isinstance(target, Component):
            indices = ", ".join(str(i) for i in target.indices[:5])
            if len(target.indices) > 5:
                indices += ", ..."
            return f"{self.node_name(target.node)}.{target.kind}[{indices}]"
        return self.node_name(target)

    def descendants(self, node):
        """Everything below a node."""
        for child in self.children(node):
            yield child
            yield from self.descendants(child)
