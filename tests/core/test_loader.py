from publish_validator.core.loader import CHECK_PATH_ENV, load_checks

CHECK_FILE = """
from publish_validator import Check

class {name}(Check):
    def validate(self, ctx):
        return []
"""


def write_check(path, name):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CHECK_FILE.format(name=name))


def names(checks):
    return sorted(check.__name__ for check in checks)


def test_builtin_checks_respect_host_folders():
    everywhere, _ = load_checks()
    in_maya, _ = load_checks(host_name="maya")
    assert "UnitScale" in names(everywhere)
    assert "UnitScale" not in names(in_maya)
    assert "RootNotEmpty" in names(in_maya)


def test_folder_rules(tmp_path):
    write_check(tmp_path / "naming.py", "GeoNaming")
    write_check(tmp_path / "sub" / "deep.py", "Deep")
    write_check(tmp_path / "_helpers.py", "Hidden")
    write_check(tmp_path / "blender" / "only_blender.py", "BlenderOnly")
    write_check(tmp_path / "maya" / "only_maya.py", "MayaOnly")

    checks, errors = load_checks([tmp_path], host_name="blender")
    found = names(checks)
    assert {"GeoNaming", "Deep", "BlenderOnly"} <= set(found)
    assert "Hidden" not in found
    assert "MayaOnly" not in found
    assert errors == []


def test_broken_files_are_reported_and_the_rest_still_load(tmp_path):
    write_check(tmp_path / "good.py", "Good")
    (tmp_path / "bad.py").write_text("raise ValueError('oops')\n")
    (tmp_path / "needs_blender.py").write_text("import bpy\n")

    checks, errors = load_checks([tmp_path])
    assert "Good" in names(checks)
    assert len(errors) == 1
    assert "bad.py" in errors[0].source
    assert "oops" in errors[0].message


def test_imported_and_abstract_checks_are_ignored(tmp_path):
    (tmp_path / "base.py").write_text(
        "from publish_validator import Check\nclass SharedBase(Check):\n    abstract = True\n"
    )
    (tmp_path / "child.py").write_text(
        "from publish_validator import Check\n"
        "class Child(Check):\n"
        "    def validate(self, ctx):\n"
        "        return []\n"
        "AlsoChild = Child\n"
    )
    checks, errors = load_checks([tmp_path])
    found = names(checks)
    assert found.count("Child") == 1
    assert "SharedBase" not in found
    assert errors == []


def test_duplicate_names_are_reported(tmp_path):
    write_check(tmp_path / "a" / "one.py", "Same")
    write_check(tmp_path / "b" / "two.py", "Same")
    checks, errors = load_checks([tmp_path])
    assert names(checks).count("Same") == 1
    assert "Two checks are called Same" in errors[0].message


def test_missing_folder_is_reported(tmp_path):
    _, errors = load_checks([tmp_path / "nope"])
    assert "does not exist" in errors[0].message


def test_env_folder(tmp_path, monkeypatch):
    write_check(tmp_path / "from_env.py", "FromEnv")
    monkeypatch.setenv(CHECK_PATH_ENV, str(tmp_path))
    checks, _ = load_checks()
    assert "FromEnv" in names(checks)


def test_edited_files_are_picked_up(tmp_path):
    path = tmp_path / "live.py"
    write_check(path, "Before")
    assert "Before" in names(load_checks([tmp_path])[0])
    write_check(path, "After")
    assert "After" in names(load_checks([tmp_path])[0])


def test_checks_can_import_helper_files(tmp_path):
    (tmp_path / "_shared.py").write_text("PREFIX = 'geo'\n")
    (tmp_path / "uses_helper.py").write_text(
        "from _shared import PREFIX\n"
        "from publish_validator import Check\n"
        "class UsesHelper(Check):\n"
        "    prefix = PREFIX\n"
        "    def validate(self, ctx):\n"
        "        return []\n"
    )
    checks, errors = load_checks([tmp_path])
    assert errors == []
    helper_check = next(c for c in checks if c.__name__ == "UsesHelper")
    assert helper_check.prefix == "geo"

    # Editing the helper is picked up on the next load, like editing a check.
    (tmp_path / "_shared.py").write_text("PREFIX = 'render'\n")
    checks, _ = load_checks([tmp_path])
    helper_check = next(c for c in checks if c.__name__ == "UsesHelper")
    assert helper_check.prefix == "render"
