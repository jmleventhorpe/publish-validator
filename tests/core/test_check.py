import pytest

from publish_validator import Check, Severity, Status, check
from publish_validator.core.check import humanize, snake
from publish_validator.testing import FakeNode, make_subject, run_check


class UVNaming(Check):
    """Summary line.

    Longer explanation.
    """

    tasks = {"model"}
    asset_types = "prop"

    class Settings:
        names = ["map1"]
        tolerance: float = 0.5
        lookup = {"a": 1}

    def validate(self, ctx):
        return []


def test_metadata_defaults():
    assert UVNaming.id == "test_check.uv_naming"
    assert UVNaming.label == "UV Naming"
    assert UVNaming.category == "General"
    assert UVNaming.severity is Severity.ERROR
    assert UVNaming.asset_types == frozenset({"prop"})
    assert UVNaming.summary() == "Summary line."
    assert "Longer explanation." in UVNaming.description()
    assert not UVNaming.is_fixable()


def test_settings_become_frozen_dataclass_with_friendly_defaults():
    settings = UVNaming.Settings()
    assert settings.names == ("map1",)
    assert settings.lookup == {"a": 1}
    with pytest.raises(AttributeError):
        settings.tolerance = 1.0  # frozen


def test_configure_overrides_and_coerces():
    settings = UVNaming.configure({"tolerance": 2, "names": ["uv", "map1"]})
    assert settings.tolerance == 2.0 and isinstance(settings.tolerance, float)
    assert settings.names == ("uv", "map1")


def test_configure_rejects_unknown_settings():
    with pytest.raises(ValueError, match="unknown setting"):
        UVNaming.configure({"tolernce": 1})


def test_settings_require_defaults():
    with pytest.raises(TypeError, match="needs a default"):

        class Broken(Check):
            class Settings:
                value: int

            def validate(self, ctx):
                return []


def test_subclass_settings_inherit_parent_fields():
    class Child(UVNaming):
        class Settings(UVNaming.Settings):
            extra = True

    settings = Child.Settings()
    assert settings.names == ("map1",) and settings.extra is True
    assert Child.id == "test_check.child"


def test_applies_to():
    subject = make_subject(FakeNode("a"), task="model", asset_type="prop")
    assert UVNaming.applies_to("blender", subject)
    other = make_subject(FakeNode("a"), task="rig", asset_type="prop")
    assert not UVNaming.applies_to("blender", other)


def test_abstract_base_is_not_concrete_but_children_are():
    class Base(Check):
        abstract = True

    class Concrete(Base):
        def validate(self, ctx):
            return []

    assert Base.is_abstract()
    assert not Concrete.is_abstract()


def test_function_check_and_fixer():
    @check(category="Hierarchy", settings={"limit": 1})
    def too_many_children(ctx):
        """Not too many children."""
        if len(ctx.host.children(ctx.root)) > ctx.settings.limit:
            yield "too many"

    assert too_many_children.id == "test_check.too_many_children"
    assert too_many_children.label == "Too Many Children"
    assert too_many_children.summary() == "Not too many children."

    root = FakeNode("root", FakeNode("a"), FakeNode("b"))
    assert run_check(too_many_children, root).status is Status.FAILED
    assert run_check(too_many_children, root, settings={"limit": 5}).status is Status.PASSED

    @too_many_children.fixer
    def _(ctx, issues):
        del ctx.root.children[1:]

    assert too_many_children.is_fixable()
    assert run_check(too_many_children, root, fix=True).status is Status.FIXED


@pytest.mark.parametrize(
    ("name", "label", "snaked"),
    [
        ("UnitScale", "Unit Scale", "unit_scale"),
        ("UVNaming", "UV Naming", "uv_naming"),
        ("root_not_empty", "Root Not Empty", "root_not_empty"),
    ],
)
def test_name_helpers(name, label, snaked):
    assert humanize(name) == label
    assert snake(name) == snaked
