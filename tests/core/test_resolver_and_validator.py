import json
import textwrap

import pytest

from publish_validator import (
    PropertyResolver,
    ResolveError,
    Status,
    Validator,
    format_text,
    load_config,
    to_json,
)
from publish_validator.testing import FakeHost, FakeNode


def build_scene():
    seat = FakeNode("seat")
    chair = FakeNode(
        "chair_root",
        FakeNode("geo", seat),
        props={"pv_task": "model", "pv_asset_type": "prop", "pv_asset_name": "chair"},
    )
    table = FakeNode("table", props={"pv_task": "model"})
    stray = FakeNode("stray")
    return FakeHost(chair, table, stray), chair, table, seat, stray


def test_resolver_walks_up_to_root():
    host, chair, _, seat, _ = build_scene()
    host.selected = [seat]
    subject = PropertyResolver().resolve(host)
    assert subject.root is chair
    assert (subject.name, subject.asset_type, subject.task) == ("chair", "prop", "model")


def test_resolver_errors_are_artist_friendly():
    host, chair, table, _, stray = build_scene()
    resolver = PropertyResolver()
    with pytest.raises(ResolveError, match="Select an asset root"):
        resolver.resolve(host)
    host.selected = [stray]
    with pytest.raises(ResolveError, match="belongs to an asset"):
        resolver.resolve(host)
    host.selected = [chair, table]
    with pytest.raises(ResolveError, match="several assets"):
        resolver.resolve(host)


def test_resolver_find_all_and_name_default():
    host, *_ = build_scene()
    names = [s.name for s in PropertyResolver().find_all(host)]
    assert names == ["chair", "table"]


STUDIO_CHECK = """
from publish_validator import Check

class GeoGroup(Check):
    \"\"\"Assets need a 'geo' group.\"\"\"
    id = "studio.geo_group"
    category = "Hierarchy"
    tasks = {"model"}

    class Settings:
        group = "geo"

    def validate(self, ctx):
        names = [ctx.host.node_name(c) for c in ctx.host.children(ctx.root)]
        if self.settings.group not in names:
            yield self.issue(f"missing '{self.settings.group}' group", ctx.root)
"""


def test_validator_end_to_end(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "hierarchy.py").write_text(textwrap.dedent(STUDIO_CHECK))
    (checks / "broken.py").write_text("raise ImportError('nope')\n")
    config_file = tmp_path / "studio.toml"
    config_file.write_text(
        'check_paths = ["checks"]\n'
        '[checks."studio.geo_group".settings]\ngroup = "render"\n'
        '[checks."typo.check"]\nenabled = false\n'
    )

    host, chair, *_ = build_scene()
    validator = Validator(host, config=load_config([config_file], use_env=False))
    host.selected = [chair]
    report = validator.run()

    assert report.subject_name == "chair"
    assert report.get("studio.geo_group").status is Status.FAILED
    assert report.get("hierarchy.root_not_empty").status is Status.PASSED
    assert report.get("transforms.unit_scale") is None  # blender-only, not loaded for "fake"
    sources = " ".join(e.source + e.message for e in report.load_errors)
    assert "broken.py" in sources and "typo.check" in sources
    assert not report.passed

    validator.select(report.get("studio.geo_group"))
    assert host.selection() == [chair]

    text = format_text(report)
    assert "[FAIL] Geo Group" in text and "BLOCKED" in text
    data = json.loads(to_json(report))
    geo = next(r for r in data["results"] if r["id"] == "studio.geo_group")
    assert geo["issues"][0]["targets"] == ["chair_root"]
    assert data["passed"] is False


def test_validator_resolver_from_config(tmp_path, monkeypatch):
    module = tmp_path / "my_pipeline.py"
    module.write_text(
        "from publish_validator import PropertyResolver\n"
        "class Resolver(PropertyResolver):\n"
        "    prefix = 'studio_'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "c.toml").write_text('resolver = "my_pipeline:Resolver"\n')
    root = FakeNode("prop", FakeNode("geo"), props={"studio_task": "model"})
    host = FakeHost(root)
    validator = Validator(host, config=load_config([tmp_path / "c.toml"], use_env=False))
    assert validator.resolve(root).task == "model"


def test_bad_resolver_falls_back_and_reports(tmp_path):
    (tmp_path / "c.toml").write_text('resolver = "does.not.exist:Nope"\n')
    validator = Validator(FakeHost(), config=load_config([tmp_path / "c.toml"], use_env=False))
    assert isinstance(validator.resolver, PropertyResolver)
    assert any("cannot load resolver" in e.message for e in validator.load_errors)
