from publish_validator import Check


class RootNotEmpty(Check):
    """The asset root must contain something.

    An empty root usually means the wrong node was marked as the asset, or the
    geometry is parented somewhere else. Parent the asset's content under it.
    """

    category = "Hierarchy"

    def validate(self, ctx):
        if not ctx.host.children(ctx.root):
            yield f"The asset root '{ctx.host.node_name(ctx.root)}' is empty."
