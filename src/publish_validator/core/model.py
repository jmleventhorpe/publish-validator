"""Plain data types shared by every part of the validator.

Nothing here knows about a DCC, a UI or how checks are found. Checks produce
:class:`Issue` objects, the runner wraps them in :class:`CheckResult`, and a run
produces a :class:`Report`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """How serious an issue is. ``ERROR`` blocks a publish; the others do not."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2}


class Status(StrEnum):
    """Outcome of running one check."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    FIXED = "fixed"
    ERRORED = "errored"  # the check itself raised; it says nothing about the asset
    SKIPPED = "skipped"

    @property
    def blocking(self) -> bool:
        """Whether this outcome should stop a publish."""
        return self in (Status.FAILED, Status.ERRORED)


@dataclass(frozen=True, slots=True)
class Component:
    """A sub-element of a node, e.g. some faces of a mesh.

    Hosts know how to select these, so geometry checks can point at the exact
    faces/edges/vertices that are wrong instead of the whole object.
    """

    node: Any
    kind: str  # "vertex", "edge" or "face"
    indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Issue:
    """One problem found by a check.

    Attributes:
        message: Human readable description of this specific problem.
        targets: Scene objects (or :class:`Component` objects) involved. These
            are what "Select" selects, and what ``fix()`` receives back.
        severity: Overrides the check's default severity for this issue only.
        data: Anything the check wants to pass from ``validate()`` to ``fix()``.
        target_names: Filled in by the runner using the host, so reports can
            show targets without holding live scene objects.
    """

    message: str
    targets: tuple[Any, ...] = ()
    severity: Severity | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    target_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The outcome of one check in one run."""

    check_id: str
    label: str
    category: str
    status: Status
    issues: tuple[Issue, ...] = ()
    fixed_issues: tuple[Issue, ...] = ()
    error: str | None = None  # traceback text when status is ERRORED
    duration: float = 0.0
    description: str = ""

    @property
    def targets(self) -> list[Any]:
        """Every target of every remaining issue, without duplicates."""
        seen: list[Any] = []
        for issue in self.issues:
            for target in issue.targets:
                if not any(target is s for s in seen):
                    seen.append(target)
        return seen


@dataclass(frozen=True, slots=True)
class LoadError:
    """A check (or config) that could not be loaded. Reported, never fatal."""

    source: str
    message: str
    traceback: str = ""


@dataclass(frozen=True, slots=True)
class Report:
    """Everything that happened in one validation run."""

    subject_name: str
    host: str
    results: tuple[CheckResult, ...]
    load_errors: tuple[LoadError, ...] = ()
    fix: bool = False

    @property
    def passed(self) -> bool:
        """True when nothing blocks a publish."""
        return not any(r.status.blocking for r in self.results)

    def by_status(self, *statuses: Status) -> list[CheckResult]:
        return [r for r in self.results if r.status in statuses]

    def get(self, check_id: str) -> CheckResult | None:
        return next((r for r in self.results if r.check_id == check_id), None)

    def counts(self) -> dict[Status, int]:
        counts = {status: 0 for status in Status}
        for result in self.results:
            counts[result.status] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation (live scene objects are dropped)."""
        return {
            "subject": self.subject_name,
            "host": self.host,
            "passed": self.passed,
            "fix": self.fix,
            "counts": {str(k): v for k, v in self.counts().items()},
            "results": [
                {
                    "id": r.check_id,
                    "label": r.label,
                    "category": r.category,
                    "status": str(r.status),
                    "duration": round(r.duration, 4),
                    "error": r.error,
                    "issues": [_issue_dict(i) for i in r.issues],
                    "fixed_issues": [_issue_dict(i) for i in r.fixed_issues],
                }
                for r in self.results
            ],
            "load_errors": [{"source": e.source, "message": e.message} for e in self.load_errors],
        }


def _issue_dict(issue: Issue) -> dict[str, Any]:
    return {
        "message": issue.message,
        "severity": str(issue.severity) if issue.severity else None,
        "targets": list(issue.target_names),
    }
