"""Open Blender with the validator panel and a demo asset to try it on.

    blender --python scripts/blender_demo.py

Runs straight from this repo's source, so nothing is installed into your
Blender preferences. The demo chair follows the standard layout and naming, with
a few deliberate problems:

    UnitScale            seat_GEO is scaled                  (can be fixed)
    AllowedObjectTypes   a camera inside the asset
    NamingConvention     backLeg.001 has Blender's number ending
    Ngons                cushion_GEO has ngon caps
    UnappliedModifiers   a Mirror modifier on backrest_GEO   (warning only)

The sidebar opens with the chair selected: click its Validate tab.
"""

import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
# The example studio config loads the example checks and tunes a few settings.
os.environ["PUBLISH_VALIDATOR_CONFIG"] = str(REPO / "examples" / "studio_checks" / "studio.toml")

from publish_validator.hosts import blender as pv_blender  # noqa: E402


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)


def add_empty(name, parent=None, **props):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    for key, value in props.items():
        obj[key] = value
    return obj


def add_cube(name, parent, offset=(0, 0, 0), size=(1, 1, 1)):
    """A box with its size and position baked into the mesh, so its object
    transform stays at zero like a published model's."""
    bpy.ops.mesh.primitive_cube_add(size=1)
    return finish_mesh(name, parent, offset, size)


def finish_mesh(name, parent, offset, size):
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    obj.data.transform(Matrix.Translation(offset) @ Matrix.Diagonal((*size, 1)))
    obj.parent = parent
    return obj


def build_chair():
    root = add_empty("chair_root", pv_task="model", pv_asset_type="prop", pv_asset_name="chair")
    geo = add_empty("geo", root)
    render = add_empty("render", geo)
    proxy = add_empty("proxy", geo)
    add_empty("simproxy", root)

    # UnitScale fails here; the Fix button bakes the scale into the mesh.
    seat = add_cube("seat_GEO", render, offset=(0, 0, 0.5), size=(1, 1, 1))
    seat.scale = (1, 1, 0.1)

    for name, x, y in [
        ("L_frontLeg_GEO", 0.4, 0.4),
        ("R_frontLeg_GEO", -0.4, 0.4),
        ("backLeg.001", 0, -0.4),
    ]:
        add_cube(name, render, offset=(x, y, 0.25), size=(0.08, 0.08, 0.5))

    backrest = add_cube("backrest_GEO", render, offset=(0, -0.45, 0.9), size=(1, 0.08, 0.7))
    backrest.modifiers.new("Mirror", "MIRROR")  # the studio config allows Bevel, not Mirror

    # A cylinder with single-face caps: two ngons.
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.3, depth=0.05, end_fill_type="NGON")
    finish_mesh("cushion_GEO", render, offset=(0, 0, 0.58), size=(1, 1, 1))

    add_cube("seat_PROXY", proxy, offset=(0, 0, 0.45), size=(1, 1, 0.9))

    camera = bpy.data.objects.new("TurntableCam", bpy.data.cameras.new("TurntableCam"))
    bpy.context.scene.collection.objects.link(camera)
    camera.parent = render
    return root


def show_sidebar():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.show_region_ui = True


clear_scene()
root = build_chair()
for obj in bpy.context.view_layer.objects:
    obj.select_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root

pv_blender.register()
show_sidebar()
print("Publish Validator demo ready: click the Validate tab in the sidebar.")
