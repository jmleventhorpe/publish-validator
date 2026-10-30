"""Tests that run inside Blender:

    blender -b --factory-startup --python-exit-code 1 --python tests/blender/run.py

Each test_ function starts from an empty scene. Exits with code 1 if any test fails.
"""

import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import bpy  # noqa: E402

from publish_validator import FAILED, FIXED, PASSED, Component, Validator  # noqa: E402
from publish_validator.cli import main as cli_main  # noqa: E402
from publish_validator.hosts import current_host  # noqa: E402
from publish_validator.hosts.blender import BlenderHost, register, unregister  # noqa: E402
from publish_validator.hosts.blender.ui import state  # noqa: E402


def make_asset(name="chair", task="model", asset_type="prop"):
    root = bpy.data.objects.new(f"{name}_root", None)
    bpy.context.scene.collection.objects.link(root)
    root["pv_task"] = task
    root["pv_asset_type"] = asset_type
    root["pv_asset_name"] = name
    return root


def add_cube(name, parent, scale=(1, 1, 1), location=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=location)
    cube = bpy.context.active_object
    cube.name = name
    cube.parent = parent
    cube.scale = scale
    return cube


def select_only(*objects):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)


def test_finds_the_blender_host():
    assert current_host().name == "blender"


def test_validate_and_fix_scale():
    root = make_asset()
    seat = add_cube("seat", root, scale=(2, 1, 1), location=(0, 0, 3))
    leg = add_cube("leg", seat, location=(5, 0, 0))
    bpy.context.view_layer.update()
    leg_position = leg.matrix_world.translation.copy()
    seat_points = [seat.matrix_world @ vertex.co for vertex in seat.data.vertices]
    select_only(leg)  # selecting a child should still find the asset root

    validator = Validator(BlenderHost())
    report = validator.run()
    print(report.as_text())
    assert report.subject_name == "chair"
    assert report.get("RootNotEmpty").status == PASSED
    assert report.get("AllowedObjectTypes").status == PASSED
    unit_scale = report.get("UnitScale")
    assert unit_scale.status == FAILED
    assert unit_scale.issues[0].target_names == ["seat"]

    validator.select(unit_scale.targets)
    assert BlenderHost().selection() == [seat]

    report = validator.run(fix=True)
    print(report.as_text())
    assert report.get("UnitScale").status == FIXED
    assert report.passed
    assert tuple(seat.scale) == (1, 1, 1)

    # Nothing should have moved in the world.
    bpy.context.view_layer.update()
    for before, vertex in zip(seat_points, seat.data.vertices, strict=True):
        assert (before - seat.matrix_world @ vertex.co).length < 0.00001
    assert (leg.matrix_world.translation - leg_position).length < 0.00001
    assert tuple(leg.scale) == (1, 1, 1)


def test_checks_are_picked_by_task():
    root = make_asset(task="lookdev")
    add_cube("body", root, scale=(3, 3, 3))
    lamp = bpy.data.objects.new("lamp", bpy.data.lights.new("lamp", "POINT"))
    bpy.context.scene.collection.objects.link(lamp)
    lamp.parent = root
    select_only(root)

    report = Validator(BlenderHost()).run()
    assert report.get("UnitScale") is None  # model-only checks
    assert report.get("AllowedObjectTypes") is None

    root["pv_task"] = "model"
    report = Validator(BlenderHost()).run()
    allowed = report.get("AllowedObjectTypes")
    assert allowed.status == FAILED
    assert allowed.issues[0].message == "lamp is a light object"


def test_selecting_faces():
    root = make_asset()
    cube = add_cube("cube", root)
    BlenderHost().select([Component(cube, "face", [0, 2])])
    assert bpy.context.mode == "EDIT_MESH"
    bpy.ops.object.mode_set(mode="OBJECT")
    assert [face.index for face in cube.data.polygons if face.select] == [0, 2]


def test_panel_buttons():
    register()
    try:
        root = make_asset()
        add_cube("seat", root, scale=(2, 2, 2))
        select_only(root)
        assert bpy.ops.publish_validator.validate() == {"FINISHED"}
        assert state.report.get("UnitScale").status == FAILED
        assert bpy.ops.publish_validator.select(check_id="UnitScale") == {"FINISHED"}
        assert bpy.ops.publish_validator.validate(fix=True) == {"FINISHED"}
        assert state.report.passed

        select_only()
        assert bpy.ops.publish_validator.validate() == {"CANCELLED"}
        assert "Select an asset root" in state.message
    finally:
        unregister()


def test_command_line():
    root = make_asset("table")
    add_cube("top", root, scale=(1, 1, 0.1))
    select_only()
    assert cli_main(["--root", "table_root"]) == 1
    assert cli_main(["--all", "--fix"]) == 0
    assert cli_main(["--root", "missing"]) == 2
    assert cli_main([]) == 2  # nothing selected: tells you to use --root or --all


def test_studio_check_folder():
    root = make_asset()
    add_cube("Seat_px", root)
    select_only(root)
    validator = Validator(BlenderHost(), check_paths=[REPO / "examples" / "studio_checks"])
    report = validator.run()
    print(report.as_text())
    assert validator.load_errors == []
    assert report.get("GeoNaming").status == PASSED
    assert report.get("UnappliedModifiers").status == PASSED


def main():
    tests = [(name, func) for name, func in globals().items() if name.startswith("test_")]
    failed = 0
    for name, test in tests:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        try:
            test()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()

    print(f"\n{len(tests) - failed}/{len(tests)} Blender tests passed")
    if failed:
        sys.exit(1)


main()
