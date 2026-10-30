"""Hierarchy checks that only use the generic Host API, so they run in any host."""

from publish_validator import check


@check(category="Hierarchy")
def root_not_empty(ctx):
    """The asset root must contain something.

    An empty root usually means the wrong node was marked as the asset, or the
    geometry was parented somewhere else. Parent the asset's content under it.
    """
    if not ctx.host.children(ctx.root):
        yield f"Asset root '{ctx.host.node_name(ctx.root)}' has no children."
