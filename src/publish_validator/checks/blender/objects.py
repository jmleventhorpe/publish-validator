"""Object-level checks for Blender."""

from publish_validator import Check


class AllowedObjectTypes(Check):
    """Only allowed object types may live under the asset root.

    Cameras, lights and similar objects inside an asset end up in every shot
    that uses it. Delete them or move them out of the asset hierarchy.
    """

    category = "Objects"
    hosts = {"blender"}
    tasks = {"model"}

    class Settings:
        allowed = ["MESH", "EMPTY"]

    def validate(self, ctx):
        allowed = set(self.settings.allowed)
        for obj in ctx.host.descendants(ctx.root):
            if obj.type not in allowed:
                yield self.issue(f"{obj.name} is a {obj.type.lower()} object", obj)
