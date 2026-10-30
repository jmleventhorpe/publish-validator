"""An example Blender-only check. It is in a folder called "blender", so it
only loads inside Blender."""

from publish_validator import WARNING, Check


class UnappliedModifiers(Check):
    """Meshes shouldn't have unapplied modifiers (subdivision is allowed).

    Other packages don't understand Blender modifiers. Apply them, or ask a lead
    to allow that modifier type in the studio config.
    """

    category = "Objects"
    hosts = ["blender"]
    tasks = ["model"]
    severity = WARNING
    settings = {"allowed": ["SUBSURF"]}

    def validate(self, ctx):
        for obj in ctx.host.meshes(ctx.root):
            modifiers = [m.name for m in obj.modifiers if m.type not in self.settings["allowed"]]
            if modifiers:
                yield self.issue(f"{obj.name} has modifiers: {', '.join(modifiers)}", obj)
