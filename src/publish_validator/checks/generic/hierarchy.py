from publish_validator import Check


class RootNotEmpty(Check):
    """The asset root must contain something.

    An empty root usually means the wrong node was marked as the asset, or the
    geometry is parented somewhere else. Parent the asset's content under it.
    """

    category = "Structure"

    def validate(self, ctx):
        if not ctx.host.children(ctx.root):
            yield f"The asset root '{ctx.host.node_name(ctx.root)}' is empty."


class GroupSetup(Check):
    """The asset must use the standard group layout.

    asset root > geo > render (the render geometry) and proxy (the light
    version), plus simproxy next to geo. This is the layout USD assets use,
    and the publish relies on it. Add or rename groups to match.
    """

    category = "Structure"
    tasks = ["model"]
    settings = {
        "required_top": ["geo", "simproxy"],
        "optional_top": ["utils", "temp"],
        "required_geo": ["proxy", "render"],
    }

    def validate(self, ctx):
        host = ctx.host
        top = {host.node_name(child): child for child in host.children(ctx.root)}
        allowed_top = self.settings["required_top"] + self.settings["optional_top"]

        for name in self.settings["required_top"]:
            if name not in top:
                yield self.issue(f"The asset root has no '{name}' group", ctx.root)
        for name, node in top.items():
            if name not in allowed_top:
                yield self.issue(f"'{name}' shouldn't be directly under the asset root", node)

        if "geo" not in top:
            return
        inside_geo = {host.node_name(child): child for child in host.children(top["geo"])}
        for name in self.settings["required_geo"]:
            if name not in inside_geo:
                yield self.issue(f"'geo' has no '{name}' group", top["geo"])
        for name, node in inside_geo.items():
            if name not in self.settings["required_geo"]:
                yield self.issue(f"'{name}' shouldn't be directly under 'geo'", node)
