"""Blender host. Nodes are bpy Objects.

An asset root is usually an Empty with the asset parented under it, marked with
custom properties (see PropertyResolver).
"""

import bmesh
import bpy
import numpy
from mathutils import Matrix

from ...core.host import Host
from ...core.results import Component

SELECT_MODES = {"vertex": "VERT", "edge": "EDGE", "face": "FACE"}


class BlenderHost(Host):
    name = "blender"

    def selection(self):
        return [obj for obj in bpy.context.view_layer.objects if obj.select_get()]

    def select(self, targets):
        components = [t for t in targets if isinstance(t, Component)]
        objects = []
        for target in targets:
            obj = target.node if isinstance(target, Component) else target
            if isinstance(obj, bpy.types.Object) and obj not in objects:
                objects.append(obj)

        if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode="OBJECT")

        view_layer = bpy.context.view_layer
        for obj in view_layer.objects:
            obj.select_set(False)
        for obj in objects:
            if obj.name in view_layer.objects:  # hidden from this view layer otherwise
                obj.select_set(True)
        if objects:
            view_layer.objects.active = objects[0]

        if components:
            select_components(components)

    def find(self, name):
        return bpy.context.scene.objects.get(name)

    def parent(self, node):
        return node.parent

    def children(self, node):
        return list(node.children)

    def descendants(self, node):
        return list(node.children_recursive)

    def get_property(self, node, key, default=None):
        return node.get(key, default)

    def find_by_property(self, key):
        return [obj for obj in bpy.context.scene.objects if key in obj]

    def node_name(self, node):
        if isinstance(node, Component):
            node = node.node
        return node.name

    # Helpers for Blender checks.

    def meshes(self, root):
        """The root and everything below it that is a mesh."""
        return [obj for obj in [root, *root.children_recursive] if obj.type == "MESH"]

    def fingerprint(self, root):
        """A cheap summary of the asset, to tell whether it changed since validating.

        Covers object names, types, parents, transforms, modifiers and mesh vertex
        positions. Selection is left out, so selecting things never changes it.
        """
        parts = []
        for obj in [root, *root.children_recursive]:
            parent = obj.parent.name if obj.parent else ""
            matrix = tuple(round(value, 5) for row in obj.matrix_world for value in row)
            modifiers = tuple((m.type, m.show_viewport) for m in getattr(obj, "modifiers", ()))
            geometry = ()
            if obj.type == "MESH":
                mesh = obj.data
                coords = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
                mesh.vertices.foreach_get("co", coords)
                geometry = (len(mesh.vertices), len(mesh.polygons), round(float(coords.sum()), 4))
            parts.append((obj.name, obj.type, parent, matrix, modifiers, geometry))
        return hash(tuple(parts))

    def apply_scale(self, objects):
        """Bake the scale into the mesh, like Object > Apply > Scale.

        Uses no operators, so it also works when Blender runs without a UI.
        """
        for obj in objects:
            if obj.type != "MESH":
                continue
            if obj.data.users > 1:
                obj.data = obj.data.copy()  # don't change other objects sharing this mesh
            scale = Matrix.Diagonal((*obj.scale, 1))
            obj.data.transform(scale)
            obj.scale = (1, 1, 1)
            # Keep children where they are, without changing their own transforms.
            for child in obj.children:
                child.matrix_parent_inverse = scale @ child.matrix_parent_inverse
        bpy.context.view_layer.update()


def select_components(components):
    """Go into Edit Mode with exactly these vertices/edges/faces selected."""
    meshes = []
    for component in components:
        if component.node.type == "MESH" and component.node not in meshes:
            meshes.append(component.node)
    if not meshes:
        return

    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.mode_set(mode="EDIT")
    modes = {SELECT_MODES[component.kind] for component in components}

    for obj in meshes:
        mesh = bmesh.from_edit_mesh(obj.data)
        mesh.select_mode = modes
        elements = {"vertex": mesh.verts, "edge": mesh.edges, "face": mesh.faces}
        for sequence in elements.values():
            sequence.ensure_lookup_table()
            for element in sequence:
                element.select = False

        for component in components:
            if component.node != obj:
                continue
            sequence = elements[component.kind]
            for index in component.indices:
                if index < len(sequence):
                    sequence[index].select_set(True)

        mesh.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)

    bpy.context.tool_settings.mesh_select_mode = ["VERT" in modes, "EDGE" in modes, "FACE" in modes]
