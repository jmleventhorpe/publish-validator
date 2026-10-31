"""The Check base class. Every check is a subclass of it.

See docs/writing-checks.md for how to write one.
"""

import copy
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

        # A subclass adds to its parents' settings rather than replacing them.
        merged = {}
        for klass in reversed(cls.__mro__):
            merged.update(klass.__dict__.get("settings", {}))
        cls.settings = merged

        # A string would match substrings ("blend" in "blender"), so insist on a list.
        for attribute in ("hosts", "tasks", "asset_types"):
            value = getattr(cls, attribute)
            if isinstance(value, str):
                raise TypeError(
                    f"{cls.__name__}.{attribute} must be a list, e.g. {attribute} = [{value!r}]"
                )

    def __init__(self, settings=None):
        settings = settings or {}
        problems = self.settings_problems(settings)
        if problems:
            raise ValueError(" ".join(problems))
        self.settings = copy.deepcopy({**self.settings, **settings})

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
    def settings_problems(cls, settings):
        """What is wrong with settings from config, as messages. Empty means they are fine."""
        name = cls.__name__
        problems = []
        unknown = set(settings) - set(cls.settings)
        if unknown:
            problems.append(
                f"Unknown setting(s) for {name}: {', '.join(sorted(unknown))}. "
                f"Valid settings are: {', '.join(cls.settings) or 'none'}."
            )
        for key, value in settings.items():
            if key in cls.settings and not same_kind(value, cls.settings[key]):
                default = cls.settings[key]
                problems.append(
                    f"{name} setting {key} must be {kind_name(default)} like {default!r}, "
                    f"not {value!r}."
                )
        return problems

    @classmethod
    def can_fix(cls):
        # True if this check wrote its own fix(), rather than inheriting the empty one
        # above. fix = None in a subclass turns off a fix it would otherwise inherit.
        return cls.fix is not None and cls.fix is not Check.fix

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


def same_kind(value, default):
    """True if a config value has the same type as the setting's default.

    A default of None accepts anything, and a whole number is fine for a decimal one.
    """
    if default is None:
        return True
    # bool is a kind of int in Python, so check it first: 1 is not true, and true is not 1.
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) and isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float))
    return isinstance(value, type(default))


def kind_name(default):
    names = {
        bool: "true or false",
        int: "a whole number",
        float: "a number",
        str: "text",
        list: "a list",
        dict: "a table",
    }
    return names.get(type(default), f"a {type(default).__name__}")
