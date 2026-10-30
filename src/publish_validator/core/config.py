"""Layered TOML configuration.

Studios change behaviour here instead of editing checks. Files are merged in
order, later files winning, so a typical chain is studio -> project -> user::

    PUBLISH_VALIDATOR_CONFIG=/studio/pv.toml:/projects/foo/pv.toml

Example file::

    # Extra folders to load checks from (relative to this file).
    check_paths = ["checks"]

    # "module:Class" of a custom subject resolver.
    resolver = "my_pipeline.validator:PipelineResolver"

    [checks."transforms.unit_scale"]
    severity = "warning"
    settings = { tolerance = 0.001 }

    [checks."blender_*"]          # glob patterns work; exact ids win over patterns
    enabled = false
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from .model import Severity

ENV_CONFIG = "PUBLISH_VALIDATOR_CONFIG"

_TOP_LEVEL_KEYS = {"check_paths", "resolver", "checks"}
_CHECK_KEYS = {"enabled", "severity", "settings"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CheckConfig:
    """Overrides for one check id (or glob pattern)."""

    enabled: bool | None = None
    severity: Severity | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)

    def merged(self, other: CheckConfig) -> CheckConfig:
        return CheckConfig(
            enabled=other.enabled if other.enabled is not None else self.enabled,
            severity=other.severity if other.severity is not None else self.severity,
            settings={**self.settings, **other.settings},
        )


@dataclass(frozen=True, slots=True)
class Config:
    checks: Mapping[str, CheckConfig] = field(default_factory=dict)
    check_paths: tuple[Path, ...] = ()
    resolver: str | None = None
    sources: tuple[str, ...] = ()

    def merged(self, other: Config) -> Config:
        checks = dict(self.checks)
        for key, value in other.checks.items():
            checks[key] = checks[key].merged(value) if key in checks else value
        paths = [*self.check_paths, *(p for p in other.check_paths if p not in self.check_paths)]
        return Config(
            checks=checks,
            check_paths=tuple(paths),
            resolver=other.resolver or self.resolver,
            sources=(*self.sources, *other.sources),
        )

    def for_check(self, check_id: str) -> CheckConfig:
        """Effective overrides for ``check_id``: matching patterns first, then the exact id."""
        result = CheckConfig()
        for key, value in self.checks.items():
            if key != check_id and _is_pattern(key) and fnmatchcase(check_id, key):
                result = result.merged(value)
        if check_id in self.checks:
            result = result.merged(self.checks[check_id])
        return result

    def unknown_ids(self, known: Iterable[str]) -> list[str]:
        """Exact ids in config that match no known check (likely typos)."""
        known = set(known)
        return [k for k in self.checks if not _is_pattern(k) and k not in known]


def load_config(
    paths: Iterable[str | os.PathLike] | None = None, *, use_env: bool = True
) -> Config:
    """Load and merge config files: ``$PUBLISH_VALIDATOR_CONFIG`` first, then ``paths``."""
    files: list[Path] = []
    if use_env:
        files += [Path(p) for p in os.environ.get(ENV_CONFIG, "").split(os.pathsep) if p]
    files += [Path(p) for p in paths or ()]
    config = Config()
    for path in files:
        config = config.merged(read_config(path))
    return config


def read_config(path: str | os.PathLike) -> Config:
    path = Path(path)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return parse_config(data, source=str(path), base_dir=path.parent)


def parse_config(
    data: Mapping[str, Any], source: str = "<config>", base_dir: Path | None = None
) -> Config:
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(
            f"{source}: unknown key(s) {sorted(unknown)}; expected {sorted(_TOP_LEVEL_KEYS)}"
        )

    base_dir = base_dir or Path.cwd()
    paths = data.get("check_paths", [])
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ConfigError(f"{source}: check_paths must be a list of strings")
    check_paths = tuple(
        (base_dir / os.path.expandvars(os.path.expanduser(p))).resolve() for p in paths
    )

    resolver = data.get("resolver")
    if resolver is not None and (not isinstance(resolver, str) or ":" not in resolver):
        raise ConfigError(f"{source}: resolver must be a 'module:Class' string")

    checks: dict[str, CheckConfig] = {}
    for check_id, entry in data.get("checks", {}).items():
        where = f"{source}: [checks.{check_id!r}]"
        if not isinstance(entry, Mapping):
            raise ConfigError(f"{where} must be a table")
        bad = set(entry) - _CHECK_KEYS
        if bad:
            raise ConfigError(
                f"{where}: unknown key(s) {sorted(bad)}; expected {sorted(_CHECK_KEYS)}"
            )
        enabled = entry.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise ConfigError(f"{where}: enabled must be true or false")
        severity = entry.get("severity")
        if severity is not None:
            try:
                severity = Severity(severity)
            except ValueError:
                options = ", ".join(s.value for s in Severity)
                raise ConfigError(f"{where}: severity must be one of {options}") from None
        settings = entry.get("settings", {})
        if not isinstance(settings, Mapping):
            raise ConfigError(f"{where}: settings must be a table")
        checks[check_id] = CheckConfig(enabled=enabled, severity=severity, settings=dict(settings))

    return Config(checks=checks, check_paths=check_paths, resolver=resolver, sources=(source,))


def _is_pattern(key: str) -> bool:
    return any(c in key for c in "*?[")
