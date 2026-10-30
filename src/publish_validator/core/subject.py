"""The asset being validated (the "subject") and how it is found in the scene.

A resolver turns the selection into a Subject. The default PropertyResolver reads
custom properties from the asset's root node. A studio with its own pipeline can
write a resolver with the same two methods and name it in config:

    resolver = "my_pipeline.validator:PipelineResolver"
"""

from dataclasses import dataclass, field


@dataclass
class Subject:
    name: str
    asset_type: str | None  # e.g. "prop", used to pick checks
    task: str | None  # e.g. "model", used to pick checks
    root: object  # the top node of the asset
    extras: dict = field(default_factory=dict)  # anything else a resolver knows


class ResolveError(Exception):
    """No asset could be found. The message is shown to the artist."""


class PropertyResolver:
    """Finds asset roots by their custom properties.

        pv_task        "model"   (required, marks the node as an asset root)
        pv_asset_type  "prop"
        pv_asset_name  "chair"   (defaults to the node's name)

    Selecting anything inside an asset finds its root.
    """

    prefix = "pv_"

    def resolve(self, host, node=None):
        """The subject for a node, or for the selection if no node is given."""
        candidates = [node] if node is not None else host.selection()
        if not candidates:
            raise ResolveError(
                f"Select an asset root (a node with a '{self.prefix}task' property)."
            )

        roots = []
        for candidate in candidates:
            root = self.find_root(host, candidate)
            if root is not None and root not in roots:
                roots.append(root)

        if not roots:
            raise ResolveError(
                f"The selection isn't part of an asset. "
                f"Asset roots have a '{self.prefix}task' property."
            )
        if len(roots) > 1:
            names = ", ".join(host.node_name(root) for root in roots)
            raise ResolveError(f"The selection covers several assets ({names}). Select one.")
        return self.make_subject(host, roots[0])

    def find_all(self, host):
        """Every asset in the scene."""
        roots = host.find_by_property(self.prefix + "task")
        return [self.make_subject(host, root) for root in roots]

    def find_root(self, host, node):
        """Walk up from a node until we reach an asset root."""
        while node is not None:
            if host.get_property(node, self.prefix + "task") is not None:
                return node
            node = host.parent(node)
        return None

    def make_subject(self, host, root):
        name = host.get_property(root, self.prefix + "asset_name") or host.node_name(root)
        return Subject(
            name=str(name),
            asset_type=host.get_property(root, self.prefix + "asset_type"),
            task=host.get_property(root, self.prefix + "task"),
            root=root,
        )
