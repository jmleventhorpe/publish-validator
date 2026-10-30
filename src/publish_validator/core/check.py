"""The :class:`Check` base class: the one thing check authors need to know.

Minimal check::

    from publish_validator import Check

    class UnitScale(Check):
        \"\"\"Objects must have a scale of 1.\"\"\"

        hosts = {"blender"}

        def validate(self, ctx):
            for obj in ctx.host.meshes(ctx.root):
                if tuple(obj.scale) != (1, 1, 1):
                    yield self.issue(f"{obj.name} is scaled", obj)

Everything else (metadata, settings, fix) is optional. Classes are picked up
automatically by discovery; there is nothing to register.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, ClassVar

from .context import Context
from .model import Issue, Severity
from .subject import Subject


def issue(
    message: str, *targets: Any, severity: Severity | str | None = None, **data: Any
) -> Issue:
    """Create an :class:`Issue`. ``targets`` are the scene objects involved."""
    return Issue(
        message=message,
        targets=tuple(targets),
        severity=Severity(severity) if severity is not None else None,
        data=data,
    )


class Check:
    """Base class for every check.

    Class attributes (all optional):
        id: Stable identifier used by config files. Defaults to
            ``"<module>.<snake_case_class_name>"``; set it explicitly if you
            might rename the class or file.
        label: Name shown in the UI. Defaults to the class name, spaced out.
        category: Group shown in the UI, e.g. "Transforms" or "Naming".
        hosts: Hosts this check runs in, e.g. ``{"blender"}``. None = all.
        tasks: Tasks it applies to, e.g. ``{"model"}``. None = all.
        asset_types: Asset types it applies to, e.g. ``{"prop"}``. None = all.
        severity: Default severity of its issues. ``ERROR`` blocks publishing.
        enabled: Set False to ship a check that studios must opt into.
        order: Lower runs first. Ties keep discovery order.
        abstract: Set True on a shared base class so it is not run itself.
        Settings: Nested class of tunable values with defaults. Studios can
            override them per project in config; read them via ``self.settings``.

    The docstring is the check's documentation: first line is a summary, the
    rest should say why it matters and how to fix it by hand.
    """

    id: ClassVar[str] = ""
    label: ClassVar[str] = ""
    category: ClassVar[str] = "General"
    hosts: ClassVar[frozenset[str] | None] = None
    tasks: ClassVar[frozenset[str] | None] = None
    asset_types: ClassVar[frozenset[str] | None] = None
    severity: ClassVar[Severity] = Severity.ERROR
    enabled: ClassVar[bool] = True
    order: ClassVar[int] = 0
    abstract: ClassVar[bool] = False

    class Settings:
        pass

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        own = cls.__dict__
        if not own.get("id"):
            cls.id = default_id(cls)
        if not own.get("label"):
            cls.label = humanize(cls.__name__)
        cls.hosts = _as_set(cls.hosts)
        cls.tasks = _as_set(cls.tasks)
        cls.asset_types = _as_set(cls.asset_types)
        cls.severity = Severity(cls.severity)
        if "Settings" in own:
            cls.Settings = make_settings_class(own["Settings"], owner=cls)

    def __init__(self, settings: Any = None) -> None:
        self.settings = settings if settings is not None else type(self).Settings()

    # -- To implement -----------------------------------------------------------

    def validate(self, ctx: Context) -> Iterable[Issue | str] | None:
        """Yield (or return a list of) issues. Nothing yielded means passed.

        Plain strings are accepted as a shortcut for an issue with no targets.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement validate()")

    def fix(self, ctx: Context, issues: list[Issue]) -> None:
        """Optional. Repair ``issues``; the runner re-validates afterwards."""
        raise NotImplementedError

    # -- Helpers ----------------------------------------------------------------

    def issue(
        self, message: str, *targets: Any, severity: Severity | str | None = None, **data: Any
    ) -> Issue:
        """Shortcut for :func:`issue`."""
        return issue(message, *targets, severity=severity, **data)

    @classmethod
    def is_fixable(cls) -> bool:
        return cls.fix is not Check.fix

    @classmethod
    def is_abstract(cls) -> bool:
        return cls is Check or bool(cls.__dict__.get("abstract", False))

    @classmethod
    def applies_to(cls, host: str, subject: Subject) -> bool:
        """Whether this check is relevant for ``subject`` in ``host``."""
        return (
            _matches(cls.hosts, host)
            and _matches(cls.tasks, subject.task)
            and _matches(cls.asset_types, subject.asset_type)
        )

    @classmethod
    def description(cls) -> str:
        doc = cls.__dict__.get("__doc__")
        return inspect.cleandoc(doc) if doc else ""

    @classmethod
    def summary(cls) -> str:
        return cls.description().split("\n", 1)[0]

    @classmethod
    def configure(cls, overrides: Mapping[str, Any] | None) -> Any:
        """Build this check's settings with ``overrides`` applied.

        Raises:
            ValueError: for unknown setting names.
        """
        defaults = cls.Settings()
        if not overrides:
            return defaults
        fields = {f.name: f for f in dataclasses.fields(defaults)}
        unknown = sorted(set(overrides) - set(fields))
        if unknown:
            valid = ", ".join(sorted(fields)) or "none"
            raise ValueError(f"unknown setting(s) {unknown} for {cls.id} (valid: {valid})")
        coerced = {k: _coerce(getattr(defaults, k), v) for k, v in overrides.items()}
        return dataclasses.replace(defaults, **coerced)


Check.Settings = dataclasses.dataclass(frozen=True)(Check.Settings)


# -- Function shortcut -----------------------------------------------------------


def check(
    fn: Callable[[Context], Any] | None = None,
    /,
    *,
    id: str | None = None,
    label: str | None = None,
    category: str = "General",
    hosts: Iterable[str] | str | None = None,
    tasks: Iterable[str] | str | None = None,
    asset_types: Iterable[str] | str | None = None,
    severity: Severity | str = Severity.ERROR,
    enabled: bool = True,
    order: int = 0,
    settings: Mapping[str, Any] | None = None,
) -> Any:
    """Turn a plain function into a :class:`Check`.

    ::

        @check(category="Hierarchy")
        def root_not_empty(ctx):
            \"\"\"The asset root must contain something.\"\"\"
            if not ctx.host.children(ctx.root):
                yield "The asset root is empty"

        @root_not_empty.fixer          # optional
        def _(ctx, issues): ...

    The function receives the :class:`Context`; settings given here are read
    via ``ctx.settings``. The decorated name becomes the generated Check class.
    """

    def wrap(func: Callable[[Context], Any]) -> type[Check]:
        module = func.__module__
        namespace: dict[str, Any] = {
            "__module__": module,
            "__qualname__": _camel(func.__name__),
            "__doc__": func.__doc__,
            "id": id or f"{module.rpartition('.')[2]}.{func.__name__}",
            "label": label or humanize(func.__name__),
            "category": category,
            "hosts": hosts,
            "tasks": tasks,
            "asset_types": asset_types,
            "severity": severity,
            "enabled": enabled,
            "order": order,
            "validate": lambda self, ctx: func(ctx),
        }
        if settings:
            namespace["Settings"] = type("Settings", (), dict(settings))
        cls = type(_camel(func.__name__), (Check,), namespace)

        def fixer(fix_func: Callable[[Context, list[Issue]], Any]) -> Callable:
            cls.fix = lambda self, ctx, issues: fix_func(ctx, issues)
            return fix_func

        cls.fixer = staticmethod(fixer)
        return cls

    return wrap(fn) if fn is not None else wrap


# -- Internals -------------------------------------------------------------------


def make_settings_class(source: type, owner: type) -> type:
    """Turn a user's plain ``class Settings`` into a frozen dataclass.

    Forgiving on purpose: annotations are optional, and list/set/dict defaults
    are allowed (lists and sets become tuples and frozensets).
    """
    if dataclasses.is_dataclass(source) and source.__dict__.get("__dataclass_params__"):
        return source

    specs: dict[str, tuple[Any, Any]] = {}
    for base in reversed(source.__mro__[1:]):
        if dataclasses.is_dataclass(base):
            defaults = base()
            for f in dataclasses.fields(base):
                specs[f.name] = (f.type, getattr(defaults, f.name))

    annotations = inspect.get_annotations(source)
    own = {
        k: v
        for k, v in vars(source).items()
        if not k.startswith("_")
        and not callable(v)
        and not isinstance(v, (classmethod, staticmethod, property))
    }
    for name in [*annotations, *[k for k in own if k not in annotations]]:
        if name not in own:
            raise TypeError(f"{owner.__name__}.Settings.{name} needs a default value")
        value = own[name]
        if isinstance(value, list):
            value = tuple(value)
        elif isinstance(value, set):
            value = frozenset(value)
        specs[name] = (annotations.get(name, type(value).__name__), value)

    fields = []
    for name, (annotation, value) in specs.items():
        if isinstance(value, dict):
            spec = dataclasses.field(default_factory=lambda v=value: dict(v))
        else:
            spec = dataclasses.field(default=value)
        fields.append((name, annotation, spec))

    methods = {k: v for k, v in vars(source).items() if callable(v) and not k.startswith("__")}
    settings = dataclasses.make_dataclass("Settings", fields, frozen=True, namespace=methods)
    settings.__module__ = owner.__module__
    settings.__qualname__ = f"{owner.__qualname__}.Settings"
    return settings


def default_id(cls: type) -> str:
    return f"{cls.__module__.rpartition('.')[2]}.{snake(cls.__name__)}"


def snake(name: str) -> str:
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def humanize(name: str) -> str:
    """``UnitScale`` / ``unit_scale`` -> ``Unit Scale``.

    Acronyms survive: ``UVNaming`` -> ``UV Naming``.
    """
    if "_" in name or name.islower():
        return " ".join(part.capitalize() for part in name.split("_") if part)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part) or name


def _as_set(value: Any) -> frozenset[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return frozenset({value})
    return frozenset(value)


def _matches(allowed: frozenset[str] | None, value: str | None) -> bool:
    return allowed is None or value in allowed


def _coerce(default: Any, value: Any) -> Any:
    """Make TOML values fit the setting's default type where that is unambiguous."""
    if isinstance(default, float) and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(default, tuple) and isinstance(value, list):
        return tuple(value)
    if isinstance(default, frozenset) and isinstance(value, list):
        return frozenset(value)
    return value
