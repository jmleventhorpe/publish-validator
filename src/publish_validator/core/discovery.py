"""Finding checks.

Checks are loaded from three places, in this order:

1. Built-ins shipped in ``publish_validator.checks``.
2. Installed packages exposing the entry-point group ``publish_validator.checks``
   (the entry point may name a module, a Check class, or a function returning
   Check classes).
3. Folders: ``check_paths`` from config, then ``$PUBLISH_VALIDATOR_PATH``
   (``os.pathsep``-separated). Every ``*.py`` file inside is loaded, recursively.
   Files and folders starting with ``_`` or ``.`` are ignored, so shared helpers
   can live alongside checks.

Folders named after *another* host (``maya/`` while running in Blender, etc.)
are skipped, and so is any module that fails only because a host module like
``bpy`` or ``maya`` is unavailable. A file that fails for any other reason is
reported as a :class:`LoadError`; it never stops the others from loading.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import logging
import os
import pkgutil
import sys
import traceback
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from .check import Check
from .model import LoadError

log = logging.getLogger(__name__)

ENV_PATH = "PUBLISH_VALIDATOR_PATH"
ENTRY_POINT_GROUP = "publish_validator.checks"
BUILTIN_PACKAGE = "publish_validator.checks"
PLUGIN_MODULE_PREFIX = "publish_validator_plugins"

#: Folder names treated as host-specific.
KNOWN_HOSTS = frozenset(
    {"blender", "maya", "houdini", "nuke", "max", "unreal", "katana", "mari", "gaffer", "c4d"}
)

#: Top-level modules that only exist inside a particular application.
HOST_MODULES = frozenset(
    {"bpy", "bmesh", "mathutils", "bpy_extras", "maya", "pymel", "hou", "nuke", "pymxs", "unreal"}
)


@dataclass(slots=True)
class Discovery:
    checks: list[type[Check]] = field(default_factory=list)
    errors: list[LoadError] = field(default_factory=list)

    def extend(self, other: Discovery) -> None:
        self.checks += other.checks
        self.errors += other.errors


def discover(
    paths: Iterable[str | os.PathLike] = (),
    *,
    host: str | None = None,
    builtins: bool = True,
    entry_points: bool = True,
    use_env: bool = True,
    reload: bool = False,
) -> Discovery:
    """Load every available check class.

    Args:
        paths: Extra folders (or single ``.py`` files) to load.
        host: Current host name; folders named after other hosts are skipped.
            None loads everything.
        reload: Re-import built-in and entry-point modules (folder files are
            always re-executed), for iterating on checks without restarting.
    """
    found = Discovery()
    if builtins:
        found.extend(_discover_package(BUILTIN_PACKAGE, host=host, reload=reload))
    if entry_points:
        found.extend(_discover_entry_points(reload=reload))
    all_paths = [Path(p) for p in paths]
    if use_env:
        all_paths += [Path(p) for p in os.environ.get(ENV_PATH, "").split(os.pathsep) if p]
    seen: set[Path] = set()
    for path in all_paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        found.extend(_discover_path(resolved, host=host))
    return found


def checks_in_module(module: ModuleType) -> list[type[Check]]:
    """Concrete Check classes *defined* in ``module`` (imports and aliases are ignored)."""
    found: list[type[Check]] = []
    for obj in vars(module).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, Check)
            and not obj.is_abstract()
            and obj.__module__ == module.__name__
            and obj not in found
        ):
            found.append(obj)
    return found


def load_file(path: Path) -> ModuleType:
    """Execute a check file as a fresh module."""
    digest = hashlib.sha1(str(path.parent).encode()).hexdigest()[:8]
    name = f"{PLUGIN_MODULE_PREFIX}.d{digest}.{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


# -- Internals -------------------------------------------------------------------


def _discover_package(package_name: str, *, host: str | None, reload: bool) -> Discovery:
    found = Discovery()
    try:
        package = importlib.import_module(package_name)
    except Exception as exc:
        found.errors.append(_load_error(package_name, exc))
        return found
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
        parts = info.name.split(".")[len(package_name.split(".")) :]
        if any(p.startswith("_") for p in parts) or _other_host(parts[:-1], host):
            continue
        if info.ispkg and _other_host(parts, host):
            continue
        found.extend(_import_module(info.name, reload=reload))
    return found


def _import_module(name: str, *, reload: bool) -> Discovery:
    found = Discovery()
    try:
        module = importlib.import_module(name)
        if reload:
            module = importlib.reload(module)
    except Exception as exc:
        if not _missing_host_module(exc):
            found.errors.append(_load_error(name, exc))
        return found
    found.checks += checks_in_module(module)
    return found


def _discover_entry_points(*, reload: bool) -> Discovery:
    found = Discovery()
    for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        source = f"entry point {ep.name} ({ep.value})"
        try:
            obj: Any = ep.load()
            if reload and isinstance(obj, ModuleType):
                obj = importlib.reload(obj)
            if isinstance(obj, ModuleType):
                found.checks += checks_in_module(obj)
            elif isinstance(obj, type) and issubclass(obj, Check):
                found.checks.append(obj)
            elif callable(obj):
                found.checks += list(obj())
            else:
                raise TypeError("must point at a module, a Check class or a function")
        except Exception as exc:
            if not _missing_host_module(exc):
                found.errors.append(_load_error(source, exc))
    return found


def _discover_path(path: Path, *, host: str | None) -> Discovery:
    found = Discovery()
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(
            f
            for f in path.rglob("*.py")
            if not any(p.startswith(("_", ".")) for p in f.relative_to(path).parts)
            and not _other_host(f.relative_to(path).parts[:-1], host)
        )
    else:
        found.errors.append(LoadError(str(path), "check path does not exist"))
        return found

    for file in files:
        try:
            module = load_file(file)
        except Exception as exc:
            if not _missing_host_module(exc):
                found.errors.append(_load_error(str(file), exc))
            continue
        found.checks += checks_in_module(module)
    return found


def _other_host(folder_parts: Iterable[str], host: str | None) -> bool:
    if host is None:
        return False
    return any(part in KNOWN_HOSTS and part != host for part in folder_parts)


def _missing_host_module(exc: BaseException) -> bool:
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        missing = exc.name.split(".")[0] in HOST_MODULES
        if missing:
            log.debug("skipping module that needs %s", exc.name)
        return missing
    return False


def _load_error(source: str, exc: BaseException) -> LoadError:
    return LoadError(
        source=source,
        message=f"{type(exc).__name__}: {exc}",
        traceback="".join(traceback.format_exception(exc)),
    )
