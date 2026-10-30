"""An example studio check. It only uses the generic host methods, so it works
in any application.

Point PUBLISH_VALIDATOR_PATH (or check_paths in a config file) at this folder
and it is picked up automatically.
"""

import re

from publish_validator import Check


class GeoNaming(Check):
    """Everything in the asset must follow the studio naming convention.

    Names start with a capital letter and contain only letters and digits.
    Proxy geometry may end in "_px". Rename the listed nodes by hand.
    """

    category = "Naming"
    tasks = ["model"]
    settings = {
        "pattern": r"^[A-Z][A-Za-z0-9]*(_px)?$",
        "ignore": ["geo", "proxy", "render", "simproxy"],
    }

    def validate(self, ctx):
        pattern = re.compile(self.settings["pattern"])
        for node in ctx.host.descendants(ctx.root):
            name = ctx.host.node_name(node)
            if name not in self.settings["ignore"] and not pattern.match(name):
                yield self.issue(f"'{name}' does not follow the naming convention", node)
