"""Integration tests that run inside Blender.

    blender -b --factory-startup --python-exit-code 1 --python tests/blender/run.py

Each ``test_*`` function gets a fresh empty scene. Exits non-zero on failure.
"""

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import bpy  # noqa: E402

from publish_validator import Component, Status, Validator, format_text  # noqa: E402
from publish_validator.cli import main as cli_main  # noqa: E402
from publish_validator.hosts import get_host  # noqa: E402
from publish_validator.hosts.blender import BlenderHost  # noqa: E402
from publish_validator.hosts.blender import register as register_ui  # noqa: E402
from publish_validator.hosts.blender import unregister as unregister_ui  # noqa: E402


def empty_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_asset(name="chair", task="model", asset_type="prop"):
    root = bpy.data.objects.new(f"{name}_root", None)
    bpy.context.scene.collection.objects.link(root)
    root["pv_task"] = task
    root["pv_asset_type"] = asset_type
    root["pv_asset_name"] = name
    return root


def add_cube(name, parent, scale=(1, 1, 1), location=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.parent = parent
    obj.scale = scale
    return obj


def select_only(*objects):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0] if objects else None


# -- Tests ------------------------------------------------------------------------


def test_detects_blender_host():
    assert get_host().name == "blender"


def test_validate_and_fix_scale():
    root = make_asset()
    seat = add_cube("seat", root, scale=(2, 1, 1), location=(0, 0, 3))
    leg = add_cube("leg", seat, location=(5, 0, 0))
    bpy.context.view_layer.update()
    leg_world = leg.matrix_world.copy()
    seat_world_verts = [seat.matrix_world @ v.co for v in seat.data.vertices]
    select_only(leg)  # resolver walks up to the root

    validator = Validator(BlenderHost())
    report = validator.run()
    print(format_text(report))
    assert report.subject_name == "chair"
    unit_scale = report.get("transforms.unit_scale")
    assert unit_scale.status is Status.FAILED, unit_scale
    assert unit_scale.issues[0].target_names == ("seat",)
    assert report.get("hierarchy.root_not_empty").status is Status.PASSED
    assert report.get("objects.allowed_object_types").status is Status.PASSED

    validator.select(unit_scale)
    assert BlenderHost().selection() == [seat]

    report = validator.run(fix=True)
    print(format_text(report))
    assert report.get("transforms.unit_scale").status is Status.FIXED
    assert tuple(seat.scale) == (1, 1, 1)
    bpy.context.view_layer.update()
    for before, vert in zip(seat_world_verts, seat.data.vertices, strict=True):
        assert (before - seat.matrix_world @ vert.co).length < 1e-5
    assert (leg.matrix_world.translation - leg_world.translation).length < 1e-5
    assert report.passed


def test_task_filtering_and_disallowed_types():
    root = make_asset(task="lookdev")
    add_cube("body", root, scale=(3, 3, 3))
    light = bpy.data.objects.new("lamp", bpy.data.lights.new("lamp", "POINT"))
    bpy.context.scene.collection.objects.link(light)
    light.parent = root
    select_only(root)

    report = Validator(BlenderHost()).run()
    assert report.get("transforms.unit_scale") is None  # model-only check
    assert report.get("objects.allowed_object_types") is None

    root["pv_task"] = "model"
    report = Validator(BlenderHost()).run()
    allowed = report.get("objects.allowed_object_types")
    assert allowed.status is Status.FAILED
    assert allowed.issues[0].message == "lamp is a light object"


def test_component_selection():
    root = make_asset()
    cube = add_cube("cube", root)
    BlenderHost().select([Component(cube, "face", (0, 2))])
    assert bpy.context.mode == "EDIT_MESH"
    bpy.ops.object.mode_set(mode="OBJECT")
    assert [p.index for p in cube.data.polygons if p.select] == [0, 2]


def test_ui_operators():
    register_ui()
    try:
        root = make_asset()
        add_cube("seat", root, scale=(2, 2, 2))
        select_only(root)
        assert bpy.ops.publish_validator.validate() == {"FINISHED"}
        from publish_validator.hosts.blender.ui import _State

        assert _State.report.get("transforms.unit_scale").status is Status.FAILED
        assert bpy.ops.publish_validator.select(check_id="transforms.unit_scale") == {"FINISHED"}
        assert bpy.ops.publish_validator.validate(fix=True) == {"FINISHED"}
        assert _State.report.passed
        select_only()
        assert bpy.ops.publish_validator.validate() == {"CANCELLED"}
        assert "Select an asset root" in _State.message
    finally:
        unregister_ui()


def test_cli_headless(tmp=None):
    root = make_asset("table")
    add_cube("top", root, scale=(1, 1, 0.1))
    select_only()
    assert cli_main(["--root", "table_root"]) == 1
    assert cli_main(["--all", "--fix"]) == 0
    assert cli_main(["--root", "missing"]) == 2


def test_external_check_folder():
    examples = ROOT / "examples" / "studio_checks"
    root = make_asset()
    add_cube("Seat_px", root)
    select_only(root)
    validator = Validator(BlenderHost(), paths=[examples])
    report = validator.run()
    print(format_text(report))
    assert not report.load_errors, report.load_errors
    assert report.get("studio.geo_naming") is not None


# -- Runner -----------------------------------------------------------------------


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failures = 0
    for name, func in tests:
        empty_scene()
        try:
            func()
            print(f"PASS {name}")
        except Exception:
            failures += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} Blender tests passed")
    if failures:
        sys.exit(1)


main()
