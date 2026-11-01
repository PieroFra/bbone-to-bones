# SPDX-License-Identifier: GPL-3.0-or-later
"""Transfer of the vertex weights of bendy bones onto the converted segments.

Fase 2 of the plan. Once :func:`core.segments.convert_bbones_to_segments` has
replaced every bbone with a chain of plain bones, the skin weights still sit on
the (now non-deforming) source bones. This module moves them onto the
``*_seg_XX`` bones that took over the deformation.

Space contract (verified on Blender 5.2 LTS, headless):

``PoseBone.bbone_segment_index(point)`` expects ``point`` in **armature
space**, expressed with the same units as ``Bone.head_local`` and
``Bone.tail_local``. Measured on the 8-segment fixture bone ``BendyB.000``:

- ``bbone_segment_index(bone.head_local)`` -> ``(0, 0.0)``;
- ``bbone_segment_index(bone.tail_local)`` -> ``(7, 1.0)``;
- ``bbone_segment_index((0, b.length, 0))`` (bone local space) -> ``(0, 0.0)``,
  i.e. bone-local coordinates are *not* what the function wants.

So the vertices are converted with
``arm_obj.matrix_world.inverted_safe() @ mesh_obj.matrix_world`` and never with
``bone.matrix_local.inverted()``. The weights are therefore transferred on the
rest mesh, against the rest bbone curve: do not pose the armature before
calling :func:`transfer_bbone_weights`.

Weights of vertex groups that are not deform bones (masks, cloth, pinning) are
read and left untouched: normalisation only ever scales the deform groups.
"""

import bpy
import numpy as np
from mathutils import Vector

from .segments import is_convertible_bone, segment_bone_name

# A deform total this close to 1.0 is considered already normalised.
NORMALIZE_EPSILON = 1e-6


def find_rigged_meshes(arm_obj, scene=None):
    """Return the mesh objects of ``scene`` deformed by ``arm_obj``.

    A mesh counts as rigged when it has an ``ARMATURE`` modifier pointing at
    ``arm_obj``, or when it is parented to it with ``parent_type == 'ARMATURE'``.
    The objects are returned as objects, never by mesh data name: the fixture
    pairs ``BodyHigh`` with the data block ``MeshHighData``, so assuming
    ``mesh_obj.name == mesh_obj.data.name`` would break here.
    """
    candidates = bpy.data.objects if scene is None else scene.objects
    meshes = []
    for obj in candidates:
        if obj.type != "MESH":
            continue
        if _is_rigged_to(obj, arm_obj):
            meshes.append(obj)
    return meshes


def _is_rigged_to(mesh_obj, arm_obj):
    """True when ``mesh_obj`` is deformed by ``arm_obj`` through a modifier or parenting."""
    for modifier in mesh_obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object == arm_obj:
            return True
    return mesh_obj.parent == arm_obj and mesh_obj.parent_type == "ARMATURE"


def vertex_coords_in_armature_space(mesh_obj, arm_obj, update_view_layer=True):
    """Return the rest vertex coordinates of ``mesh_obj`` in armature space.

    The bulk read is a single ``foreach_get`` on a preallocated numpy buffer;
    the whole mesh is then transformed by
    ``arm_obj.matrix_world.inverted_safe() @ mesh_obj.matrix_world``. The result
    is a list of ``Vector`` ready for ``PoseBone.bbone_segment_index``, which
    expects armature space (see the module docstring).
    """
    if update_view_layer:
        bpy.context.view_layer.update()
    mesh = mesh_obj.data
    count = len(mesh.vertices)
    if count == 0:
        return []
    coords = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    local = coords.reshape(count, 3)
    matrix = np.array([list(row) for row in arm_obj.matrix_world.inverted_safe() @ mesh_obj.matrix_world], dtype=np.float64)
    points = local @ matrix[:3, :3].T + matrix[:3, 3]
    return [Vector(point) for point in points]


def split_bbone_weight(weight, index, blend_next, segment_count):
    """Split ``weight`` between segment ``index`` and ``index + 1``.

    ``index`` and ``blend_next`` are the pair returned by
    ``PoseBone.bbone_segment_index`` for the vertex position. The current
    segment keeps ``weight * (1 - blend_next)``, the next one gets
    ``weight * blend_next``. On the last segment (``index + 1 >= segment_count``)
    or with ``blend_next == 0`` everything stays on ``index``.

    Returns ``{segment_index: weight}``, without zero entries.
    """
    index = int(index)
    count = int(segment_count)
    if count <= 0:
        raise ValueError("segment_count must be >= 1 (got {0})".format(count))
    if index < 0 or index >= count:
        raise ValueError("segment index {0} out of range 0..{1}".format(index, count - 1))
    blend = min(max(float(blend_next), 0.0), 1.0)
    if index + 1 < count and blend > 0.0:
        result = {index: weight * (1.0 - blend), index + 1: weight * blend}
    else:
        result = {index: weight}
    return {segment: value for segment, value in result.items() if value != 0.0}


def _is_deform_bone(bones, name):
    """True when ``name`` is a bone of the armature that deforms the mesh."""
    bone = bones.get(name)
    return bone is not None and bool(bone.use_deform)


def _bbone_source_kind(bones, name):
    """Classify a vertex group name: ``'source'``, ``'deform'`` or ``'other'``.

    A group is a bbone source when it names a bendy bone, or when its first
    segment bone (``<name>_seg_00``) exists, which is how an already converted
    source is recognised.
    """
    bone = bones.get(name)
    if bone is not None and is_convertible_bone(bone):
        return "source"
    if segment_bone_name(name, 0) in bones:
        return "source"
    if bone is not None and bone.use_deform:
        return "deform"
    return "other"


def _read_vertex_weights(mesh_obj, bones):
    """Read every weight of ``mesh_obj`` once, with the kind of each group.

    Returns ``(rows, kinds)``: ``rows[vertex_index]`` is a list of
    ``(group_name, kind, weight)`` and ``kinds`` maps every group name to its
    classification (computed once per group, not once per vertex).
    """
    names_by_index = {group.index: group.name for group in mesh_obj.vertex_groups}
    kinds = {}
    rows = []
    for vertex in mesh_obj.data.vertices:
        items = []
        for element in vertex.groups:
            name = names_by_index.get(element.group)
            if name is None:
                continue
            kind = kinds.get(name)
            if kind is None:
                kind = _bbone_source_kind(bones, name)
                kinds[name] = kind
            items.append((name, kind, float(element.weight)))
        rows.append(items)
    return rows, kinds


def _next_chain_segment_group(bones, source_name):
    """Return the first segment group of the bone chained to the tail of ``source_name``.

    The last joint of a bendy bone coincides with the first joint of the child
    bone connected to its tail, so a vertex blended past the last segment must
    land on ``<child>_seg_00``. Returns ``None`` when no such bone exists.
    """
    source = bones.get(source_name)
    if source is None:
        return None
    tail = source.tail_local
    for other in bones:
        if other.name == source_name:
            continue
        group_name = segment_bone_name(other.name, 0)
        if group_name not in bones:
            continue
        if (other.head_local - tail).length <= 1e-5:
            return group_name
    return None


def transfer_bbone_weights(arm_obj, mesh_objs=None, normalize_deform=True, remove_source_weights=True):
    """Move the bbone skin weights onto the converted segment bones.

    For every rigged mesh (``mesh_objs`` or :func:`find_rigged_meshes`) the
    existing weights are read in one pass. Every weight sitting on a bbone
    source is split with :func:`split_bbone_weight` on the segment bones and
    accumulated in memory as ``{segment_group_name: {vertex_index: weight}}``.
    Nothing is written until the end: each target group is rewritten in a
    single pass, and the source groups are cleared when
    ``remove_source_weights`` is true (their bones are ``use_deform == False``
    after the conversion).

    With ``normalize_deform`` the weights of the deform groups only are scaled
    so that they sum to ``1.0`` per vertex; groups that are not deform bones
    (masks, cloth, pinning) keep their weights untouched, and a total already
    at ``1.0`` within :data:`NORMALIZE_EPSILON` is preserved as is.

    Returns a report dict with ``armature``, ``meshes``, ``sources`` (bbone
    groups that were transferred), ``segments`` (groups written), ``vertices``
    (weighted vertices handled) and the two option flags.
    """
    bones = arm_obj.data.bones
    meshes = find_rigged_meshes(arm_obj) if mesh_objs is None else list(mesh_objs)
    report = {
        "armature": arm_obj.name,
        "meshes": [],
        "sources": [],
        "segments": [],
        "vertices": 0,
        "normalize_deform": bool(normalize_deform),
        "remove_source_weights": bool(remove_source_weights),
    }
    sources_seen = set()
    segments_seen = set()

    for mesh_obj in meshes:
        rows, kinds = _read_vertex_weights(mesh_obj, bones)
        coords = vertex_coords_in_armature_space(mesh_obj, arm_obj)
        targets = {}
        source_vertices = {}

        for vertex_index, items in enumerate(rows):
            new_weights = {}
            has_source = False
            for name, kind, weight in items:
                if kind != "source" or weight <= 0.0:
                    continue
                pose_bone = arm_obj.pose.bones.get(name)
                if pose_bone is None:
                    continue
                count = int(bones[name].bbone_segments)
                index, blend_next = pose_bone.bbone_segment_index(coords[vertex_index])
                blend = min(max(float(blend_next), 0.0), 1.0)
                next_group = None
                if index == count - 1 and blend > 0.0:
                    next_group = _next_chain_segment_group(bones, name)
                if next_group is not None:
                    pairs = {segment_bone_name(name, index): weight * (1.0 - blend), next_group: weight * blend}
                else:
                    pairs = {}
                    for segment, value in split_bbone_weight(weight, index, blend_next, count).items():
                        pairs[segment_bone_name(name, segment)] = value
                for group_name, value in pairs.items():
                    new_weights[group_name] = new_weights.get(group_name, 0.0) + value
                source_vertices.setdefault(name, []).append(vertex_index)
                sources_seen.add(name)
                has_source = True

            if not has_source:
                continue

            deform_total = sum(weight for _, kind, weight in items if kind == "deform")
            if normalize_deform:
                deform_total += sum(value for name, value in new_weights.items() if _is_deform_bone(bones, name))
                factor = 1.0
                if deform_total > 0.0 and abs(deform_total - 1.0) > NORMALIZE_EPSILON:
                    factor = 1.0 / deform_total
            else:
                factor = 1.0

            for name, value in new_weights.items():
                targets.setdefault(name, {})[vertex_index] = value * factor
                segments_seen.add(name)
            if normalize_deform and factor != 1.0:
                for name, kind, weight in items:
                    if kind == "deform":
                        targets.setdefault(name, {})[vertex_index] = weight * factor
            report["vertices"] += 1

        for group_name, values in targets.items():
            group = mesh_obj.vertex_groups.get(group_name)
            if group is None:
                group = mesh_obj.vertex_groups.new(name=group_name)
            indices = sorted(values)
            group.remove(indices)
            for vertex_index in indices:
                group.add([vertex_index], values[vertex_index], "REPLACE")

        if remove_source_weights:
            for group_name, indices in source_vertices.items():
                group = mesh_obj.vertex_groups.get(group_name)
                if group is not None and indices:
                    group.remove(sorted(indices))

        report["meshes"].append(mesh_obj.name)

    report["sources"] = sorted(sources_seen)
    report["segments"] = sorted(segments_seen)
    return report


def pose_segments_from_bbones(arm_obj, bone_names=None):
    """Pose the ``*_seg_XX`` bones on the current posed bbone curve.

    A bbone segment deforms its vertices by the LBS matrix
    ``posed_seg @ rest_seg.inverted()``, with
    ``posed_seg = pose_bone.matrix @ pose_bone.bbone_segment_matrix(index, rest=False)``
    and
    ``rest_seg = bone.matrix_local @ pose_bone.bbone_segment_matrix(index, rest=True)``.
    A plain segment deforms by ``segment.matrix @ segment.bone.matrix_local.inverted()``,
    so the two are identical only when ``segment.matrix`` is set to
    ``posed_seg @ rest_seg.inverted() @ segment.bone.matrix_local``. The trailing
    ``matrix_local`` factor matters: ``rest_seg`` is not the rigid chord frame of
    ``segment.bone`` as soon as the source bbone has a rest curve or a
    non-uniform rest scale. Assigning ``posed_seg`` alone leaves the mesh at rest
    (1.98 m of error on the fixture).

    The segments are set in chain order with a depsgraph update between them,
    because each segment is parented to the previous one. The armature stays in
    object mode. Returns a report dict with ``armature``, ``posed`` and
    ``missing`` (segment bones that do not exist yet, i.e. not converted).
    """
    bones = arm_obj.data.bones
    if bone_names is None:
        sources = [bone.name for bone in bones if is_convertible_bone(bone)]
    else:
        sources = []
        for name in bone_names:
            if name not in bones:
                raise ValueError("bone '{0}' not found in armature '{1}'".format(name, arm_obj.name))
            if is_convertible_bone(bones[name]):
                sources.append(name)

    report = {"armature": arm_obj.name, "posed": [], "missing": []}
    for source in sources:
        bone = bones[source]
        pose_bone = arm_obj.pose.bones[source]
        count = int(bone.bbone_segments)
        posed_mats = [
            pose_bone.matrix @ pose_bone.bbone_segment_matrix(index, rest=False)
            for index in range(count)
        ]
        rest_mats = [
            bone.matrix_local @ pose_bone.bbone_segment_matrix(index, rest=True)
            for index in range(count)
        ]
        for index in range(count):
            name = segment_bone_name(source, index)
            segment = arm_obj.pose.bones.get(name)
            if segment is None:
                report["missing"].append(name)
                continue
            segment.matrix = posed_mats[index] @ rest_mats[index].inverted() @ segment.bone.matrix_local
            bpy.context.view_layer.update()
            report["posed"].append(name)
    return report
