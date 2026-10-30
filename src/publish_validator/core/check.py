"""The Check base class. Every check is a subclass of it.

See docs/writing-checks.md for how to write one.
"""

import inspect
import re

from .results import ERROR, Issue


class Check:
    label = ""  # name shown in the UI, defaults to the class name with spaces
    category = "General"  # group shown in the UI
    hosts = None  # e.g. ["blender"], None means every application
    tasks = None  # e.g. ["model"], None means every task
    asset_types = None  # e.g. ["prop", "character"], None means every asset type
    severity = ERROR  # used for issues that don't set their own
    enabled = True  # False means studios have to switch it on in their config
    settings = {}  # values a studio can change in config without editing the check
    abstract = False  # True on shared base classes, so they aren't run themselves

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "label" not in cls.__dict__:
            cls.label = spaced_name(cls.__name__)

    def __init__(self, settings=None):
        settings = settings or {}
        unknown = set(settings) - set(self.settings)
        if unknown:
            raise ValueError(
                f"Unknown setting(s) for {type(self).__name__}: {', '.join(sorted(unknown))}. "
                f"Valid settings are: {', '.join(self.settings) or 'none'}"
            )
        # Copy, so changing self.settings never changes the class defaults.
        self.settings = {**self.settings, **settings}

    def validate(self, ctx):
        """Return or yield the issues found. Returning nothing means the check passed."""
        raise NotImplementedError(f"{type(self).__name__} needs a validate() method")

    def fix(self, ctx, issues):
        """Optional. Repair the issues; the check is run again afterwards."""
        raise NotImplementedError

    def issue(self, message, *targets, severity=None, **data):
        """Make an Issue. targets are the scene objects involved."""
        return Issue(message, list(targets), severity, data)

    @classmethod
    def can_fix(cls):
        return cls.fix is not Check.fix

    @classmethod
    def applies_to(cls, host_name, subject):
        return (
            (cls.hosts is None or host_name in cls.hosts)
            and (cls.tasks is None or subject.task in cls.tasks)
            and (cls.asset_types is None or subject.asset_type in cls.asset_types)
        )

    @classmethod
    def description(cls):
        """The check's own docstring (not one inherited from a parent class)."""
        doc = cls.__dict__.get("__doc__")
        return inspect.cleandoc(doc) if doc else ""


class Context:
    """What a check works with: the asset (subject), the application (host) and a cache."""

    def __init__(self, subject, host):
        self.subject = subject
        self.host = host
        self.root = subject.root
        self.cache = {}  # shared by every check in one run

    def cached(self, key, compute):
        """Compute a value once per run and share it between checks.

        meshes = ctx.cached("meshes", lambda: ctx.host.meshes(ctx.root))
        """
        if key not in self.cache:
            self.cache[key] = compute()
        return self.cache[key]


def spaced_name(name):
    """UnitScale -> Unit Scale, UVNaming -> UV Naming."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
