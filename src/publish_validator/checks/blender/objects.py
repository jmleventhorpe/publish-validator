from publish_validator import Check


class AllowedObjectTypes(Check):
    """Only allowed object types may be inside the asset."""

    category = "Objects"
    hosts = ["blender"]
    tasks = ["model"]
    settings = {"allowed": ["MESH", "EMPTY"]}

    def validate(self, ctx):
        for obj in ctx.host.descendants(ctx.root):
            if obj.type not in self.settings["allowed"]:
                yield self.issue(f"{obj.name} is a {obj.type.lower()} object", obj)
