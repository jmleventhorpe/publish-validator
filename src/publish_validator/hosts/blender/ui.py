"""Minimal native Blender UI: a sidebar panel (View3D > N > Validate).

The UI only talks to :class:`~publish_validator.Validator` and reads the
resulting :class:`~publish_validator.Report`; it holds no validation logic.
"""

from __future__ import annotations

from itertools import groupby

import bpy

from ...core.model import Report, Status
from ...core.subject import ResolveError
from ...core.validator import Validator
from .host import BlenderHost

ISSUE_LINES = 25

_STATUS_ICONS = {
    Status.PASSED: "CHECKMARK",
    Status.WARNING: "ERROR",
    Status.FAILED: "CANCEL",
    Status.FIXED: "CHECKMARK",
    Status.ERRORED: "QUESTION",
    Status.SKIPPED: "RADIOBUT_OFF",
}


class _State:
    validator: Validator | None = None
    report: Report | None = None
    message: str = ""
    expanded: set[str] = set()

    @classmethod
    def get_validator(cls) -> Validator:
        if cls.validator is None:
            cls.validator = Validator(BlenderHost())
        return cls.validator


def _redraw(context: bpy.types.Context) -> None:
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class PV_OT_validate(bpy.types.Operator):
    """Validate the selected asset"""

    bl_idname = "publish_validator.validate"
    bl_label = "Validate"
    bl_options = {"REGISTER", "UNDO"}

    fix: bpy.props.BoolProperty(name="Fix", default=False, options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        if properties.fix:
            return "Validate, automatically fix what can be fixed, then validate again"
        return "Run every check that applies to the selected asset"

    def execute(self, context):
        validator = _State.get_validator()
        try:
            subject = validator.resolve()
        except ResolveError as exc:
            _State.message = str(exc)
            self.report({"WARNING"}, str(exc))
            _redraw(context)
            return {"CANCELLED"}

        report = validator.run(subject, fix=self.fix)
        _State.report, _State.message = report, ""
        _State.expanded = {r.check_id for r in report.results if r.status.blocking}
        counts = report.counts()
        summary = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
        self.report({"INFO" if report.passed else "WARNING"}, f"{subject.name}: {summary}")
        _redraw(context)
        return {"FINISHED"}


class PV_OT_select(bpy.types.Operator):
    """Select the objects this check complained about"""

    bl_idname = "publish_validator.select"
    bl_label = "Select Issues"
    bl_options = {"REGISTER", "UNDO"}

    check_id: bpy.props.StringProperty()

    def execute(self, context):
        result = _State.report and _State.report.get(self.check_id)
        if result is None or not result.targets:
            return {"CANCELLED"}
        try:
            _State.get_validator().select(result)
        except ReferenceError:
            self.report({"WARNING"}, "Objects changed since validation; validate again")
            return {"CANCELLED"}
        return {"FINISHED"}


class PV_OT_toggle(bpy.types.Operator):
    """Show or hide this check's details"""

    bl_idname = "publish_validator.toggle"
    bl_label = "Toggle Details"
    bl_options = {"INTERNAL"}

    check_id: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        result = _State.report and _State.report.get(properties.check_id)
        return (result.description if result else "") or cls.__doc__

    def execute(self, context):
        _State.expanded ^= {self.check_id}
        _redraw(context)
        return {"FINISHED"}


class PV_OT_reload(bpy.types.Operator):
    """Reload config and re-import every check (for check authors)"""

    bl_idname = "publish_validator.reload"
    bl_label = "Reload Checks"

    def execute(self, context):
        _State.validator = Validator(BlenderHost())
        _State.report = None
        n = len(_State.validator.registry)
        self.report({"INFO"}, f"Loaded {n} checks")
        _redraw(context)
        return {"FINISHED"}


class PV_PT_panel(bpy.types.Panel):
    bl_label = "Publish Validator"
    bl_idname = "PV_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Validate"

    def draw(self, context):
        layout = self.layout
        validator = _State.get_validator()

        try:
            subject = validator.resolve()
            info = f"{subject.name}  ({subject.asset_type or '?'} / {subject.task or '?'})"
            layout.label(text=info, icon="OBJECT_DATA")
        except ResolveError as exc:
            layout.label(text=str(exc), icon="INFO")
            subject = None

        row = layout.row(align=True)
        row.enabled = subject is not None
        row.scale_y = 1.4
        row.operator(PV_OT_validate.bl_idname, text="Validate", icon="CHECKMARK").fix = False
        row.operator(PV_OT_validate.bl_idname, text="Fix", icon="TOOL_SETTINGS").fix = True

        if _State.message:
            layout.label(text=_State.message, icon="ERROR")

        report = _State.report
        if report is not None:
            self.draw_report(layout, report)

        footer = layout.row()
        footer.alignment = "RIGHT"
        footer.operator(PV_OT_reload.bl_idname, text="", icon="FILE_REFRESH", emboss=False)

    def draw_report(self, layout, report: Report) -> None:
        header = layout.row()
        header.alert = not report.passed
        state = "Passed" if report.passed else "Blocked"
        header.label(text=f"{state}: {report.subject_name}")

        results = [r for r in report.results if r.status is not Status.SKIPPED]
        for category, group in groupby(
            sorted(results, key=lambda r: r.category), key=lambda r: r.category
        ):
            box = layout.box()
            box.label(text=category)
            for result in group:
                self.draw_result(box.column(align=True), result)

        if report.load_errors:
            box = layout.box()
            box.alert = True
            box.label(text=f"{len(report.load_errors)} load error(s), see console", icon="ERROR")
            for error in report.load_errors[:5]:
                box.label(text=f"{error.source}: {error.message}")

    def draw_result(self, col, result) -> None:
        expanded = result.check_id in _State.expanded
        has_details = bool(result.issues or result.fixed_issues or result.error)

        row = col.row(align=True)
        row.alert = result.status.blocking
        toggle = row.operator(
            PV_OT_toggle.bl_idname,
            text="",
            icon="DISCLOSURE_TRI_DOWN" if expanded else "DISCLOSURE_TRI_RIGHT",
            emboss=False,
        )
        toggle.check_id = result.check_id
        row.label(text=result.label, icon=_STATUS_ICONS[result.status])
        if result.targets:
            select = row.operator(PV_OT_select.bl_idname, text="", icon="RESTRICT_SELECT_OFF")
            select.check_id = result.check_id

        if not (expanded and has_details):
            return
        details = col.box().column(align=True)
        details.scale_y = 0.8
        for issue in result.issues[:ISSUE_LINES]:
            details.label(text=issue.message)
        if len(result.issues) > ISSUE_LINES:
            details.label(text=f"... and {len(result.issues) - ISSUE_LINES} more")
        for issue in result.fixed_issues[:ISSUE_LINES]:
            details.label(text=f"Fixed: {issue.message}", icon="CHECKMARK")
        if result.error:
            details.label(text=result.error.strip().splitlines()[-1], icon="ERROR")


CLASSES = (PV_OT_validate, PV_OT_select, PV_OT_toggle, PV_OT_reload, PV_PT_panel)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _State.validator = None
    _State.report = None
