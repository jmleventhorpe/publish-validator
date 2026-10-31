"""What a validation run produces: issues, a result per check, and a report."""

import json
from dataclasses import dataclass, field

# How serious an issue is. Only errors block a publish.
INFO = "info"
WARNING = "warning"
ERROR = "error"
SEVERITIES = (INFO, WARNING, ERROR)

# The outcome of one check. WARNING (above) is also used as a status.
PASSED = "passed"
FAILED = "failed"
FIXED = "fixed"
ERRORED = "errored"  # the check itself crashed, which says nothing about the asset
SKIPPED = "skipped"
STATUSES = (PASSED, FIXED, WARNING, FAILED, ERRORED, SKIPPED)
BLOCKING = (FAILED, ERRORED)


@dataclass
class Component:
    """Part of a mesh (some faces, edges or vertices), so Select can pick exactly those."""

    node: object
    kind: str  # "vertex", "edge" or "face"
    indices: list


@dataclass
class Issue:
    """One problem found by a check."""

    message: str
    targets: list = field(default_factory=list)  # scene objects to select and fix
    severity: str | None = None  # None means "use the check's severity"
    data: dict = field(default_factory=dict)  # anything validate() wants to hand to fix()
    target_names: list = field(default_factory=list)  # filled in for reports


@dataclass
class CheckResult:
    check_id: str
    label: str
    category: str
    description: str
    status: str
    issues: list = field(default_factory=list)
    fixed_issues: list = field(default_factory=list)
    error: str = ""  # the traceback, if the check crashed
    can_fix: bool = False  # the check has a fix() method
    skip_reason: str = ""  # why it was skipped, e.g. "disabled in config"

    @property
    def short_error(self):
        """The last line of the traceback, e.g. "KeyError: 'scale'"."""
        return last_line(self.error)

    @property
    def targets(self):
        """Every target of every issue, without duplicates."""
        targets = []
        for issue in self.issues:
            for target in issue.targets:
                if target not in targets:
                    targets.append(target)
        return targets


@dataclass
class LoadError:
    """A check file or setting that could not be loaded."""

    source: str
    message: str  # can be a whole traceback

    @property
    def short_message(self):
        return last_line(self.message)


@dataclass
class Report:
    subject_name: str
    host_name: str
    results: list
    load_errors: list = field(default_factory=list)
    with_fixes: bool = False

    @property
    def passed(self):
        """True when nothing blocks the publish."""
        return not any(result.status in BLOCKING for result in self.results)

    def get(self, check_id):
        for result in self.results:
            if result.check_id == check_id:
                return result
        return None

    def replace(self, result):
        """Swap in a newer result for the same check, e.g. after fixing just that check."""
        for index, old in enumerate(self.results):
            if old.check_id == result.check_id:
                self.results[index] = result
                return
        self.results.append(result)

    def counts(self, results=None):
        """How many results have each status, e.g. {"passed": 4, "failed": 1}.

        Statuses are always in the same order, and ones with no results are left out.
        """
        statuses = [result.status for result in (self.results if results is None else results)]
        return {status: statuses.count(status) for status in STATUSES if status in statuses}

    def summary(self):
        """e.g. "4 passed, 1 failed"."""
        return ", ".join(f"{count} {status}" for status, count in self.counts().items())

    def as_dict(self):
        return {
            "subject": self.subject_name,
            "host": self.host_name,
            "passed": self.passed,
            "with_fixes": self.with_fixes,
            "results": [
                {
                    "id": result.check_id,
                    "label": result.label,
                    "status": result.status,
                    "skip_reason": result.skip_reason,
                    "issues": [issue_as_dict(issue) for issue in result.issues],
                    "fixed": [issue_as_dict(issue) for issue in result.fixed_issues],
                    "error": result.error,
                }
                for result in self.results
            ],
            "load_errors": [{"source": e.source, "message": e.message} for e in self.load_errors],
        }

    def as_json(self):
        return json.dumps(self.as_dict(), indent=2)

    def as_text(self, show_passed=True, max_issues=20):
        """A readable summary for the console or a log file."""
        title = f"Validation of '{self.subject_name}' in {self.host_name}"
        lines = [title + (" (with fixes)" if self.with_fixes else ""), ""]

        by_category = {}
        for result in self.results:
            if result.status == SKIPPED or (result.status == PASSED and not show_passed):
                continue
            by_category.setdefault(result.category, []).append(result)

        for category in sorted(by_category):
            lines.append(category)
            for result in by_category[category]:
                lines.append(f"  [{result.status.upper()}] {result.label}")
                for issue in result.issues[:max_issues]:
                    lines.append(f"      - {issue.message}")
                if len(result.issues) > max_issues:
                    lines.append(f"      ... and {len(result.issues) - max_issues} more")
                for issue in result.fixed_issues:
                    lines.append(f"      fixed: {issue.message}")
                if result.error:
                    lines.append(f"      ! {result.short_error}")
            lines.append("")

        for error in self.load_errors:
            lines.append(f"Problem in {error.source}: {error.short_message}")

        lines.append(f"{'PASSED' if self.passed else 'BLOCKED'}: {self.summary()}")
        return "\n".join(lines)


def last_line(text):
    lines = text.strip().splitlines()
    return lines[-1] if lines else ""


def issue_as_dict(issue):
    return {"message": issue.message, "severity": issue.severity, "targets": issue.target_names}
