"""Example Blender-only check, written as a plain function.

It lives in a folder named "blender", so it is only loaded inside Blender.
"""

from publish_validator import Severity, check


@check(
    id="studio.unapplied_modifiers",
    category="Objects",
    hosts="blender",
    tasks="model",
    severity=Severity.WARNING,
    settings={"allowed": ["SUBSURF"]},
)
def unapplied_modifiers(ctx):
    """Meshes should not carry unapplied modifiers (subdivision is allowed).

    Downstream packages do not understand Blender modifiers. Apply them, or ask
    a lead to allow the modifier type in the studio config.
    """
    allowed = set(ctx.settings.allowed)
    for obj in ctx.host.meshes(ctx.root):
        extra = [m.name for m in obj.modifiers if m.type not in allowed]
        if extra:
            yield f"{obj.name} has modifiers: {', '.join(extra)}"
