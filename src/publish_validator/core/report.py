"""Rendering a :class:`Report` for people (text) and machines (JSON)."""

from __future__ import annotations

import json
from itertools import groupby

from .model import Report, Status

_ICONS = {
    Status.PASSED: "ok  ",
    Status.WARNING: "WARN",
    Status.FAILED: "FAIL",
    Status.FIXED: "FIX ",
    Status.ERRORED: "ERR ",
    Status.SKIPPED: "skip",
}


def format_text(
    report: Report,
    *,
    max_issues: int = 20,
    show_passed: bool = True,
    show_skipped: bool = False,
    show_tracebacks: bool = False,
) -> str:
    """A readable, grouped summary suitable for a console or log file."""
    lines = [f"Validation of '{report.subject_name}' in {report.host}"]
    if report.fix:
        lines[0] += " (with fixes)"
    lines.append("")

    hidden = set()
    if not show_passed:
        hidden.add(Status.PASSED)
    if not show_skipped:
        hidden.add(Status.SKIPPED)
    visible = [r for r in report.results if r.status not in hidden]

    for category, results in groupby(
        sorted(visible, key=lambda r: r.category), key=lambda r: r.category
    ):
        lines.append(f"{category}")
        for result in results:
            lines.append(f"  [{_ICONS[result.status]}] {result.label}  ({result.check_id})")
            for issue in result.issues[:max_issues]:
                severity = f"{issue.severity}: " if issue.severity else ""
                lines.append(f"         - {severity}{issue.message}")
            if len(result.issues) > max_issues:
                lines.append(f"         ... and {len(result.issues) - max_issues} more")
            for issue in result.fixed_issues[:max_issues]:
                lines.append(f"         + fixed: {issue.message}")
            if result.status is Status.ERRORED and result.error:
                if show_tracebacks:
                    lines += [f"         {line}" for line in result.error.rstrip().splitlines()]
                else:
                    lines.append(f"         ! {result.error.rstrip().splitlines()[-1]}")
        lines.append("")

    for error in report.load_errors:
        lines.append(f"Load error: {error.source}: {error.message}")
    if report.load_errors:
        lines.append("")

    counts = report.counts()
    summary = ", ".join(f"{n} {status}" for status, n in counts.items() if n)
    lines.append(f"{'PASSED' if report.passed else 'BLOCKED'}: {summary or 'no checks ran'}")
    return "\n".join(lines)


def to_json(report: Report, *, indent: int | None = 2) -> str:
    return json.dumps(report.to_dict(), indent=indent)
