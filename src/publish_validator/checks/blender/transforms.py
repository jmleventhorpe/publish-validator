"""Transform checks for Blender."""

from publish_validator import Check


class UnitScale(Check):
    """Mesh objects must have a scale of (1, 1, 1).

    Unapplied scale distorts modifiers, physics and exports to other packages.
    Fix by hand with Object > Apply > Scale.
    """

    category = "Transforms"
    hosts = {"blender"}
    tasks = {"model"}

    class Settings:
        tolerance = 1e-6

    def validate(self, ctx):
        tolerance = self.settings.tolerance
        for obj in ctx.host.meshes(ctx.root):
            if any(abs(value - 1.0) > tolerance for value in obj.scale):
                scale = ", ".join(f"{v:g}" for v in obj.scale)
                yield self.issue(f"{obj.name} has scale ({scale})", obj)

    def fix(self, ctx, issues):
        for issue in issues:
            ctx.host.apply_scale(issue.targets)
