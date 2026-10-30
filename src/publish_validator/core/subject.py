"""What is being validated, and how to work that out from the scene.

A :class:`Subject` describes one asset: its name, type, task and root node.
A *resolver* turns a selection (or an explicit node) into a Subject. Studios
with their own pipeline write their own resolver; the built-in
:class:`PropertyResolver` reads plain custom properties from the root node, so
the validator works with no pipeline at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .host import Host


@dataclass(frozen=True, slots=True)
class Subject:
    """The asset being validated.

    Attributes:
        name: Asset name, e.g. "chair".
        asset_type: e.g. "prop", "character", "set". Used to pick checks.
        task: e.g. "model", "lookdev", "rig". Used to pick checks.
        root: The host node at the top of the asset.
        extras: Anything else the resolver knows (version, project, ...).
    """

    name: str
    asset_type: str | None
    task: str | None
    root: Any
    extras: Mapping[str, Any] = field(default_factory=dict)


class ResolveError(Exception):
    """Raised when no single subject can be found. The message is shown to artists."""


@runtime_checkable
class SubjectResolver(Protocol):
    """Turns host state into a :class:`Subject`."""

    def resolve(self, host: Host, node: Any | None = None) -> Subject:
        """Resolve ``node``, or the current selection when ``node`` is None.

        Raises:
            ResolveError: with a message suitable for an artist.
        """
        ...

    def find_all(self, host: Host) -> list[Subject]:
        """Every subject in the scene (for headless / batch validation)."""
        ...


class PropertyResolver:
    """Default resolver: an asset root is any node with a ``pv_task`` property.

    Recognised properties (all optional except the marker)::

        pv_task        "model"      <- marks the node as an asset root
        pv_asset_type  "prop"
        pv_asset_name  "chair"      (defaults to the node's name)

    Any other ``pv_*`` property ends up in ``Subject.extras``.
    Selecting any node inside an asset resolves to its root.
    """

    prefix = "pv_"

    @property
    def marker(self) -> str:
        return f"{self.prefix}task"

    def is_root(self, host: Host, node: Any) -> bool:
        return host.get_property(node, self.marker) is not None

    def subject_for(self, host: Host, root: Any) -> Subject:
        def prop(key: str) -> Any:
            value = host.get_property(root, self.prefix + key)
            return None if value is None else str(value)

        return Subject(
            name=prop("asset_name") or host.node_name(root),
            asset_type=prop("asset_type"),
            task=prop("task"),
            root=root,
        )

    def find_root(self, host: Host, node: Any) -> Any | None:
        while node is not None:
            if self.is_root(host, node):
                return node
            node = host.parent(node)
        return None

    def resolve(self, host: Host, node: Any | None = None) -> Subject:
        candidates = [node] if node is not None else host.selection()
        if not candidates:
            raise ResolveError(f"Select an asset root (a node with a '{self.marker}' property).")
        roots: list[Any] = []
        for candidate in candidates:
            root = self.find_root(host, candidate)
            if root is not None and not any(root is r for r in roots):
                roots.append(root)
        if not roots:
            raise ResolveError(
                f"Nothing selected belongs to an asset. Asset roots carry a "
                f"'{self.marker}' property."
            )
        if len(roots) > 1:
            names = ", ".join(host.node_name(r) for r in roots)
            raise ResolveError(f"Selection spans several assets ({names}); select one.")
        return self.subject_for(host, roots[0])

    def find_all(self, host: Host) -> list[Subject]:
        return [self.subject_for(host, root) for root in host.find_by_property(self.marker)]
