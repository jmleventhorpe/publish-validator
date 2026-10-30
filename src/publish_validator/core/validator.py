"""High-level entry point tying host, resolver, registry and config together.

This is what UIs, the CLI and publish hooks use::

    validator = Validator(BlenderHost())
    report = validator.run()            # validates the selected asset
    if not report.passed: ...
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterable
from typing import Any

from .check import Check
from .config import Config, ConfigError, load_config
from .host import Host
from .model import CheckResult, Issue, LoadError, Report
from .registry import Registry
from .runner import Observer, run
from .subject import PropertyResolver, Subject, SubjectResolver


class Validator:
    """Validation for one host, with config, checks and resolver loaded once.

    Args:
        host: The application adapter.
        config: Overrides; defaults to :func:`load_config` (``$PUBLISH_VALIDATOR_CONFIG``).
        registry: Checks to use; defaults to discovering them.
        resolver: Subject resolver; defaults to config ``resolver`` or
            :class:`PropertyResolver`.
        paths: Extra check folders on top of config and environment.
    """

    def __init__(
        self,
        host: Host,
        *,
        config: Config | None = None,
        registry: Registry | None = None,
        resolver: SubjectResolver | None = None,
        paths: Iterable[str | os.PathLike] = (),
    ) -> None:
        self.host = host
        self._config_errors: list[LoadError] = []
        if config is None:
            try:
                config = load_config()
            except ConfigError as exc:
                self._config_errors.append(LoadError("config", str(exc)))
                config = Config()
        self.config = config
        self._paths = [*config.check_paths, *paths]
        self.registry = registry if registry is not None else self._discover()
        self.resolver = resolver or self._make_resolver()

    # -- Queries ------------------------------------------------------------------

    @property
    def load_errors(self) -> list[LoadError]:
        unknown = [
            LoadError("config", f"config refers to unknown check id {check_id!r}")
            for check_id in self.config.unknown_ids(self.registry.ids)
        ]
        return [*self._config_errors, *self.registry.errors, *unknown]

    def resolve(self, node: Any | None = None) -> Subject:
        """The subject for ``node``, or for the current selection. Raises ResolveError."""
        return self.resolver.resolve(self.host, node)

    def checks_for(self, subject: Subject) -> list[type[Check]]:
        return self.registry.applicable(self.host.name, subject)

    # -- Actions ------------------------------------------------------------------

    def run(
        self,
        subject: Subject | None = None,
        *,
        fix: bool = False,
        only: Iterable[str] | None = None,
        observer: Observer | None = None,
    ) -> Report:
        """Validate ``subject`` (default: resolved from the selection)."""
        subject = subject or self.resolve()
        return run(
            subject,
            self.host,
            self.checks_for(subject),
            config=self.config,
            fix=fix,
            only=only,
            observer=observer,
            load_errors=self.load_errors,
        )

    def run_all(self, *, fix: bool = False, only: Iterable[str] | None = None) -> list[Report]:
        """Validate every subject in the scene (headless / batch use)."""
        return [self.run(s, fix=fix, only=only) for s in self.resolver.find_all(self.host)]

    def select(self, item: CheckResult | Issue) -> None:
        """Select the targets of a result or a single issue in the host."""
        self.host.select(item.targets)

    def reload(self) -> None:
        """Re-import all checks (for iterating on checks without restarting)."""
        self.registry = self._discover(reload=True)

    # -- Internals ----------------------------------------------------------------

    def _discover(self, reload: bool = False) -> Registry:
        return Registry.discover(self._paths, host=self.host.name, reload=reload)

    def _make_resolver(self) -> SubjectResolver:
        if self.config.resolver:
            try:
                return import_string(self.config.resolver)()
            except Exception as exc:
                self._config_errors.append(
                    LoadError("config", f"cannot load resolver {self.config.resolver!r}: {exc}")
                )
        return PropertyResolver()


def import_string(path: str) -> Any:
    """Import ``"package.module:attribute"``."""
    module_name, _, attribute = path.partition(":")
    obj: Any = importlib.import_module(module_name)
    for part in attribute.split("."):
        obj = getattr(obj, part)
    return obj
