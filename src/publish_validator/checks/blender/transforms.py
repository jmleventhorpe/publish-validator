from publish_validator import Check


class UnitScale(Check):
    """Mesh objects must have a scale of 1.

    Unapplied scale distorts modifiers, physics and exports to other packages.
    To fix by hand: Object > Apply > Scale.
    """

    category = "Transforms"
    hosts = ["blender"]
    tasks = ["model"]
    settings = {"tolerance": 0.000001}

    def validate(self, ctx):
        for obj in ctx.host.meshes(ctx.root):
            if any(abs(value - 1) > self.settings["tolerance"] for value in obj.scale):
                scale = ", ".join(f"{value:g}" for value in obj.scale)
                yield self.issue(f"{obj.name} has a scale of ({scale})", obj)

    def fix(self, ctx, issues):
        for issue in issues:
            ctx.host.apply_scale(issue.targets)
