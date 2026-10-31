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


class ZeroTransforms(Check):
    """Every object's origin must sit at the world centre, unrotated.

    In Blender the origin is the pivot, so this is also the "pivots at zero"
    rule. It looks at the final world position, so parents and delta
    transforms count too. Scale is covered by Unit Scale. To fix by hand:
    Object > Apply > Location and Rotation.
    """

    category = "Transforms"
    hosts = ["blender"]
    tasks = ["model"]
    settings = {"tolerance": 0.0001}

    def validate(self, ctx):
        tolerance = self.settings["tolerance"]
        for obj in [ctx.root, *ctx.host.descendants(ctx.root)]:
            location, rotation, _ = obj.matrix_world.decompose()
            problems = []
            if location.length > tolerance:
                problems.append("moved " + ", ".join(f"{value:g}" for value in location))
            if rotation.angle > tolerance:
                problems.append(f"rotated {rotation.angle * 57.29578:g}°")
            if problems:
                yield self.issue(f"{obj.name} is {' and '.join(problems)}", obj)


class HasAnimation(Check):
    """A model shouldn't carry animation.

    Keyframes or drivers on a model move it in every shot that uses it. Clear
    them with Object > Animation > Clear Keyframes, and remove any drivers.
    """

    category = "Transforms"
    hosts = ["blender"]
    tasks = ["model"]

    def validate(self, ctx):
        for obj in [ctx.root, *ctx.host.descendants(ctx.root)]:
            animation = obj.animation_data
            if animation is None:
                continue
            found = []
            if animation.action:
                found.append("keyframes")
            if animation.drivers:
                found.append("drivers")
            if animation.nla_tracks:
                found.append("NLA tracks")
            if found:
                yield self.issue(f"{obj.name} has {', '.join(found)}", obj)
