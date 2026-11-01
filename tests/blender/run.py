"""Tests that run inside Blender:

    blender -b --factory-startup --python-exit-code 1 --python tests/blender/run.py

Each test_ function starts from an empty scene. Exits with code 1 if any test fails.
"""

import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402

from publish_validator import (  # noqa: E402
    FAILED,
    FIXED,
    PASSED,
    SKIPPED,
    WARNING,
    Component,
    Validator,
)
from publish_validator.cli import main as cli_main  # noqa: E402
from publish_validator.hosts import current_host  # noqa: E402
from publish_validator.hosts.blender import BlenderHost, register, unregister  # noqa: E402
from publish_validator.hosts.blender.ui import state  # noqa: E402


def add_empty(name, parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    return obj


def make_asset(name="chair", task="model", asset_type="prop"):
    """An asset with the standard groups and nothing in them yet."""
    root = add_empty(f"{name}_root")
    root["pv_task"] = task
    root["pv_asset_type"] = asset_type
    root["pv_asset_name"] = name
    geo = add_empty("geo", root)
    asset = SimpleNamespace(root=root, geo=geo)
    asset.render = add_empty("render", geo)
    asset.proxy = add_empty("proxy", geo)
    asset.simproxy = add_empty("simproxy", root)
    return asset


def add_cube(name, parent, scale=(1, 1, 1), offset=(0, 0, 0)):
    """A cube with its position baked into the mesh, so the object sits at zero."""
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    cube.name = name
    cube.data.name = name
    cube.data.transform(Matrix.Translation(offset))
    cube.parent = parent
    cube.scale = scale
    return cube


def add_mesh(name, parent, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    return obj


def add_lamp(parent):
    lamp = bpy.data.objects.new("lamp", bpy.data.lights.new("lamp", "POINT"))
    bpy.context.scene.collection.objects.link(lamp)
    lamp.parent = parent
    return lamp


def select_only(*objects):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)


def messages(report, check_id):
    return [issue.message for issue in report.get(check_id).issues]


def test_finds_the_blender_host():
    assert current_host().name == "blender"


def test_a_clean_asset_passes_every_check():
    asset = make_asset()
    add_cube("seat", asset.render)
    add_cube("seat_proxy", asset.proxy)
    select_only(asset.root)
    report = Validator(BlenderHost()).run()
    print(report.as_text())
    assert report.passed
    assert {result.status for result in report.results} == {PASSED}


def test_each_check_finds_its_problem():
    asset = make_asset()
    render = asset.render
    add_cube("good", render)
    add_cube("bad.001", render)
    add_cube("wrong", asset.proxy)  # proxies end in _proxy
    add_cube("stray_proxy", render)  # a proxy outside the proxy group
    add_empty("junk", asset.root)

    renamed = add_cube("renamed", render)
    renamed.data.name = "Cube"

    parent = add_cube("parent", render)
    add_cube("child", parent)

    moved = add_cube("moved", render)
    moved.location = (1, 0, 0)

    animated = add_cube("animated", render)
    animated.keyframe_insert("location", frame=1)

    bpy.ops.mesh.primitive_cylinder_add(vertices=8, end_fill_type="NGON")
    bpy.context.active_object.name = "ngon"
    bpy.context.active_object.data.name = "ngon"
    bpy.context.active_object.parent = render

    add_mesh("flat", render, [(0, 0, 0), (1, 0, 0), (2, 0, 0)], [(0, 1, 2)])
    add_mesh(
        "stacked",
        render,
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        [(0, 1, 2, 3), (0, 1, 2, 3)],
    )
    add_mesh(
        "doubled",
        render,
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 0), (1, 0, 0), (0, -1, 0)],
        [(0, 1, 2), (3, 5, 4)],
    )
    add_mesh(
        "fin",
        render,
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)],
        [(0, 1, 2), (0, 1, 3), (0, 1, 4)],
    )
    select_only(asset.root)

    report = Validator(BlenderHost()).run()
    print(report.as_text())

    assert "'junk' shouldn't be directly under the asset root" in messages(report, "GroupSetup")
    naming = messages(report, "NamingConvention")
    assert "bad.001 has Blender's automatic number ending" in naming
    assert "wrong should end in _proxy" in naming
    assert "stray_proxy is named as a proxy but isn't under 'proxy'" in naming
    assert messages(report, "MeshDataNames") == ["renamed uses mesh data called Cube"]
    assert messages(report, "GeoChildren") == ["parent has meshes under it: child"]
    assert messages(report, "ZeroTransforms") == ["moved is moved 1, 0, 0"]
    assert messages(report, "HasAnimation") == ["animated has keyframes"]
    assert messages(report, "Ngons") == ["ngon has 2 ngons"]
    assert messages(report, "ZeroAreaFaces") == ["flat has 1 faces with no area"]
    assert messages(report, "LaminaFaces") == ["stacked has 1 pairs of lamina faces"]
    assert messages(report, "DoubleVerts") == ["doubled has 4 overlapping vertices"]  # 2 pairs
    assert messages(report, "NonManifold") == ["fin has 1 non-manifold edges"]
    assert report.get("MeshHoles").status == WARNING
    assert any(m.startswith("flat has") for m in messages(report, "MeshHoles"))

    # Geometry problems point at the exact elements.
    ngons = report.get("Ngons").issues[0].targets[0]
    assert isinstance(ngons, Component) and ngons.kind == "face" and len(ngons.indices) == 2


def test_validate_and_fix_scale():
    asset = make_asset()
    seat = add_cube("seat", asset.render, scale=(2, 1, 1), offset=(0, 0, 3))
    legs = add_empty("legs", seat)
    leg = add_cube("leg", legs, offset=(5, 0, 0))
    bpy.context.view_layer.update()
    leg_points = [leg.matrix_world @ vertex.co for vertex in leg.data.vertices]
    seat_points = [seat.matrix_world @ vertex.co for vertex in seat.data.vertices]
    select_only(leg)  # selecting a child should still find the asset root

    validator = Validator(BlenderHost())
    report = validator.run()
    print(report.as_text())
    assert report.subject_name == "chair"
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
    for before, vertex in zip(leg_points, leg.data.vertices, strict=True):
        assert (before - leg.matrix_world @ vertex.co).length < 0.00001


def test_checks_are_picked_by_task():
    asset = make_asset(task="lookdev")
    add_cube("body", asset.render, scale=(3, 3, 3))
    add_lamp(asset.render)
    select_only(asset.root)

    report = Validator(BlenderHost()).run()
    assert report.get("UnitScale") is None  # model-only checks
    assert report.get("AllowedObjectTypes") is None

    asset.root["pv_task"] = "model"
    report = Validator(BlenderHost()).run()
    assert messages(report, "AllowedObjectTypes") == ["lamp is a light object"]


def test_selecting_faces():
    asset = make_asset()
    cube = add_cube("cube", asset.render)
    BlenderHost().select([Component(cube, "face", [0, 2])])
    assert bpy.context.mode == "EDIT_MESH"
    bpy.ops.object.mode_set(mode="OBJECT")
    assert [face.index for face in cube.data.polygons if face.select] == [0, 2]


def test_panel_buttons():
    register()
    try:
        asset = make_asset()
        add_cube("seat", asset.render, scale=(2, 2, 2))
        select_only(asset.root)
        assert bpy.ops.publish_validator.validate() == {"FINISHED"}
        assert state.report.get("UnitScale").status == FAILED
        assert bpy.ops.publish_validator.select(check_id="UnitScale") == {"FINISHED"}
        assert bpy.ops.publish_validator.validate(fix=True) == {"FINISHED"}
        assert state.report.passed

        select_only()
        assert bpy.ops.publish_validator.validate() == {"CANCELLED"}
    finally:
        unregister()


def test_panel_checkboxes_fix_one_and_stale():
    register()
    try:
        asset = make_asset()
        seat = add_cube("seat", asset.render, scale=(2, 2, 2))
        lamp = add_lamp(asset.render)
        select_only(asset.root)

        # Untick all, then tick all, from the buttons above the list.
        bpy.ops.publish_validator.tick_all(tick=False)
        bpy.ops.publish_validator.validate()
        assert {r.status for r in state.report.results} == {SKIPPED}
        bpy.ops.publish_validator.tick_all(tick=True)
        assert not state.unticked

        # Unticked checks are skipped, and don't block publishing.
        bpy.ops.publish_validator.toggle_check(check_id="UnitScale")
        bpy.ops.publish_validator.toggle_check(check_id="AllowedObjectTypes")
        assert bpy.ops.publish_validator.validate() == {"FINISHED"}
        assert state.report.get("UnitScale").status == SKIPPED
        assert state.report.passed

        # Tick them again: both fail.
        bpy.ops.publish_validator.toggle_check(check_id="UnitScale")
        bpy.ops.publish_validator.toggle_check(check_id="AllowedObjectTypes")
        bpy.ops.publish_validator.validate()
        assert state.report.get("UnitScale").status == FAILED
        assert state.report.get("AllowedObjectTypes").status == FAILED

        # Fixing one check leaves the other result alone.
        assert bpy.ops.publish_validator.fix_one(check_id="UnitScale") == {"FINISHED"}
        assert state.report.get("UnitScale").status == FIXED
        assert state.report.get("AllowedObjectTypes").status == FAILED
        assert tuple(seat.scale) == (1, 1, 1)
        assert not state.stale  # our own fix doesn't count as a change

        # Select picks what that check found.
        bpy.ops.publish_validator.select(check_id="AllowedObjectTypes")
        assert BlenderHost().selection() == [lamp]

        # Selecting doesn't make results out of date; moving something does.
        select_only(asset.root)
        bpy.context.view_layer.update()
        assert not state.stale
        seat.location.x += 1
        bpy.context.view_layer.update()
        assert state.stale
        bpy.ops.publish_validator.validate()
        assert not state.stale
    finally:
        unregister()


def test_command_line():
    asset = make_asset("table")
    add_cube("top", asset.render, scale=(1, 1, 0.1))
    select_only()
    assert cli_main(["--root", "table_root"]) == 1
    assert cli_main(["--all", "--fix"]) == 0
    assert cli_main(["--root", "missing"]) == 2
    assert cli_main([]) == 2  # nothing selected: tells you to use --root or --all


def test_studio_check_folder():
    asset = make_asset()
    add_cube("seat", asset.render)
    select_only(asset.root)
    validator = Validator(BlenderHost(), check_paths=[REPO / "examples" / "studio_checks"])
    report = validator.run()
    print(report.as_text())
    assert validator.load_errors == []
    assert report.get("PolyBudget").status == PASSED


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
