"""Blender integration: the host adapter plus a minimal sidebar UI.

From a script or the Python console::

    from publish_validator.hosts.blender import BlenderHost
    from publish_validator import Validator, format_text

    print(format_text(Validator(BlenderHost()).run()))
"""

from .host import BlenderHost


def register() -> None:
    from . import ui

    ui.register()


def unregister() -> None:
    from . import ui

    ui.unregister()


__all__ = ["BlenderHost", "register", "unregister"]
