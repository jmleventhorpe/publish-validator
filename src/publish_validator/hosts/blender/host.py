"""Blender host. Nodes are bpy Objects and Collections.

An asset root is either an Empty with the asset parented under it, or a
Collection holding the asset, marked with custom properties (see
PropertyResolver). Selecting any object inside the asset finds its root.
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
            node = target.node if isinstance(target, Component) else target
            # Selecting a collection selects the objects in it.
            found = node.all_objects if isinstance(node, bpy.types.Collection) else [node]
            for obj in found:
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
        """An object's parent object, or else the collection it's in; a collection's
        parent collection. None at the top of the scene."""
        if isinstance(node, bpy.types.Collection):
            return next((c for c in scene_collections() if node in c.children.values()), None)
        if node.parent is not None:
            return node.parent
        return next((c for c in node.users_collection if c in scene_collections()), None)

    def children(self, node):
        """An object's children; a collection's child collections and top-level objects."""
        if isinstance(node, bpy.types.Collection):
            inside = set(node.all_objects)
            top = [obj for obj in node.objects if obj.parent not in inside]
            return [*node.children, *top]
        return list(node.children)

    def descendants(self, node):
        """Every object below a node; for a collection, every object in it."""
        if isinstance(node, bpy.types.Collection):
            return list(node.all_objects)
        return list(node.children_recursive)

    def get_property(self, node, key, default=None):
        return node.get(key, default)

    def find_by_property(self, key):
        nodes = [*bpy.context.scene.objects, *scene_collections()]
        return [node for node in nodes if key in node]

    def node_name(self, node):
        if isinstance(node, Component):
            node = node.node
        return node.name

    # Helpers for Blender checks.

    def objects(self, root):
        """The root, if it's an object, and every object below it."""
        own = [] if isinstance(root, bpy.types.Collection) else [root]
        return [*own, *self.descendants(root)]

    def meshes(self, root):
        """The root and everything below it that is a mesh."""
        return [obj for obj in self.objects(root) if obj.type == "MESH"]

    def fingerprint(self, root):
        """A cheap summary of the asset, to tell whether it changed since validating.

        Covers object names, types, parents, transforms, modifiers and mesh vertex
        positions. Selection is left out, so selecting things never changes it.
        """
        parts = []
        for obj in self.objects(root):
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


def scene_collections():
    """Every collection in the current scene (not the scene's own top collection)."""
    return bpy.context.scene.collection.children_recursive


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
