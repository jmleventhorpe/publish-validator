import pytest

from publish_validator import FAILED, FIXED, PASSED, Check, Subject
from publish_validator.testing import FakeNode, run_check


class UVNaming(Check):
    """Meshes need a UV set called map1.

    More detail here.
    """

    tasks = ["model"]
    asset_types = ["prop"]
    settings = {"names": ["map1"], "tolerance": 0.5}

    def validate(self, ctx):
        return []


class TooManyChildren(Check):
    settings = {"limit": 1}

    def validate(self, ctx):
        if len(ctx.host.children(ctx.root)) > self.settings["limit"]:
            yield "Too many children"

    def fix(self, ctx, issues):
        del ctx.root.children[1:]


def test_defaults():
    assert UVNaming.label == "UV Naming"
    assert UVNaming.category == "General"
    assert UVNaming.description().startswith("Meshes need a UV set called map1.")
    assert not UVNaming.can_fix()
    assert TooManyChildren.can_fix()


def test_settings_override_without_changing_the_class():
    check = UVNaming({"tolerance": 2})
    assert check.settings == {"names": ["map1"], "tolerance": 2}
    assert UVNaming.settings["tolerance"] == 0.5


def test_unknown_setting_is_an_error():
    with pytest.raises(ValueError, match="tolernce"):
        UVNaming({"tolernce": 1})


def test_applies_to():
    prop_model = Subject("chair", "prop", "model", root=None)
    prop_rig = Subject("chair", "prop", "rig", root=None)
    assert UVNaming.applies_to("blender", prop_model)
    assert not UVNaming.applies_to("blender", prop_rig)


def test_run_and_fix():
    root = FakeNode("root", FakeNode("a"), FakeNode("b"))
    assert run_check(TooManyChildren, root).status == FAILED
    assert run_check(TooManyChildren, root, settings={"limit": 5}).status == PASSED
    assert run_check(TooManyChildren, root, fix=True).status == FIXED
    assert len(root.children) == 1
