"""The coloured status icons (green, orange, red) shown in the panel.

The images live in the icons/ folder next to this file and are made by
scripts/make_icons.py. If they can't be loaded, Blender's own icons are used.
"""

from pathlib import Path

import bpy.utils.previews

ICON_FOLDER = Path(__file__).parent / "icons"

# Built-in icons to use if the images are missing.
FALLBACK = {
    "passed": "CHECKMARK",
    "fixed": "CHECKMARK",
    "warning": "ERROR",
    "failed": "CANCEL",
    "errored": "QUESTION",
    "skipped": "REMOVE",
    "not_run": "RADIOBUT_OFF",
}

previews = None


def register():
    global previews
    previews = bpy.utils.previews.new()
    for image in ICON_FOLDER.glob("*.png"):
        previews.load(image.stem, str(image), "IMAGE")


def unregister():
    global previews
    if previews is not None:
        bpy.utils.previews.remove(previews)
    previews = None


def status_icon(status):
    """Keyword arguments for layout.label() or layout.operator(), e.g. **status_icon("failed")."""
    if previews is not None and status in previews and previews[status].icon_id:
        return {"icon_value": previews[status].icon_id}
    return {"icon": FALLBACK.get(status, "DOT")}
