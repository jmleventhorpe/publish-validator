"""Helpers for testing checks without opening a DCC.

::

    from publish_validator.testing import FakeHost, FakeNode, run_check

    def test_root_not_empty():
        root = FakeNode("chair", props={"pv_task": "model"})
        result = run_check(RootNotEmpty, root)
        assert result.status is Status.FAILED

``FakeNode`` accepts arbitrary keyword attributes, so a check that reads
``node.scale`` can be tested with ``FakeNode("cube", scale=(2, 1, 1))``.
Host-specific checks (``hosts = {"blender"}``) are better tested inside the
host itself; see ``tests/blender``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .core.check import Check
from .core.config import CheckConfig, Config
from .core.host import Host
from .core.model import CheckResult, Component
from .core.runner import run
from .core.subject import PropertyResolver, Subject


class FakeNode:
    """A minimal scene node: a name, a parent, children, custom props and any attributes."""

    def __init__(
        self,
        name: str,
        *children: FakeNode,
        type: str = "node",
        props: Mapping[str, Any] | None = None,
        **attributes: Any,
    ) -> None:
        self.name = name
        self.type = type
        self.props = dict(props or {})
        self.parent: FakeNode | None = None
        self.children: list[FakeNode] = []
        for key, value in attributes.items():
            setattr(self, key, value)
        for child in children:
            self.add(child)

    def add(self, child: FakeNode) -> FakeNode:
        child.parent = self
        self.children.append(child)
        return child

    def walk(self) -> Iterable[FakeNode]:
        yield self
        for child in self.children:
            yield from child.walk()

    def __repr__(self) -> str:
        return f"FakeNode({self.name!r})"


class FakeHost(Host):
    """In-memory host over a list of :class:`FakeNode` trees."""

    def __init__(self, *roots: FakeNode, name: str = "fake") -> None:
        self.name = name
        self.roots = list(roots)
        self.selected: list[Any] = []
        self._watchers: list[Callable[[], None]] = []

    def nodes(self) -> Iterable[FakeNode]:
        for root in self.roots:
            yield from root.walk()

    def selection(self) -> list[Any]:
        return list(self.selected)

    def select(self, targets: Iterable[Any]) -> None:
        self.selected = list(targets)
        for callback in list(self._watchers):
            callback()

    def find(self, name: str) -> FakeNode | None:
        return next((n for n in self.nodes() if n.name == name), None)

    def parent(self, node: FakeNode) -> FakeNode | None:
        return node.parent

    def children(self, node: FakeNode) -> list[FakeNode]:
        return list(node.children)

    def get_property(self, node: FakeNode, key: str, default: Any = None) -> Any:
        return node.props.get(key, default)

    def find_by_property(self, key: str) -> list[FakeNode]:
        return [n for n in self.nodes() if key in n.props]

    def node_name(self, node: Any) -> str:
        if isinstance(node, Component):
            node = node.node
        return getattr(node, "name", str(node))

    def watch_selection(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._watchers.append(callback)
        return lambda: self._watchers.remove(callback)


def make_subject(
    root: FakeNode,
    *,
    task: str | None = None,
    asset_type: str | None = None,
    host: Host | None = None,
) -> Subject:
    """A Subject for ``root``, reading ``pv_*`` props unless task/asset_type are given."""
    subject = PropertyResolver().subject_for(host or FakeHost(root), root)
    return Subject(
        name=subject.name,
        asset_type=asset_type or subject.asset_type,
        task=task or subject.task,
        root=root,
    )


def run_check(
    check_cls: type[Check],
    root: FakeNode,
    *,
    host: Host | None = None,
    fix: bool = False,
    settings: Mapping[str, Any] | None = None,
    task: str | None = None,
    asset_type: str | None = None,
) -> CheckResult:
    """Run a single check against ``root`` and return its result.

    Applicability filters (hosts/tasks/asset_types) are ignored so the check
    always runs; test those separately with ``check_cls.applies_to``.
    """
    host = host or FakeHost(root)
    subject = make_subject(root, task=task, asset_type=asset_type, host=host)
    config = Config(checks={check_cls.id: CheckConfig(enabled=True, settings=dict(settings or {}))})
    report = run(subject, host, [check_cls], config=config, fix=fix)
    return report.results[0]
