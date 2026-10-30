"""The object every check receives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .host import Host
from .subject import Subject

T = TypeVar("T")


@dataclass(slots=True)
class Context:
    """Everything a check needs while it runs.

    Attributes:
        subject: The asset being validated (``ctx.subject.root`` is its top node).
        host: The application adapter, for scene queries and helpers.
        settings: This check's settings, after studio/project config overrides.
        cache: Shared by every check in one run; use :meth:`cached`.
    """

    subject: Subject
    host: Host
    settings: Any = None
    cache: dict[Any, Any] = field(default_factory=dict)

    @property
    def root(self) -> Any:
        return self.subject.root

    def cached(self, key: Any, factory: Callable[[], T]) -> T:
        """Compute ``factory()`` once per run and share it between checks.

        Example::

            meshes = ctx.cached("meshes", lambda: list(ctx.host.meshes(ctx.root)))
        """
        if key not in self.cache:
            self.cache[key] = factory()
        return self.cache[key]
