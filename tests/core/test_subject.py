import pytest

from publish_validator import Config, ConfigError, PropertyResolver, ResolveError, Validator
from publish_validator.testing import FakeHost, FakeNode


def make_scene():
    seat = FakeNode("seat")
    chair = FakeNode(
        "chair_root",
        FakeNode("geo", seat),
        props={"pv_task": "model", "pv_asset_type": "prop", "pv_asset_name": "chair"},
    )
    table = FakeNode("table", props={"pv_task": "model"})
    stray = FakeNode("stray")
    return FakeHost(chair, table, stray), chair, table, seat, stray


def test_selecting_inside_an_asset_finds_its_root():
    host, chair, _, seat, _ = make_scene()
    host.selected = [seat]
    subject = PropertyResolver().resolve(host)
    assert subject.root is chair
    assert (subject.name, subject.asset_type, subject.task) == ("chair", "prop", "model")


def test_messages_for_the_artist():
    host, chair, table, _, stray = make_scene()
    resolver = PropertyResolver()
    with pytest.raises(ResolveError, match="Select an asset root"):
        resolver.resolve(host)
    host.selected = [stray]
    with pytest.raises(ResolveError, match="isn't part of an asset"):
        resolver.resolve(host)
    host.selected = [chair, table]
    with pytest.raises(ResolveError, match="several assets"):
        resolver.resolve(host)


def test_find_all():
    host, *_ = make_scene()
    assert [s.name for s in PropertyResolver().find_all(host)] == ["chair", "table"]


def test_custom_resolver_from_config(tmp_path, monkeypatch):
    (tmp_path / "pipeline.py").write_text(
        "from publish_validator import PropertyResolver\n"
        "class Resolver(PropertyResolver):\n"
        "    prefix = 'studio_'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    config = Config()
    config.resolver = "pipeline:Resolver"

    root = FakeNode("prop", props={"studio_task": "model"})
    validator = Validator(FakeHost(root), config=config)
    assert validator.resolve(root).task == "model"


def test_a_bad_resolver_is_a_config_error():
    config = Config()
    config.resolver = "no.such.module:Resolver"
    with pytest.raises(ConfigError, match="Could not load the resolver"):
        Validator(FakeHost(), config=config)
