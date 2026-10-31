"""The Blender sidebar panel (View3D > N > Validate).

This file only calls the Validator and draws what it returns. All the
validation logic lives in core/.
"""

import textwrap
from pathlib import Path

import bpy

from ...core.config import ConfigError
from ...core.results import BLOCKING, ERRORED, FAILED, FIXED, PASSED, SKIPPED, WARNING
from ...core.subject import ResolveError
from ...core.validator import Validator
from . import icons
from .host import BlenderHost

MAX_ISSUE_LINES = 25

# Worst first. Decides each category's icon and the order of checks inside it.
WORST_FIRST = [ERRORED, FAILED, WARNING, FIXED, PASSED, SKIPPED, "not_run"]

# Which icon an issue gets, from its severity.
ISSUE_ICONS = {"error": FAILED, "warning": WARNING, "info": PASSED}


class PanelState:
    """What the panel remembers. Blender panels can't hold Python objects themselves."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.validator = None
        self.report = None
        self.message = ""
        self.unticked = set()  # optional checks the artist switched off, this session only
        self.active_check = ""  # the check shown in the detail box
        self.stale = False  # the asset changed after it was validated
        self.root = None  # the asset root the report is about
        self.fingerprint = None  # the asset's fingerprint when it was validated

    def get_validator(self):
        if self.validator is None:
            try:
                self.validator = Validator(BlenderHost())
            except ConfigError as error:
                self.message = str(error)
        return self.validator

    def store_report(self, subject, report):
        self.report = report
        self.stale = False
        self.root = subject.root
        self.fingerprint = BlenderHost().fingerprint(subject.root)
        names = [result.check_id for result in report.results]
        if self.active_check not in names:
            problems = [r.check_id for r in report.results if r.status in BLOCKING]
            self.active_check = (problems or names or [""])[0]


state = PanelState()


def redraw_panels(context=None):
    context = context or bpy.context
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def selected_subject(validator):
    """The asset for the current selection, or (None, message)."""
    try:
        return validator.resolve(), ""
    except ResolveError as error:
        return None, str(error)


def ticked_checks(validator, subject):
    return [
        check.__name__ for check in validator.plan(subject) if check.__name__ not in state.unticked
    ]


def current_results(subject):
    """The last results, if they are for the asset that's selected now."""
    if state.report is None or subject is None or state.report.subject_name != subject.name:
        return {}
    return {result.check_id: result for result in state.report.results}


# -- Operators ---------------------------------------------------------------------


class PV_OT_validate(bpy.types.Operator):
    """Check the selected asset"""

    bl_idname = "publish_validator.validate"
    bl_label = "Validate"
    bl_options = {"REGISTER", "UNDO"}

    fix: bpy.props.BoolProperty(name="Fix", default=False, options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        if properties.fix:
            return "Fix every ticked check that can fix itself, then check everything again"
        return "Run every ticked check on the selected asset"

    def execute(self, context):
        validator = state.get_validator()
        if validator is None:
            self.report({"ERROR"}, state.message)
            return {"CANCELLED"}

        subject, message = selected_subject(validator)
        if subject is None:
            self.report({"WARNING"}, message)
            return {"CANCELLED"}

        only = ticked_checks(validator, subject)
        report = validator.run(subject, fix=self.fix, only=only)
        state.store_report(subject, report)
        level = "INFO" if report.passed else "WARNING"
        self.report({level}, f"{subject.name}: {report.summary()}")
        redraw_panels(context)
        return {"FINISHED"}


class PV_OT_fix_one(bpy.types.Operator):
    """Fix just this check, then check it again"""

    bl_idname = "publish_validator.fix_one"
    bl_label = "Fix"
    bl_options = {"REGISTER", "UNDO"}

    check_id: bpy.props.StringProperty()

    def execute(self, context):
        validator = state.get_validator()
        subject, message = selected_subject(validator)
        if subject is None or state.report is None:
            self.report({"WARNING"}, message or "Validate first.")
            return {"CANCELLED"}

        result = validator.run_one(self.check_id, subject, fix=True)
        state.report.replace(result)
        state.store_report(subject, state.report)
        self.report({"INFO"}, f"{result.label}: {result.status}")
        redraw_panels(context)
        return {"FINISHED"}


class PV_OT_toggle_check(bpy.types.Operator):
    """Include or skip this check when validating"""

    bl_idname = "publish_validator.toggle_check"
    bl_label = "Include Check"
    bl_options = {"INTERNAL"}

    check_id: bpy.props.StringProperty()

    def execute(self, context):
        if self.check_id in state.unticked:
            state.unticked.remove(self.check_id)
        else:
            state.unticked.add(self.check_id)
        redraw_panels(context)
        return {"FINISHED"}


class PV_OT_tick_all(bpy.types.Operator):
    """Tick or untick every check"""

    bl_idname = "publish_validator.tick_all"
    bl_label = "Tick All"
    bl_options = {"INTERNAL"}

    tick: bpy.props.BoolProperty(default=True)

    @classmethod
    def description(cls, context, properties):
        return "Tick every check" if properties.tick else "Untick every check"

    def execute(self, context):
        if self.tick:
            state.unticked.clear()
        else:
            validator = state.get_validator()
            subject, message = selected_subject(validator)
            if subject is None:
                self.report({"WARNING"}, message)
                return {"CANCELLED"}
            state.unticked = {check.__name__ for check in validator.plan(subject)}
        redraw_panels(context)
        return {"FINISHED"}


class PV_OT_set_active(bpy.types.Operator):
    """Show this check's details"""

    bl_idname = "publish_validator.set_active"
    bl_label = "Show Details"
    bl_options = {"INTERNAL"}

    check_id: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        # The tooltip is the check's own docstring.
        validator = state.get_validator()
        for check in validator.checks if validator else []:
            if check.__name__ == properties.check_id and check.description():
                return check.description()
        return cls.__doc__

    def execute(self, context):
        state.active_check = self.check_id
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


# -- Panel ---------------------------------------------------------------------------


class PV_PT_panel(bpy.types.Panel):
    bl_label = "Publish Validator"
    bl_idname = "PV_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Validate"

    def draw(self, context):
        layout = self.layout
        validator = state.get_validator()
        if validator is None:
            layout.label(text=state.message, icon="ERROR")
            return

        subject, message = selected_subject(validator)
        results = current_results(subject)

        self.draw_asset(layout, subject, message)
        if subject is not None:
            # What each row shows; unticked checks count as skipped.
            shown = [status_of(check, results) for check in validator.plan(subject)]
            self.draw_buttons(layout, results, shown)
            self.draw_banners(layout, subject)
            self.draw_checks(layout, validator, subject, results)
            self.draw_details(context, layout, validator, subject, results)
        self.draw_load_errors(layout, validator)

    def draw_asset(self, layout, subject, message):
        box = layout.box()
        if subject is None:
            box.label(text=message, icon="INFO")
            return
        row = box.row()
        row.label(text=subject.name, icon="OUTLINER_OB_EMPTY")
        kind = row.row()
        kind.alignment = "RIGHT"
        kind.label(text=f"{subject.asset_type or '?'} · {subject.task or '?'}")

    def draw_buttons(self, layout, results, shown):
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("publish_validator.validate", text="Validate", icon="CHECKMARK").fix = False
        fixable = [r for r in results.values() if r.can_fix and r.status in (FAILED, WARNING)]
        fix_all = row.row(align=True)
        fix_all.enabled = bool(fixable)
        label = f"Fix All ({len(fixable)})" if fixable else "Fix All"
        fix_all.operator("publish_validator.validate", text=label, icon="TOOL_SETTINGS").fix = True

        if results:
            # Counts on the left, the verdict on the right with enough room to fit.
            summary = layout.row().split(factor=0.62)
            counts = summary.row(align=True)
            counts.alignment = "LEFT"
            # Fixed counts as passed: both are green. Skipped checks are left out;
            # they're already greyed out in the list.
            totals = {
                PASSED: shown.count(PASSED) + shown.count(FIXED),
                WARNING: shown.count(WARNING),
                FAILED: shown.count(FAILED),
                ERRORED: shown.count(ERRORED),
            }
            for status, count in totals.items():
                if count:
                    counts.label(text=str(count), **icons.status_icon(status))
                    counts.separator(factor=0.5)
            verdict = summary.row()
            verdict.alignment = "RIGHT"
            blocked = any(status in BLOCKING for status in shown)
            verdict.alert = blocked
            verdict.label(text="Errors to fix" if blocked else "No errors")

    def draw_banners(self, layout, subject):
        if state.report is None:
            return
        if state.report.subject_name != subject.name:
            box = layout.box()
            box.label(text=f"Results are for {state.report.subject_name}.", icon="INFO")
            box.label(text="Validate again to check this asset.")
        elif state.stale:
            box = layout.box()
            box.alert = True
            box.label(text="Asset changed since validating.", icon="ERROR")
            box.label(text="Validate again before publishing.", icon="BLANK1")

    def draw_checks(self, layout, validator, subject, results):
        row = layout.row()
        row.label(text="Checks")
        ticks = row.row(align=True)
        ticks.alignment = "RIGHT"
        ticks.operator("publish_validator.tick_all", text="Tick All").tick = True
        ticks.operator("publish_validator.tick_all", text="Untick All").tick = False

        by_category = {}
        for check in validator.plan(subject):
            by_category.setdefault(check.category, []).append(check)

        for category in sorted(by_category):
            checks = by_category[category]
            statuses = [status_of(check, results) for check in checks]
            all_good = all(status in (PASSED, FIXED, SKIPPED) for status in statuses)

            # Each category is a framed box: its header on top, its checks inside.
            box = layout.box()
            header, body = box.panel(f"pv_category_{category}", default_closed=all_good)
            header.label(text=category)
            counts = header.row(align=True)
            counts.alignment = "RIGHT"
            for status in (PASSED, WARNING, FAILED):
                count = statuses.count(status) + (statuses.count(FIXED) if status == PASSED else 0)
                if count:
                    counts.label(text=str(count), **icons.status_icon(status))
            if body is None:
                continue

            ordered = sorted(
                checks,
                key=lambda check: (WORST_FIRST.index(status_of(check, results)), check.label),
            )
            column = body.column(align=True)
            for check in ordered:
                result = results.get(check.__name__)
                self.draw_check_row(column, check, result, status_of(check, results))

    def draw_check_row(self, layout, check, result, status):
        name = check.__name__
        active = name == state.active_check
        row = layout.row(align=True)
        row.separator(factor=1.0)  # indent checks under their category

        icon = "CHECKBOX_DEHLT" if name in state.unticked else "CHECKBOX_HLT"
        toggle = row.operator("publish_validator.toggle_check", text="", icon=icon, emboss=False)
        toggle.check_id = name

        # Name on the left, buttons on the right. The arrow and the name both show
        # the check's details; the active check is drawn pressed.
        label = row.row(align=True)
        label.alignment = "LEFT"
        label.active = status != SKIPPED
        # The arrow comes first so a long name can never push it out of view.
        arrow = "DISCLOSURE_TRI_DOWN" if active else "DISCLOSURE_TRI_RIGHT"
        open_details = label.operator(
            "publish_validator.set_active", text="", icon=arrow, emboss=False
        )
        open_details.check_id = name
        details = label.operator(
            "publish_validator.set_active",
            text=check.label,
            emboss=active,
            depress=active,
            **icons.status_icon(status),
        )
        details.check_id = name

        buttons = row.row(align=True)
        buttons.alignment = "RIGHT"
        if result and result.can_fix and status in (FAILED, WARNING):
            fix = buttons.operator("publish_validator.fix_one", text="", icon="TOOL_SETTINGS")
            fix.check_id = name
        if result and result.targets and status != SKIPPED:
            select = buttons.operator(
                "publish_validator.select", text="", icon="RESTRICT_SELECT_OFF"
            )
            select.check_id = name

    def draw_details(self, context, layout, validator, subject, results):
        check = next((c for c in validator.plan(subject) if c.__name__ == state.active_check), None)
        if check is None:
            return
        result = results.get(check.__name__)

        # A framed, collapsible section like the categories, titled "Details".
        frame = layout.box()
        header, box = frame.panel("pv_details", default_closed=False)
        header.label(text="Details")
        if box is None:
            return
        box.label(text=check.label, **icons.status_icon(status_of(check, results)))

        # Labels don't wrap, so wrap text to the sidebar's width ourselves.
        width = max(24, int(context.region.width / (7.5 * context.preferences.system.ui_scale)))
        text = box.column(align=True)
        text.scale_y = 0.8
        for paragraph in check.description().split("\n\n"):
            for line in textwrap.wrap(" ".join(paragraph.split()), width):
                text.label(text=line)

        if result is None:
            box.label(text="Not run yet.")
            return
        if result.status == SKIPPED:
            box.label(text=f"Skipped: {result.skip_reason}.", **icons.status_icon(SKIPPED))
        if result.error:
            box.label(text=result.short_error, **icons.status_icon(ERRORED))

        if result.issues:
            box.separator()
            box.label(text=f"Problems ({len(result.issues)})")
            issues = box.column(align=True)
            for issue in result.issues[:MAX_ISSUE_LINES]:
                # Leave room for the icon.
                lines = textwrap.wrap(issue.message, width - 6) or [""]
                icon = icons.status_icon(ISSUE_ICONS.get(issue.severity, FAILED))
                issues.label(text=lines[0], **icon)
                for line in lines[1:]:
                    issues.label(text=line, icon="BLANK1")
            if len(result.issues) > MAX_ISSUE_LINES:
                issues.label(text=f"... and {len(result.issues) - MAX_ISSUE_LINES} more")

        if result.fixed_issues:
            box.separator()
            box.label(text=f"Fixed ({len(result.fixed_issues)})")
            fixed = box.column(align=True)
            for issue in result.fixed_issues:
                fixed.label(text=issue.message, **icons.status_icon(FIXED))

        if result.status == PASSED:
            box.separator()
            box.label(text="No problems found.", **icons.status_icon(PASSED))

    def draw_load_errors(self, layout, validator):
        errors = validator.load_errors
        if errors:
            header, body = layout.panel("pv_load_errors", default_closed=True)
            header.label(text=f"{len(errors)} loading problem(s)", icon="ERROR")
            if body is not None:
                for error in errors:
                    body.label(text=f"{Path(error.source).name}: {error.short_message}")
        row = layout.row()
        row.alignment = "RIGHT"
        row.operator("publish_validator.reload", text="", icon="FILE_REFRESH", emboss=False)


def status_of(check, results):
    result = results.get(check.__name__)
    if result is None:
        return "not_run"
    if result.status == SKIPPED or check.__name__ in state.unticked:
        return SKIPPED
    return result.status


# -- Keeping results honest ------------------------------------------------------------


@bpy.app.handlers.persistent
def mark_stale(scene, depsgraph):
    """After a change to the validated asset, mark the results as out of date."""
    if state.report is None or state.stale or state.root is None:
        return
    try:
        changed = BlenderHost().fingerprint(state.root) != state.fingerprint
    except ReferenceError:  # the asset root was deleted
        changed = True
    if changed:
        state.stale = True
        redraw_panels()


@bpy.app.handlers.persistent
def forget_results(*args):
    """A different file was opened: the old results mean nothing now."""
    state.report = None
    state.root = None
    state.stale = False
    state.active_check = ""


CLASSES = [
    PV_OT_validate,
    PV_OT_fix_one,
    PV_OT_toggle_check,
    PV_OT_tick_all,
    PV_OT_set_active,
    PV_OT_select,
    PV_OT_reload,
    PV_PT_panel,
]
HANDLERS = [
    (bpy.app.handlers.depsgraph_update_post, mark_stale),
    (bpy.app.handlers.load_post, forget_results),
]


def register():
    icons.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    for handlers, function in HANDLERS:
        if function not in handlers:
            handlers.append(function)


def unregister():
    for handlers, function in HANDLERS:
        if function in handlers:
            handlers.remove(function)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    icons.unregister()
    state.reset()
