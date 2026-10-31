"""An example studio check. It is in a folder called "blender", so it only loads
inside Blender. Point PUBLISH_VALIDATOR_PATH (or check_paths in a config file) at
the folder above this one and it is picked up automatically.
"""

from publish_validator import WARNING, Check


class PolyBudget(Check):
    """Props should stay within the studio's face budget.

    Heavy props slow down every shot they appear in. Reduce the mesh, or ask a
    lead to raise the budget for this asset in the project config.
    """

    category = "Geometry"
    hosts = ["blender"]
    tasks = ["model"]
    asset_types = ["prop"]
    severity = WARNING
    settings = {"max_faces": 50000}

    def validate(self, ctx):
        faces = sum(len(obj.data.polygons) for obj in ctx.host.meshes(ctx.root))
        if faces > self.settings["max_faces"]:
            yield self.issue(
                f"{faces} faces, over the budget of {self.settings['max_faces']}", ctx.root
            )
