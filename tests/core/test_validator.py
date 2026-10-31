import pytest

from publish_validator import (
    ERRORED,
    FAILED,
    FIXED,
    SKIPPED,
    WARNING,
    Check,
    Component,
    Config,
    Validator,
)
from publish_validator.core.validator import config_errors
from publish_validator.testing import FakeHost, FakeNode


def make_scene():
    seat = FakeNode("seat", scale=(2, 1, 1))
    leg = FakeNode("leg", scale=(1, 1, 1))
    root = FakeNode("chair", FakeNode("geo", seat, leg), props={"pv_task": "model"})
    host = FakeHost(root)
    host.selected = [root]
    return host


class Scale(Check):
    def validate(self, ctx):
        for node in ctx.host.descendants(ctx.root):
            if getattr(node, "scale", (1, 1, 1)) != (1, 1, 1):
                yield self.issue(f"{node.name} is scaled", node)

    def fix(self, ctx, issues):
        for issue in issues:
            for node in issue.targets:
                node.scale = (1, 1, 1)


class Crashes(Check):
    def validate(self, ctx):
        raise RuntimeError("boom")


class Warns(Check):
    severity = WARNING

    def validate(self, ctx):
        yield "Just a warning"


class BadFix(Check):
    def validate(self, ctx):
        yield "Broken"

    def fix(self, ctx, issues):
        raise RuntimeError("fix failed")


def run(*checks, config=None, **kwargs):
    validator = Validator(make_scene(), config=config or Config())
    validator.checks = list(checks)  # use just these, not the built-in checks
    return validator.run(**kwargs)


def test_statuses():
    report = run(Scale, Crashes, Warns)
    assert report.get("Scale").status == FAILED
    assert report.get("Crashes").status == ERRORED
    assert "boom" in report.get("Crashes").error
    assert report.get("Warns").status == WARNING
    assert not report.passed


def test_issue_details():
    report = run(Scale)
    issue = report.get("Scale").issues[0]
    assert issue.message == "seat is scaled"
    assert issue.severity == "error"
    assert issue.target_names == ["seat"]


def test_fix_then_check_again():
    report = run(Scale, fix=True)
    result = report.get("Scale")
    assert result.status == FIXED
    assert [issue.message for issue in result.fixed_issues] == ["seat is scaled"]
    assert report.passed


def test_crashing_fix_is_reported():
    report = run(BadFix, fix=True)
    assert report.get("BadFix").status == ERRORED
    assert "fix failed" in report.get("BadFix").error


def test_config_can_disable_and_change_severity():
    config = Config()
    config.checks = {
        "Crashes": {"enabled": False, "settings": {}},
        "Scale": {"severity": "warning", "settings": {}},
    }
    report = run(Scale, Crashes, config=config)
    assert report.get("Crashes").status == SKIPPED
    assert report.get("Scale").status == WARNING
    assert report.passed


def test_only():
    report = run(Scale, Warns, only=["Warns"])
    assert report.get("Scale").status == SKIPPED
    assert report.get("Warns").status == WARNING


def test_cache_is_shared_between_checks():
    computed = []

    class First(Check):
        def validate(self, ctx):
            ctx.cached("thing", lambda: computed.append(1))

    class Second(First):
        pass

    run(First, Second)
    assert computed == [1]


def test_component_names():
    class Faces(Check):
        def validate(self, ctx):
            yield self.issue("Ngons", Component(ctx.root, "face", [1, 2, 3, 4, 5, 6, 7]))

    report = run(Faces)
    assert report.get("Faces").issues[0].target_names == ["chair.face[1, 2, 3, 4, 5, ...]"]


def test_report_text_and_json():
    report = run(Scale, Warns)
    text = report.as_text()
    assert "[FAILED] Scale" in text
    assert "BLOCKED" in text
    assert '"passed": false' in report.as_json()


def test_select():
    validator = Validator(make_scene(), config=Config())
    validator.checks = [Scale]
    result = validator.run().get("Scale")
    validator.select(result.targets)
    assert [node.name for node in validator.host.selection()] == ["seat"]


def test_summary_order_is_always_the_same():
    report = run(Warns, Scale, Crashes)
    assert report.summary() == "1 warning, 1 failed, 1 errored"


class Tolerant(Check):
    settings = {"tolerance": 0.1}

    def validate(self, ctx):
        return []


def test_config_mistakes_are_reported_before_anything_runs(tmp_path):
    # A Maya check isn't loaded outside Maya, but config may still mention it.
    maya = tmp_path / "maya"
    maya.mkdir()
    (maya / "rigs.py").write_text("class MayaOnly:\n    pass\n")

    config = Config()
    config.checks = {
        "Tolerant": {"enabled": False, "settings": {"tolerence": 1, "tolerance": "high"}},
        "Tolerent": {"settings": {}},
        "MayaOnly": {"settings": {}},
    }
    config.sources = {"Tolerent": ["project.toml"]}
    errors = config_errors(config, [Tolerant], [tmp_path])

    messages = [error.message for error in errors]
    assert len(messages) == 3
    # Reported even though the check is disabled.
    assert "Unknown setting(s) for Tolerant: tolerence" in messages[0]
    assert "tolerance must be a number like 0.1, not 'high'" in messages[1]
    assert messages[2] == "[checks.Tolerent] doesn't match any check. Check the spelling."
    assert errors[2].source == "project.toml"


def config_with(**checks):
    config = Config()
    config.checks = {name: {"settings": {}, **options} for name, options in checks.items()}
    return config


def test_unticking_every_check_skips_them_all():
    # An empty `only` means "nothing selected", not "run everything".
    report = run(Scale, Warns, only=[])
    assert {r.status for r in report.results} == {SKIPPED}
    assert report.passed


def test_skip_reasons():
    config = config_with(Crashes={"enabled": False})
    report = run(Crashes, Warns, config=config, only=["Crashes"])
    assert report.get("Crashes").skip_reason == "disabled in config"
    assert report.get("Warns").skip_reason == "not selected"


def test_plan_leaves_out_disabled_checks():
    validator = Validator(make_scene(), config=config_with(Crashes={"enabled": False}))
    validator.checks = [Scale, Crashes, Warns]
    planned = [check.__name__ for check in validator.plan(validator.resolve())]
    assert planned == ["Scale", "Warns"]


def test_run_one_and_replace():
    validator = Validator(make_scene(), config=Config())
    validator.checks = [Scale, Warns]
    report = validator.run()
    assert report.get("Scale").status == FAILED
    assert report.get("Scale").can_fix
    assert not report.get("Warns").can_fix

    assert validator.run_one("Scale").status == FAILED  # no fix: nothing changes
    fixed = validator.run_one("Scale", fix=True)
    assert fixed.status == FIXED

    report.replace(fixed)
    assert report.get("Scale").status == FIXED
    assert report.get("Warns").status == WARNING
    assert report.counts() == {"fixed": 1, "warning": 1}
    assert report.passed


def test_run_one_unknown_check():
    validator = Validator(make_scene(), config=Config())
    validator.checks = [Scale]
    with pytest.raises(KeyError, match="No check called Nope"):
        validator.run_one("Nope")
