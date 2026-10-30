from publish_validator import Check, Component, Observer, Severity, Status, run
from publish_validator.core.config import CheckConfig, Config
from publish_validator.testing import FakeHost, FakeNode, make_subject


def scene():
    root = FakeNode(
        "chair",
        FakeNode("geo", FakeNode("seat", scale=(2, 1, 1)), FakeNode("leg", scale=(1, 1, 1))),
        props={"pv_task": "model", "pv_asset_type": "prop"},
    )
    return root, FakeHost(root)


def scaled(host, root):
    return [n for n in host.descendants(root) if getattr(n, "scale", (1, 1, 1)) != (1, 1, 1)]


class Scale(Check):
    def validate(self, ctx):
        for node in scaled(ctx.host, ctx.root):
            yield self.issue(f"{node.name} is scaled", node)

    def fix(self, ctx, issues):
        for issue in issues:
            for node in issue.targets:
                node.scale = (1, 1, 1)


class Explodes(Check):
    def validate(self, ctx):
        raise RuntimeError("boom")


class YieldsJunk(Check):
    def validate(self, ctx):
        yield 42


class Warns(Check):
    severity = Severity.WARNING

    def validate(self, ctx):
        yield "just a warning"
        yield self.issue("only info", severity="info")


class Mixed(Check):
    def validate(self, ctx):
        yield self.issue("minor", severity=Severity.INFO)


class BrokenFix(Check):
    def validate(self, ctx):
        yield "bad"

    def fix(self, ctx, issues):
        raise RuntimeError("fix failed")


def run_checks(*checks, **kwargs):
    root, host = scene()
    return run(make_subject(root), host, checks, **kwargs), root


def test_statuses_and_isolation():
    report, _ = run_checks(Scale, Explodes, YieldsJunk, Warns, Mixed)
    status = {r.check_id: r.status for r in report.results}
    assert status == {
        Scale.id: Status.FAILED,
        Explodes.id: Status.ERRORED,
        YieldsJunk.id: Status.ERRORED,
        Warns.id: Status.WARNING,
        Mixed.id: Status.PASSED,
    }
    assert "boom" in report.get(Explodes.id).error
    assert "yield Issue objects" in report.get(YieldsJunk.id).error
    assert not report.passed


def test_issue_severity_and_target_names():
    report, _ = run_checks(Scale, Warns)
    (scale_issue,) = report.get(Scale.id).issues
    assert scale_issue.severity is Severity.ERROR
    assert scale_issue.target_names == ("seat",)
    warn_severities = [i.severity for i in report.get(Warns.id).issues]
    assert warn_severities == [Severity.WARNING, Severity.INFO]


def test_fix_then_revalidate():
    report, _root = run_checks(Scale, fix=True)
    result = report.get(Scale.id)
    assert result.status is Status.FIXED
    assert [i.message for i in result.fixed_issues] == ["seat is scaled"]
    assert report.passed


def test_fix_error_is_reported_with_original_issues():
    report, _ = run_checks(BrokenFix, fix=True)
    result = report.get(BrokenFix.id)
    assert result.status is Status.ERRORED
    assert "fix failed" in result.error
    assert [i.message for i in result.issues] == ["bad"]


def test_config_disable_and_severity_override():
    config = Config(
        checks={
            Explodes.id: CheckConfig(enabled=False),
            Scale.id: CheckConfig(severity=Severity.WARNING),
        }
    )
    report, _ = run_checks(Scale, Explodes, config=config)
    assert report.get(Explodes.id).status is Status.SKIPPED
    assert report.get(Scale.id).status is Status.WARNING
    assert report.passed


def test_disabled_by_default_check_can_be_enabled():
    class OptIn(Check):
        enabled = False

        def validate(self, ctx):
            yield "found"

    report, _ = run_checks(OptIn)
    assert report.get(OptIn.id).status is Status.SKIPPED
    config = Config(checks={OptIn.id: CheckConfig(enabled=True)})
    report, _ = run_checks(OptIn, config=config)
    assert report.get(OptIn.id).status is Status.FAILED


def test_bad_settings_override_errors_only_that_check():
    config = Config(checks={Scale.id: CheckConfig(settings={"nope": 1})})
    report, _ = run_checks(Scale, Mixed, config=config)
    assert report.get(Scale.id).status is Status.ERRORED
    assert "unknown setting" in report.get(Scale.id).error
    assert report.get(Mixed.id).status is Status.PASSED


def test_only():
    report, _ = run_checks(Scale, Warns, only=[Warns.id])
    assert report.get(Scale.id).status is Status.SKIPPED
    assert report.get(Warns.id).status is Status.WARNING


def test_observer_and_shared_cache():
    calls = []

    class First(Check):
        def validate(self, ctx):
            ctx.cached("thing", lambda: calls.append("computed") or 1)
            return []

    class Second(First):
        pass

    events = []

    class Recorder(Observer):
        def on_start(self, check, index, total):
            events.append(("start", check.id, index, total))

        def on_result(self, result):
            events.append(("result", result.check_id))

        def on_finish(self, report):
            events.append(("finish", len(report.results)))

    run_checks(First, Second, observer=Recorder())
    assert calls == ["computed"]
    assert events == [
        ("start", First.id, 0, 2),
        ("result", First.id),
        ("start", Second.id, 1, 2),
        ("result", Second.id),
        ("finish", 2),
    ]


def test_component_display_name():
    class Faces(Check):
        def validate(self, ctx):
            yield self.issue("ngons", Component(ctx.root, "face", (1, 2, 3, 7)))

    report, _ = run_checks(Faces)
    assert report.get(Faces.id).issues[0].target_names == ("chair.face[1:3,7]",)
