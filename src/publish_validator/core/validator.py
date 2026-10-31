"""The Validator: the one object that UIs, the command line and publish hooks use.

validator = Validator(BlenderHost())
report = validator.run()     # validates the selected asset
if not report.passed:
    ...
"""

import importlib
import traceback

from .check import Context
from .config import ConfigError, load_config
from .loader import class_names_on_disk, load_checks
from .results import (
    ERROR,
    ERRORED,
    FAILED,
    FIXED,
    PASSED,
    SKIPPED,
    WARNING,
    CheckResult,
    Issue,
    LoadError,
    Report,
)
from .subject import PropertyResolver


class Validator:
    def __init__(self, host, config=None, resolver=None, check_paths=()):
        self.host = host
        self.config = config or load_config()
        self.resolver = resolver or make_resolver(self.config.resolver)
        self.extra_check_paths = list(check_paths)
        self.reload()

    def reload(self):
        """Load every check file again, so edited checks work without a restart."""
        folders = self.config.check_paths + self.extra_check_paths
        self.checks, self.load_errors = load_checks(folders, self.host.name)
        self.load_errors += config_errors(self.config, self.checks, folders)

    def resolve(self, node=None):
        """The asset for a node, or for the selection. Raises ResolveError."""
        return self.resolver.resolve(self.host, node)

    def checks_for(self, subject):
        return [check for check in self.checks if check.applies_to(self.host.name, subject)]

    def run(self, subject=None, fix=False, only=None):
        """Run every check that applies to the subject (by default, the selected asset).

        fix: also apply automatic fixes.
        only: a list of check names; any others are skipped.
        """
        if subject is None:
            subject = self.resolve()
        ctx = Context(subject, self.host)

        results = []
        for check_class in self.checks_for(subject):
            # Checks are identified by their class name, in config and in reports.
            name = check_class.__name__
            options = self.config.for_check(name)
            enabled = options.get("enabled", check_class.enabled)
            if not enabled or (only and name not in only):
                results.append(make_result(check_class, SKIPPED))
            else:
                results.append(run_check(check_class, ctx, options, fix))

        return Report(subject.name, self.host.name, results, self.load_errors, fix)

    def run_all(self, fix=False, only=None):
        """Validate every asset in the scene, for batch and farm use."""
        subjects = self.resolver.find_all(self.host)
        return [self.run(subject, fix, only) for subject in subjects]

    def select(self, targets):
        self.host.select(targets)


def config_errors(config, checks, folders=()):
    """Mistakes in the config's [checks] tables, found before anything runs.

    Without this, a misspelled check name would be ignored, and a bad setting
    would only show up when that check ran.
    """
    errors = []
    by_name = {check.__name__: check for check in checks}
    on_disk = None  # only read the check files if a name isn't loaded
    for name, options in config.checks.items():
        source = ", ".join(config.sources.get(name, [])) or "config"
        check = by_name.get(name)
        if check is None:
            if on_disk is None:
                on_disk = class_names_on_disk(folders)
            if name not in on_disk:
                message = f"[checks.{name}] doesn't match any check. Check the spelling."
                errors.append(LoadError(source, message))
            continue
        for problem in check.settings_problems(options.get("settings", {})):
            errors.append(LoadError(source, problem))
    return errors


def run_check(check_class, ctx, options=None, fix=False):
    """Run one check and return its CheckResult."""
    options = options or {}
    forced_severity = options.get("severity")
    try:
        check = check_class(options.get("settings"))
        issues = find_issues(check, ctx, forced_severity)
        fixed = []
        if fix and issues and check.can_fix():
            check.fix(ctx, issues)
            ctx.cache.clear()  # the scene has changed, so cached values are out of date
            # Check again, so the report shows what is really left.
            remaining = find_issues(check, ctx, forced_severity)
            fixed = [issue for issue in issues if issue not in remaining]
            issues = remaining
    except Exception:
        # A broken check must never stop the other checks from running.
        return make_result(check_class, ERRORED, error=traceback.format_exc())

    return make_result(check_class, get_status(issues, fixed), issues, fixed)


def find_issues(check, ctx, forced_severity=None):
    """Call check.validate() and fill in each issue's severity and target names."""
    issues = []
    for issue in check.validate(ctx) or []:
        if isinstance(issue, str):
            issue = Issue(issue)
        # A severity set in config beats the issue's own, which beats the check's default.
        issue.severity = forced_severity or issue.severity or check.severity
        issue.target_names = [ctx.host.display_name(target) for target in issue.targets]
        issues.append(issue)
    return issues


def get_status(issues, fixed):
    severities = {issue.severity for issue in issues}
    if ERROR in severities:
        return FAILED
    if WARNING in severities:
        return WARNING
    if fixed:
        return FIXED
    return PASSED


def make_result(check_class, status, issues=(), fixed=(), error=""):
    return CheckResult(
        check_id=check_class.__name__,
        label=check_class.label,
        category=check_class.category,
        description=check_class.description(),
        status=status,
        issues=list(issues),
        fixed_issues=list(fixed),
        error=error,
    )


def make_resolver(path):
    """Create the resolver named in config ("module:Class"), or the default one."""
    if not path:
        return PropertyResolver()
    module_name, class_name = path.split(":")
    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)()
    except Exception as error:
        raise ConfigError(f"Could not load the resolver {path}: {error}") from error
