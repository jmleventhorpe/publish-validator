"""The Blender sidebar panel (View3D > N > Validate).

This file only calls the Validator and draws the Report it returns. All the
validation logic lives in core/.
"""

import bpy

from ...core.config import ConfigError
from ...core.results import BLOCKING, ERRORED, FAILED, FIXED, PASSED, SKIPPED, WARNING
from ...core.subject import ResolveError
from ...core.validator import Validator
from .host import BlenderHost

MAX_ISSUE_LINES = 25

STATUS_ICONS = {
    PASSED: "CHECKMARK",
    FIXED: "CHECKMARK",
    WARNING: "ERROR",
    FAILED: "CANCEL",
    ERRORED: "QUESTION",
}


class PanelState:
    """What the panel remembers between clicks. Blender panels can't hold Python objects."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.validator = None
        self.report = None
        self.message = ""
        self.open_checks = set()  # checks whose details are expanded

    def get_validator(self):
        if self.validator is None:
            try:
                self.validator = Validator(BlenderHost())
            except ConfigError as error:
                self.message = str(error)
        return self.validator


state = PanelState()


def redraw_panels(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class PV_OT_validate(bpy.types.Operator):
    """Run every check that applies to the selected asset"""

    bl_idname = "publish_validator.validate"
    bl_label = "Validate"
    bl_options = {"REGISTER", "UNDO"}

    fix: bpy.props.BoolProperty(name="Fix", default=False, options={"SKIP_SAVE"})

    def execute(self, context):
        validator = state.get_validator()
        if validator is None:
            self.report({"ERROR"}, state.message)
            return {"CANCELLED"}

        try:
            subject = validator.resolve()
        except ResolveError as error:
            state.message = str(error)
            self.report({"WARNING"}, state.message)
            redraw_panels(context)
            return {"CANCELLED"}

        state.report = validator.run(subject, fix=self.fix)
        state.message = ""
        # Open the details of anything that failed.
        state.open_checks = {r.check_id for r in state.report.results if r.status in BLOCKING}

        level = "INFO" if state.report.passed else "WARNING"
        self.report({level}, f"{subject.name}: {state.report.summary()}")
        redraw_panels(context)
        return {"FINISHED"}


class PV_OT_select(bpy.types.Operator):
    """Select what this check found"""

    bl_idname = "publish_validator.select"
    bl_label = "Select"
    bl_options = {"REGISTER", "UNDO"}

    check_id: bpy.props.StringProperty()

    def execute(self, context):
        result = state.report.get(self.check_id) if state.report else None
        if result is None or not result.targets:
            return {"CANCELLED"}
        try:
            state.validator.select(result.targets)
        except ReferenceError:  # an object was deleted since validating
            self.report({"WARNING"}, "The scene has changed. Validate again.")
            return {"CANCELLED"}
        return {"FINISHED"}


class PV_OT_toggle(bpy.types.Operator):
    """Show or hide the details"""

    bl_idname = "publish_validator.toggle"
    bl_label = "Show Details"
    bl_options = {"INTERNAL"}

    check_id: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        # The tooltip is the check's docstring.
        result = state.report.get(properties.check_id) if state.report else None
        return result.description if result and result.description else cls.__doc__

    def execute(self, context):
        if self.check_id in state.open_checks:
            state.open_checks.remove(self.check_id)
        else:
            state.open_checks.add(self.check_id)
        redraw_panels(context)
        return {"FINISHED"}


class PV_OT_reload(bpy.types.Operator):
    """Reload the config and every check file (handy while writing checks)"""

    bl_idname = "publish_validator.reload"
    bl_label = "Reload Checks"

    def execute(self, context):
        state.reset()
        validator = state.get_validator()
        if validator is None:
            self.report({"ERROR"}, state.message)
            return {"CANCELLED"}
        self.report({"INFO"}, f"Loaded {len(validator.checks)} checks")
        redraw_panels(context)
        return {"FINISHED"}


class PV_PT_panel(bpy.types.Panel):
    bl_label = "Publish Validator"
    bl_idname = "PV_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Validate"

    def draw(self, context):
        layout = self.layout
        validator = state.get_validator()

        # Show which asset the buttons will validate.
        subject = None
        if validator is not None:
            try:
                subject = validator.resolve()
                kind = f"{subject.asset_type or '?'} / {subject.task or '?'}"
                layout.label(text=f"{subject.name}  ({kind})", icon="OBJECT_DATA")
            except ResolveError as error:
                layout.label(text=str(error), icon="INFO")

        row = layout.row(align=True)
        row.scale_y = 1.4
        row.enabled = subject is not None
        row.operator("publish_validator.validate", text="Validate", icon="CHECKMARK").fix = False
        row.operator("publish_validator.validate", text="Fix", icon="TOOL_SETTINGS").fix = True

        if state.message:
            layout.label(text=state.message, icon="ERROR")

        if state.report:
            self.draw_report(layout, state.report)

        footer = layout.row()
        footer.alignment = "RIGHT"
        footer.operator("publish_validator.reload", text="", icon="FILE_REFRESH", emboss=False)

    def draw_report(self, layout, report):
        header = layout.row()
        header.alert = not report.passed
        header.label(text=("Passed: " if report.passed else "Blocked: ") + report.subject_name)

        by_category = {}
        for result in report.results:
            if result.status != SKIPPED:
                by_category.setdefault(result.category, []).append(result)

        for category in sorted(by_category):
            box = layout.box()
            box.label(text=category)
            for result in by_category[category]:
                self.draw_result(box.column(align=True), result)

        if report.load_errors:
            box = layout.box()
            box.alert = True
            box.label(text=f"{len(report.load_errors)} loading problem(s):", icon="ERROR")
            for error in report.load_errors[:5]:
                box.label(text=f"{error.source}: {error.short_message}")

    def draw_result(self, column, result):
        is_open = result.check_id in state.open_checks

        row = column.row(align=True)
        row.alert = result.status in BLOCKING
        arrow = "DISCLOSURE_TRI_DOWN" if is_open else "DISCLOSURE_TRI_RIGHT"
        toggle = row.operator("publish_validator.toggle", text="", icon=arrow, emboss=False)
        toggle.check_id = result.check_id

        row.label(text=result.label, icon=STATUS_ICONS[result.status])

        if result.targets:
            select = row.operator("publish_validator.select", text="", icon="RESTRICT_SELECT_OFF")
            select.check_id = result.check_id

        if not is_open:
            return
        details = column.box().column(align=True)
        details.scale_y = 0.8
        for issue in result.issues[:MAX_ISSUE_LINES]:
            details.label(text=issue.message)
        if len(result.issues) > MAX_ISSUE_LINES:
            details.label(text=f"... and {len(result.issues) - MAX_ISSUE_LINES} more")
        for issue in result.fixed_issues:
            details.label(text=f"Fixed: {issue.message}", icon="CHECKMARK")
        if result.error:
            details.label(text=result.short_error, icon="ERROR")
        if not (result.issues or result.fixed_issues or result.error):
            details.label(text=result.description.split("\n")[0] or "No problems found.")


CLASSES = [PV_OT_validate, PV_OT_select, PV_OT_toggle, PV_OT_reload, PV_PT_panel]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    state.reset()
