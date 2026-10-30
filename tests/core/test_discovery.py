import textwrap

from publish_validator.core.discovery import ENV_PATH, discover
from publish_validator.core.registry import Registry

CHECK = """
from publish_validator import Check

class {name}(Check):
    {extra}
    def validate(self, ctx):
        return []
"""


def write(path, name, extra=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(CHECK.format(name=name, extra=extra)))


def ids(found):
    return sorted(c.id for c in found.checks)


def test_folder_discovery_rules(tmp_path):
    write(tmp_path / "naming.py", "GeoNaming")
    write(tmp_path / "sub" / "deep.py", "Deep")
    write(tmp_path / "_helpers.py", "Hidden")
    write(tmp_path / "_private" / "inside.py", "AlsoHidden")
    write(tmp_path / "blender" / "only_blender.py", "BlenderOnly")
    write(tmp_path / "maya" / "only_maya.py", "MayaOnly")

    found = discover([tmp_path], host="blender", builtins=False, entry_points=False, use_env=False)
    assert ids(found) == ["deep.deep", "naming.geo_naming", "only_blender.blender_only"]
    assert found.errors == []


def test_imported_checks_are_not_collected_twice(tmp_path):
    write(tmp_path / "base.py", "Base", extra="abstract = True")
    (tmp_path / "child.py").write_text(
        "from publish_validator import Check\n"
        "class Child(Check):\n"
        "    def validate(self, ctx):\n"
        "        return []\n"
        "Alias = Child\n"
    )
    found = discover([tmp_path], builtins=False, entry_points=False, use_env=False)
    assert ids(found) == ["child.child"]


def test_broken_file_is_reported_and_others_still_load(tmp_path):
    write(tmp_path / "good.py", "Good")
    (tmp_path / "bad.py").write_text("raise ValueError('oops')\n")
    (tmp_path / "needs_bpy.py").write_text("import bpy\n")

    found = discover([tmp_path], builtins=False, entry_points=False, use_env=False)
    assert ids(found) == ["good.good"]
    assert len(found.errors) == 1
    assert "bad.py" in found.errors[0].source
    assert "ValueError: oops" in found.errors[0].message


def test_missing_path_is_reported(tmp_path):
    found = discover([tmp_path / "nope"], builtins=False, entry_points=False, use_env=False)
    assert found.errors and "does not exist" in found.errors[0].message


def test_env_path(tmp_path, monkeypatch):
    write(tmp_path / "from_env.py", "FromEnv")
    monkeypatch.setenv(ENV_PATH, str(tmp_path))
    found = discover(builtins=False, entry_points=False)
    assert ids(found) == ["from_env.from_env"]


def test_builtins_respect_host_folders():
    everything = ids(discover(entry_points=False, use_env=False))
    assert "hierarchy.root_not_empty" in everything
    assert "transforms.unit_scale" in everything
    in_maya = ids(discover(host="maya", entry_points=False, use_env=False))
    assert "hierarchy.root_not_empty" in in_maya
    assert "transforms.unit_scale" not in in_maya


def test_duplicate_ids_are_reported(tmp_path):
    write(tmp_path / "a" / "same.py", "Thing")
    write(tmp_path / "b" / "same.py", "Thing")
    registry = Registry.discover([tmp_path], builtins=False, entry_points=False, use_env=False)
    assert registry.ids == ["same.thing"]
    assert len(registry.errors) == 1
    assert "duplicate check id 'same.thing'" in registry.errors[0].message


def test_files_are_re_executed_on_each_discovery(tmp_path):
    path = tmp_path / "live.py"
    write(path, "Before")
    assert ids(discover([tmp_path], builtins=False, entry_points=False, use_env=False)) == [
        "live.before"
    ]
    write(path, "After")
    assert ids(discover([tmp_path], builtins=False, entry_points=False, use_env=False)) == [
        "live.after"
    ]
