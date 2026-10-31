from publish_validator import Check


class AllowedObjectTypes(Check):
    """Only allowed object types may be inside the asset.

    Cameras, lights and similar objects inside an asset end up in every shot
    that uses it. Delete them or move them out of the asset.
    """

    category = "Structure"
    hosts = ["blender"]
    tasks = ["model"]
    settings = {"allowed": ["MESH", "EMPTY"]}

    def validate(self, ctx):
        for obj in ctx.host.descendants(ctx.root):
            if obj.type not in self.settings["allowed"]:
                yield self.issue(f"{obj.name} is a {obj.type.lower()} object", obj)


class GeoChildren(Check):
    """Meshes shouldn't have other meshes parented under them.

    Geometry belongs under groups (empties), not under other geometry, so each
    piece can be moved, hidden and exported on its own. Re-parent the child
    meshes to a group.
    """

    category = "Structure"
    hosts = ["blender"]
    tasks = ["model"]

    def validate(self, ctx):
        for obj in ctx.host.meshes(ctx.root):
            children = [child.name for child in obj.children if child.type == "MESH"]
            if children:
                yield self.issue(f"{obj.name} has meshes under it: {', '.join(children)}", obj)
