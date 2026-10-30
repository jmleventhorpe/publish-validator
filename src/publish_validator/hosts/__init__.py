"""Host adapters. Each subpackage imports its application's API, so import
only the one you need, or use :func:`current_host` to pick automatically."""

from __future__ import annotations

import importlib.util

from ..core.host import Host

#: host name -> (module that proves we are inside it, "module:Class" of the adapter)
HOSTS = {
    "blender": ("bpy", "publish_validator.hosts.blender.host:BlenderHost"),
    "maya": ("maya.cmds", "publish_validator.hosts.maya.host:MayaHost"),
    "houdini": ("hou", "publish_validator.hosts.houdini.host:HoudiniHost"),
}


def available_hosts() -> list[str]:
    """Hosts whose application module can be imported in this interpreter."""
    found = []
    for name, (probe, _) in HOSTS.items():
        try:
            if importlib.util.find_spec(probe) is not None:
                found.append(name)
        except ModuleNotFoundError:  # parent package missing, e.g. "maya" for "maya.cmds"
            continue
    return found


def get_host(name: str = "auto") -> Host:
    """Create a host adapter by name, or detect the running application."""
    from ..core.validator import import_string

    if name == "auto":
        available = available_hosts()
        if not available:
            raise RuntimeError(
                "No supported application detected (Blender, Maya or Houdini). "
                "Run inside a host, e.g. `blender -b file.blend --python-expr ...`."
            )
        name = available[0]
    if name not in HOSTS:
        raise ValueError(f"unknown host {name!r}; known hosts: {', '.join(HOSTS)}")
    return import_string(HOSTS[name][1])()


def current_host() -> Host:
    return get_host("auto")
