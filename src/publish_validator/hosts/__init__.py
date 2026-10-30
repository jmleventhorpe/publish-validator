"""One adapter per application. Each imports its application's Python API, so
import only the one you need, or let current_host() pick."""


def current_host():
    """The host adapter for the application this code is running in."""
    try:
        import bpy
    except ImportError:
        pass
    else:
        from .blender import BlenderHost

        return BlenderHost()

    try:
        import maya.cmds
    except ImportError:
        pass
    else:
        from .maya import MayaHost

        return MayaHost()

    try:
        import hou
    except ImportError:
        pass
    else:
        from .houdini import HoudiniHost

        return HoudiniHost()

    raise RuntimeError("Not running inside Blender, Maya or Houdini.")
