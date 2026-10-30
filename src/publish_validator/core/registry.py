"""The set of known checks, and picking which ones apply."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator

from .check import Check
from .discovery import discover
from .model import LoadError
from .subject import Subject


class Registry:
    """An ordered collection of check classes, keyed by id.

    When two checks share an id the first one wins and the clash is reported
    in :attr:`errors`.
    """

    def __init__(self, checks: Iterable[type[Check]] = (), errors: Iterable[LoadError] = ()):
        self._checks: dict[str, type[Check]] = {}
        self.errors: list[LoadError] = list(errors)
        for check in checks:
            self.add(check)

    @classmethod
    def discover(
        cls,
        paths: Iterable[str | os.PathLike] = (),
        *,
        host: str | None = None,
        **kwargs,
    ) -> Registry:
        """Build a registry from :func:`~publish_validator.core.discovery.discover`."""
        found = discover(paths, host=host, **kwargs)
        return cls(found.checks, found.errors)

    def add(self, check: type[Check]) -> None:
        existing = self._checks.get(check.id)
        if existing is check:
            return
        if existing is not None:
            self.errors.append(
                LoadError(
                    source=_where(check),
                    message=f"duplicate check id {check.id!r}; already defined by "
                    f"{_where(existing)}. Set a unique `id` on one of them.",
                )
            )
            return
        self._checks[check.id] = check

    def get(self, check_id: str) -> type[Check] | None:
        return self._checks.get(check_id)

    def __iter__(self) -> Iterator[type[Check]]:
        return iter(self._checks.values())

    def __len__(self) -> int:
        return len(self._checks)

    def __contains__(self, check_id: object) -> bool:
        return check_id in self._checks

    @property
    def ids(self) -> list[str]:
        return list(self._checks)

    def applicable(self, host: str, subject: Subject) -> list[type[Check]]:
        """Checks relevant to ``subject`` in ``host``, sorted by ``order`` (stable)."""
        matches = [c for c in self._checks.values() if c.applies_to(host, subject)]
        return sorted(matches, key=lambda c: c.order)


def _where(check: type[Check]) -> str:
    return f"{check.__module__}.{check.__qualname__}"
