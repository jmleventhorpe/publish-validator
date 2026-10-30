"""Blender support: the host adapter and the sidebar panel (View3D > N > Validate)."""

from .host import BlenderHost


def register():
    from . import ui

    ui.register()


def unregister():
    from . import ui

    ui.unregister()
