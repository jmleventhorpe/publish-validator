import re

from publish_validator import Check


class NamingConvention(Check):
    """Objects must follow the naming convention.

    Geometry and groups: seat, L_frontLeg, legs (side prefix optional).
    Proxy geometry, under the proxy group: seat_proxy.
    Use letters and digits only: no spaces, dots or dashes, and no Blender
    ".001" endings (number with leg001 instead). These names survive the
    export to USD unchanged.
    """

    category = "Naming"
    hosts = ["blender"]
    tasks = ["model"]
    settings = {
        "geo_suffix": "",  # empty: render geometry has no suffix
        "proxy_suffix": "proxy",
        "group_suffix": "",  # empty: groups have no suffix
        "sides": ["L", "R", "C"],
        "group_names": ["geo", "render", "proxy", "simproxy", "utils", "temp"],
    }

    def validate(self, ctx):
        sides = "|".join(re.escape(side) for side in self.settings["sides"])
        word = "[a-z][a-zA-Z0-9]*"
        proxy_ending = "_" + self.settings["proxy_suffix"]

        for obj in ctx.host.descendants(ctx.root):
            name = obj.name
            if obj.type == "EMPTY":
                if name in self.settings["group_names"]:
                    continue
                suffix = self.settings["group_suffix"]
            elif obj.type == "MESH":
                in_proxy = any(parent.name == "proxy" for parent in parents(obj))
                if not in_proxy and name.endswith(proxy_ending):
                    yield self.issue(f"{name} is named as a proxy but isn't under 'proxy'", obj)
                    continue
                suffix = self.settings["proxy_suffix" if in_proxy else "geo_suffix"]
            else:
                continue  # other object types are Allowed Object Types' business

            ending = f"_{re.escape(suffix)}" if suffix else ""
            if re.match(rf"^(?:(?:{sides})_)?{word}(?:_{word})*{ending}$", name):
                continue
            if re.search(r"\.\d+$", name):
                reason = "has Blender's automatic number ending"
            elif suffix and not name.endswith("_" + suffix):
                reason = f"should end in _{suffix}"
            else:
                reason = "should use letters and digits, starting lower case, e.g. frontLeg"
            yield self.issue(f"{name} {reason}", obj)


class MeshDataNames(Check):
    """Each mesh's data should be named the same as its object.

    Blender names them the same when you create a mesh, but they drift apart as
    objects are renamed or duplicated, which makes exports and linking harder to
    follow. Rename the mesh data in the Object Data properties to match.
    Meshes shared by several objects are skipped.
    """

    category = "Naming"
    hosts = ["blender"]
    tasks = ["model"]

    def validate(self, ctx):
        for obj in ctx.host.meshes(ctx.root):
            if obj.data.users == 1 and obj.data.name != obj.name:
                yield self.issue(f"{obj.name} uses mesh data called {obj.data.name}", obj)


def parents(obj):
    while obj.parent is not None:
        obj = obj.parent
        yield obj
