"""Mesh geometry checks. Each one points at the exact faces, edges or vertices,
so Select goes into Edit Mode with just those selected."""

# mathutils only exists inside Blender, so outside Blender this file is skipped
# quietly before numpy (which ships with Blender) is needed.
import mathutils
import numpy

from publish_validator import WARNING, Check, Component


class GeometryCheck(Check):
    abstract = True
    category = "Geometry"
    hosts = ["blender"]
    tasks = ["model"]

    def meshes(self, ctx):
        # Shared by every geometry check in a run.
        return ctx.cached("meshes", lambda: ctx.host.meshes(ctx.root))


class Ngons(GeometryCheck):
    """Faces should have 3 or 4 corners.

    Faces with more corners (ngons) subdivide and deform unpredictably, and other
    packages triangulate them differently. Split them into quads or triangles.
    """

    def validate(self, ctx):
        for obj in self.meshes(ctx):
            sizes = read(obj.data.polygons, "loop_total", int)
            faces = numpy.flatnonzero(sizes > 4)
            if len(faces):
                yield self.issue(
                    f"{obj.name} has {len(faces)} ngons", Component(obj, "face", faces.tolist())
                )


class ZeroAreaFaces(GeometryCheck):
    """Faces must have some area.

    Faces squashed flat to nothing (all corners on a line or a point) shade badly
    and break UVs and baking. Merge or delete them, e.g. Mesh > Clean Up >
    Degenerate Dissolve.
    """

    settings = {"min_area": 0.0000001}

    def validate(self, ctx):
        for obj in self.meshes(ctx):
            areas = read(obj.data.polygons, "area", float)
            faces = numpy.flatnonzero(areas < self.settings["min_area"])
            if len(faces):
                yield self.issue(
                    f"{obj.name} has {len(faces)} faces with no area",
                    Component(obj, "face", faces.tolist()),
                )


class LaminaFaces(GeometryCheck):
    """Two faces mustn't share exactly the same corners.

    Lamina faces sit on top of each other, so the surface flickers when rendered
    and shading breaks. Delete one of each pair.
    """

    def validate(self, ctx):
        for obj in self.meshes(ctx):
            seen = {}
            faces = []
            for face in obj.data.polygons:
                corners = tuple(sorted(face.vertices))
                if corners in seen:
                    faces += [seen[corners], face.index]
                else:
                    seen[corners] = face.index
            if faces:
                yield self.issue(
                    f"{obj.name} has {len(faces) // 2} pairs of lamina faces",
                    Component(obj, "face", sorted(set(faces))),
                )


class DoubleVerts(GeometryCheck):
    """Vertices shouldn't sit on top of each other.

    Overlapping vertices leave hidden seams that split shading and UVs. Merge them
    with Mesh > Merge > By Distance.
    """

    settings = {"distance": 0.0001}

    def validate(self, ctx):
        for obj in self.meshes(ctx):
            vertices = obj.data.vertices
            tree = mathutils.kdtree.KDTree(len(vertices))
            for vertex in vertices:
                tree.insert(vertex.co, vertex.index)
            tree.balance()
            doubles = set()
            for vertex in vertices:
                for _, index, _ in tree.find_range(vertex.co, self.settings["distance"]):
                    if index != vertex.index:
                        doubles.add(index)
            if doubles:
                yield self.issue(
                    f"{obj.name} has {len(doubles)} overlapping vertices",
                    Component(obj, "vertex", sorted(doubles)),
                )


class NonManifold(GeometryCheck):
    """An edge mustn't be shared by more than two faces.

    Edges where three or more faces meet can't be smoothed, subdivided or
    simulated properly. Separate or rebuild the faces around them.
    """

    def validate(self, ctx):
        for obj in self.meshes(ctx):
            edges = numpy.flatnonzero(faces_per_edge(obj.data) > 2)
            if len(edges):
                yield self.issue(
                    f"{obj.name} has {len(edges)} non-manifold edges",
                    Component(obj, "edge", edges.tolist()),
                )


class MeshHoles(GeometryCheck):
    """Meshes should be closed, with no holes or open borders.

    An open border is an edge with a face on one side only. Holes show up as gaps
    in renders and break simulation and 3D printing. Fill them (Face > Fill) or,
    if the mesh is meant to be open, like a leaf card, ignore this warning.
    """

    severity = WARNING

    def validate(self, ctx):
        for obj in self.meshes(ctx):
            edges = numpy.flatnonzero(faces_per_edge(obj.data) == 1)
            if len(edges):
                yield self.issue(
                    f"{obj.name} has {len(edges)} open border edges",
                    Component(obj, "edge", edges.tolist()),
                )


class UnappliedModifiers(GeometryCheck):
    """Meshes shouldn't have unapplied modifiers (subdivision is allowed).

    Other packages don't understand Blender modifiers. Apply them, or ask a lead
    to allow that modifier type in the studio config.
    """

    severity = WARNING
    settings = {"allowed": ["SUBSURF"]}

    def validate(self, ctx):
        for obj in ctx.host.meshes(ctx.root):
            modifiers = [m.name for m in obj.modifiers if m.type not in self.settings["allowed"]]
            if modifiers:
                yield self.issue(f"{obj.name} has modifiers: {', '.join(modifiers)}", obj)


def read(collection, attribute, kind):
    """Read one attribute of every item in a mesh collection into a numpy array."""
    values = numpy.empty(len(collection), dtype=kind)
    collection.foreach_get(attribute, values)
    return values


def faces_per_edge(mesh):
    """How many faces use each edge."""
    edge_of_each_corner = read(mesh.loops, "edge_index", int)
    return numpy.bincount(edge_of_each_corner, minlength=len(mesh.edges))
