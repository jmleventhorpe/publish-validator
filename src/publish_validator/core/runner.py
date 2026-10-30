"""Running checks against a subject and turning the outcome into a Report."""

from __future__ import annotations

import dataclasses
import time
import traceback
from collections.abc import Iterable
from typing import Any

from .check import Check
from .config import Config
from .context import Context
from .host import Host
from .model import CheckResult, Issue, LoadError, Report, Severity, Status
from .subject import Subject


class Observer:
    """Receives progress events from :func:`run`. Override what you need.

    UIs subscribe through this instead of the runner knowing about any UI.
    """

    def on_start(self, check: type[Check], index: int, total: int) -> None: ...

    def on_result(self, result: CheckResult) -> None: ...

    def on_finish(self, report: Report) -> None: ...


def run(
    subject: Subject,
    host: Host,
    checks: Iterable[type[Check]],
    *,
    config: Config | None = None,
    fix: bool = False,
    only: Iterable[str] | None = None,
    observer: Observer | None = None,
    load_errors: Iterable[LoadError] = (),
) -> Report:
    """Run ``checks`` against ``subject``.

    Args:
        checks: Check classes, normally ``registry.applicable(host.name, subject)``.
        config: Studio/project overrides (enabled, severity, settings).
        fix: Run ``fix()`` on checks that found issues and support it, then
            re-validate to report what is actually left.
        only: If given, run just these check ids; the rest are SKIPPED.
        observer: Progress callbacks.
    """
    config = config or Config()
    observer = observer or Observer()
    only = set(only) if only is not None else None
    checks = list(checks)
    cache: dict[Any, Any] = {}
    results: list[CheckResult] = []

    for index, check_cls in enumerate(checks):
        observer.on_start(check_cls, index, len(checks))
        overrides = config.for_check(check_cls.id)
        enabled = overrides.enabled if overrides.enabled is not None else check_cls.enabled
        if not enabled or (only is not None and check_cls.id not in only):
            result = _result(check_cls, Status.SKIPPED)
        else:
            result = _run_one(check_cls, subject, host, overrides, cache, fix)
        results.append(result)
        observer.on_result(result)

    report = Report(
        subject_name=subject.name,
        host=host.name,
        results=tuple(results),
        load_errors=tuple(load_errors),
        fix=fix,
    )
    observer.on_finish(report)
    return report


def _run_one(check_cls, subject, host, overrides, cache, fix) -> CheckResult:
    start = time.perf_counter()
    try:
        settings = check_cls.configure(overrides.settings)
        check = check_cls(settings)
        ctx = Context(subject=subject, host=host, settings=settings, cache=cache)
        issues = _collect(check, ctx, host, overrides.severity)
    except Exception:
        return _errored(check_cls, start)

    fixed: list[Issue] = []
    if fix and issues and check_cls.is_fixable():
        try:
            check.fix(ctx, list(issues))
            cache.clear()  # the scene changed; cached queries are stale
            remaining = _collect(check, ctx, host, overrides.severity)
        except Exception:
            return _errored(check_cls, start, issues=issues)
        remaining_messages = {i.message for i in remaining}
        fixed = [i for i in issues if i.message not in remaining_messages]
        issues = remaining

    status = _status(issues)
    if status is Status.PASSED and fixed:
        status = Status.FIXED
    return _result(
        check_cls,
        status,
        issues=issues,
        fixed=fixed,
        duration=time.perf_counter() - start,
    )


def _collect(check: Check, ctx: Context, host: Host, forced: Severity | None) -> list[Issue]:
    """Run validate() and normalise what it produced."""
    produced = check.validate(ctx)
    issues: list[Issue] = []
    for item in produced or ():
        if isinstance(item, str):
            item = Issue(item)
        elif not isinstance(item, Issue):
            raise TypeError(
                f"{type(check).__name__}.validate() produced {type(item).__name__}; "
                "yield Issue objects (self.issue(...)) or strings"
            )
        severity = forced or item.severity or check.severity
        issues.append(
            dataclasses.replace(
                item,
                severity=severity,
                target_names=tuple(_safe_name(host, t) for t in item.targets),
            )
        )
    return issues


def _status(issues: list[Issue]) -> Status:
    worst = max((i.severity.rank for i in issues if i.severity), default=-1)
    if worst >= Severity.ERROR.rank:
        return Status.FAILED
    if worst >= Severity.WARNING.rank:
        return Status.WARNING
    return Status.PASSED


def _result(check_cls, status, *, issues=(), fixed=(), duration=0.0, error=None) -> CheckResult:
    return CheckResult(
        check_id=check_cls.id,
        label=check_cls.label,
        category=check_cls.category,
        status=status,
        issues=tuple(issues),
        fixed_issues=tuple(fixed),
        error=error,
        duration=duration,
        description=check_cls.description(),
    )


def _errored(check_cls, start: float, issues=()) -> CheckResult:
    return _result(
        check_cls,
        Status.ERRORED,
        issues=issues,
        duration=time.perf_counter() - start,
        error=traceback.format_exc(),
    )


def _safe_name(host: Host, target: Any) -> str:
    try:
        return host.display_name(target)
    except Exception:
        return repr(target)
