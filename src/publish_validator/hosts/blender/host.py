"""Blender host adapter.

Nodes are ``bpy.types.Object``. Asset roots are usually Empties with the asset
parented underneath, marked with custom properties (see ``PropertyResolver``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

import bmesh
import bpy
from mathutils import Matrix

from ...core.host import Host
from ...core.model import Component

_SELECT_MODES = {"vertex": "VERT", "edge": "EDGE", "face": "FACE"}


class BlenderHost(Host):
    name = "blender"

    # -- Host API -----------------------------------------------------------------

    def selection(self) -> list[bpy.types.Object]:
        view_layer = bpy.context.view_layer
        selected = [obj for obj in view_layer.objects if obj.select_get()]
        active = view_layer.objects.active
        if active in selected:  # active first, like artists expect
            selected.remove(active)
            selected.insert(0, active)
        return selected

    def select(self, targets: Iterable[Any]) -> None:
        targets = list(targets)
        components = [t for t in targets if isinstance(t, Component)]
        objects = [t.node if isinstance(t, Component) else t for t in targets]
        objects = [o for o in dict.fromkeys(objects) if isinstance(o, bpy.types.Object)]

        _ensure_object_mode()
        view_layer = bpy.context.view_layer
        for obj in view_layer.objects:
            obj.select_set(False)
        visible = [o for o in objects if o.name in view_layer.objects]
        for obj in visible:
            obj.select_set(True)
        if visible:
            view_layer.objects.active = visible[0]
        if components:
            _select_components(components)

    def find(self, name: str) -> bpy.types.Object | None:
        return bpy.data.objects.get(name)

    def parent(self, node: bpy.types.Object) -> bpy.types.Object | None:
        return node.parent

    def children(self, node: bpy.types.Object) -> list[bpy.types.Object]:
        return list(node.children)

    def descendants(self, node: bpy.types.Object) -> Iterator[bpy.types.Object]:
        return iter(node.children_recursive)

    def get_property(self, node: Any, key: str, default: Any = None) -> Any:
        getter = getattr(node, "get", None)
        return getter(key, default) if getter else default

    def find_by_property(self, key: str) -> list[bpy.types.Object]:
        return [obj for obj in bpy.context.scene.objects if key in obj]

    def node_name(self, node: Any) -> str:
        if isinstance(node, Component):
            node = node.node
        return getattr(node, "name", str(node))

    def watch_selection(self, callback: Callable[[], None]) -> Callable[[], None]:
        last: list[tuple[str, ...]] = [self._selection_key()]

        @bpy.app.handlers.persistent
        def handler(_scene, _depsgraph):
            key = self._selection_key()
            if key != last[0]:
                last[0] = key
                callback()

        bpy.app.handlers.depsgraph_update_post.append(handler)

        def unwatch() -> None:
            if handler in bpy.app.handlers.depsgraph_update_post:
                bpy.app.handlers.depsgraph_update_post.remove(handler)

        return unwatch

    # -- Blender helpers for checks -------------------------------------------------

    def meshes(self, root: bpy.types.Object) -> list[bpy.types.Object]:
        """Mesh objects at or below ``root``."""
        objects = [root, *root.children_recursive]
        return [obj for obj in objects if obj.type == "MESH"]

    def apply_scale(self, objects: Iterable[bpy.types.Object]) -> None:
        """Bake object scale into mesh data, like Object > Apply > Scale.

        Works without operators (so it is safe headless). Shared mesh data is
        made single-user first. Children keep their world transform and their
        own local values; the compensation goes into their parent-inverse matrix.
        """
        for obj in objects:
            if obj.type != "MESH":
                continue
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            scale = Matrix.Diagonal((*obj.scale, 1.0))
            obj.data.transform(scale)
            obj.scale = (1.0, 1.0, 1.0)
            for child in obj.children:
                child.matrix_parent_inverse = scale @ child.matrix_parent_inverse
        bpy.context.view_layer.update()

    # -- Internals ------------------------------------------------------------------

    def _selection_key(self) -> tuple[str, ...]:
        try:
            return tuple(obj.name for obj in self.selection())
        except (AttributeError, ReferenceError):
            return ()


def _ensure_object_mode() -> None:
    if bpy.context.mode != "OBJECT" and bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")


def _select_components(components: list[Component]) -> None:
    """Enter edit mode with exactly ``components`` selected. Best effort."""
    kinds = {c.kind for c in components}
    meshes = [c.node for c in components if getattr(c.node, "type", None) == "MESH"]
    if not meshes or not kinds <= set(_SELECT_MODES):
        return
    bpy.context.view_layer.objects.active = meshes[0]
    if not bpy.ops.object.mode_set.poll():
        return
    bpy.ops.object.mode_set(mode="EDIT")
    for obj in dict.fromkeys(meshes):
        bm = bmesh.from_edit_mesh(obj.data)
        for seq in (bm.verts, bm.edges, bm.faces):
            for element in seq:
                element.select = False
        bm.select_mode = {_SELECT_MODES[k] for k in kinds}
        tables = {"vertex": bm.verts, "edge": bm.edges, "face": bm.faces}
        for table in tables.values():
            table.ensure_lookup_table()
        for component in components:
            if component.node is not obj:
                continue
            table = tables[component.kind]
            for index in component.indices:
                if index < len(table):
                    table[index].select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
    bpy.context.tool_settings.mesh_select_mode = tuple(
        mode in {_SELECT_MODES[k] for k in kinds} for mode in ("VERT", "EDGE", "FACE")
    )
