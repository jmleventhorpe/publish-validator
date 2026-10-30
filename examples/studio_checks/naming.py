"""Example studio check: works in every host because it only uses the generic Host API.

Point PUBLISH_VALIDATOR_PATH (or `check_paths` in a config file) at this folder
and it is picked up automatically.
"""

import re

from publish_validator import Check


class GeoNaming(Check):
    """Everything under the asset root must follow the studio naming convention.

    Names start with a capital letter and contain only letters and digits.
    Proxy geometry may end in "_px". Rename the listed nodes by hand.
    """

    id = "studio.geo_naming"  # explicit id: stays stable if the file or class is renamed
    category = "Naming"
    tasks = {"model"}

    class Settings:
        pattern = r"^[A-Z][A-Za-z0-9]*(_px)?$"
        ignore = ["geo", "proxy", "render", "simproxy"]

    def validate(self, ctx):
        pattern = re.compile(self.settings.pattern)
        for node in ctx.host.descendants(ctx.root):
            name = ctx.host.node_name(node)
            if name in self.settings.ignore:
                continue
            if not pattern.match(name):
                yield self.issue(f"'{name}' does not match {self.settings.pattern}", node)
