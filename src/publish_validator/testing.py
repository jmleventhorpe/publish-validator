"""Helpers for testing checks without opening Blender, Maya or Houdini.

    from publish_validator import FAILED
    from publish_validator.testing import FakeNode, run_check_on

    def test_empty_root():
        root = FakeNode("chair")
        assert run_check_on(RootNotEmpty, root).status == FAILED

FakeNode takes any extra attributes, so FakeNode("cube", scale=(2, 1, 1)) works
for a check that reads node.scale.
"""

from .core.check import Context
from .core.host import Host
from .core.results import Component
from .core.subject import Subject
from .core.validator import run_check


class FakeNode:
    def __init__(self, name, *children, props=None, **attributes):
        self.name = name
        self.props = props or {}  # custom properties, as read by get_property()
        self.parent = None
        self.children = []
        for key, value in attributes.items():
            setattr(self, key, value)
        for child in children:
            self.add(child)

    def add(self, child):
        child.parent = self
        self.children.append(child)
        return child

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def __repr__(self):
        return f"FakeNode({self.name!r})"


class FakeHost(Host):
    """A host whose scene is a few FakeNode trees."""

    def __init__(self, *roots, name="fake"):
        self.name = name
        self.roots = list(roots)
        self.selected = []

    def all_nodes(self):
        for root in self.roots:
            yield from root.walk()

    def selection(self):
        return list(self.selected)

    def select(self, targets):
        self.selected = list(targets)

    def find(self, name):
        for node in self.all_nodes():
            if node.name == name:
                return node
        return None

    def parent(self, node):
        return node.parent

    def children(self, node):
        return list(node.children)

    def get_property(self, node, key, default=None):
        return node.props.get(key, default)

    def find_by_property(self, key):
        return [node for node in self.all_nodes() if key in node.props]

    def node_name(self, node):
        if isinstance(node, Component):
            node = node.node
        return node.name


def run_check_on(check_class, root, fix=False, settings=None, task=None, asset_type=None):
    """Run one check on a FakeNode tree and return its CheckResult.

    The check's hosts/tasks/asset_types are ignored, so it always runs.
    """
    host = FakeHost(root)
    subject = Subject(name=root.name, asset_type=asset_type, task=task, root=root)
    options = {"settings": settings or {}}
    return run_check(check_class, Context(subject, host), options, fix)
