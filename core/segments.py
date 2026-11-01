# SPDX-License-Identifier: GPL-3.0-or-later
"""Conversion of bendy bones (B-Bones) into chains of regular bones.

Fase 1 of the plan. Every bone with ``bbone_segments > 1`` is replaced by
``bbone_segments`` plain bones placed on the rest bbone curve:

- the segment data is collected first, in object mode, by the pure function
  :func:`collect_segment_specs` (no data is modified, no mode is changed);
- :func:`convert_bbones_to_segments` then writes everything in one single
  OBJECT -> EDIT -> OBJECT transition, never one ``mode_set`` per bone.

Space contract (verified by ``tests/run.py::fase1_spazio_bbone``):
``PoseBone.bbone_segment_matrix(index, rest=True)`` is expressed in the bone
local space, so the armature space matrix of a segment is
``bone.matrix_local @ pose_bone.bbone_segment_matrix(index, rest=True)``.
The head of the segment is that matrix translation; the segment roll is fixed
with ``EditBone.align_roll`` on the matrix Z axis, so the Z axis of the new
bone matches the Z axis of the bbone segment.
"""

import bpy


def segment_bone_name(bone_name, index):
    """Return the deterministic name of segment ``index`` of ``bone_name``.

    Two-digit index (``BendyA.000_seg_07``) so names sort and stay stable
    across sessions; a segment never collides with an original bone name.
    """
    index = int(index)
    if index < 0:
        raise ValueError("segment index must be >= 0 (got {0})".format(index))
    return "{0}_seg_{1:02d}".format(bone_name, index)


def is_convertible_bone(bone):
    """True when ``bone`` is a bendy bone with more than one segment."""
    return int(getattr(bone, "bbone_segments", 1)) > 1


def _segment_matrices(bone, pose_bone, count):
    """Armature-space matrices of the ``count`` rest segments of ``bone``."""
    return [
        bone.matrix_local @ pose_bone.bbone_segment_matrix(index, rest=True)
        for index in range(count)
    ]


def collect_segment_specs(arm_obj, bone_names=None):
    """Collect, in object mode, the bones that will replace the bbone chains.

    Pure: it reads the armature and returns plain data, it never changes the
    object mode nor the armature. Each spec is a dict with:

    - ``name``: segment bone name (see :func:`segment_bone_name`);
    - ``source``: original bendy bone name;
    - ``index``: segment index inside the source bone;
    - ``head``/``tail``: armature-space endpoints (Vector);
    - ``roll_axis``: normalized armature-space Z axis of the segment;
    - ``parent``: name of the parent bone (``None`` for a root);
    - ``use_connect``: ``False`` for every segment, they only share the head.

    ``bone_names`` restricts the conversion to the given bones; unknown names
    raise ``ValueError``, names that are not bendy bones are skipped.
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

    last_segment_of = {
        src: segment_bone_name(src, int(bones[src].bbone_segments) - 1) for src in sources
    }

    specs = []
    for source in sources:
        bone = bones[source]
        pose_bone = arm_obj.pose.bones[source]
        count = int(bone.bbone_segments)
        matrices = _segment_matrices(bone, pose_bone, count)
        heads = [matrix.to_translation().copy() for matrix in matrices]
        seg_len = bone.length / float(count)
        for index, matrix in enumerate(matrices):
            roll_axis = matrix.col[2].to_3d()
            if roll_axis.length <= 1e-9:
                raise ValueError(
                    "bone '{0}' segment {1}: degenerate Z axis (bbone scale is zero)".format(source, index)
                )
            tangent = matrix.col[1].to_3d()
            if tangent.length <= 1e-9:
                raise ValueError(
                    "bone '{0}' segment {1}: degenerate Y axis (bbone scale is zero)".format(source, index)
                )
            head = heads[index]
            tail = head + tangent.normalized() * seg_len
            if index == 0:
                if bone.parent is None:
                    parent = None
                elif bone.parent.name in last_segment_of:
                    parent = last_segment_of[bone.parent.name]
                else:
                    parent = bone.parent.name
            else:
                parent = segment_bone_name(source, index - 1)
            specs.append(
                {
                    "name": segment_bone_name(source, index),
                    "source": source,
                    "index": index,
                    "head": head,
                    "tail": tail,
                    "roll_axis": roll_axis.normalized(),
                    "parent": parent,
                    "use_connect": False,
                }
            )
    return specs


def convert_bbones_to_segments(arm_obj, bone_names=None):
    """Replace every bendy bone of ``arm_obj`` with a chain of plain bones.

    One single OBJECT -> EDIT -> OBJECT transition for the whole conversion.
    Returns a report dict:

    - ``converted``: source bone names (their ``use_deform`` is now ``False``);
    - ``segments``: ``{source: [segment names, in order]}``;
    - ``created``: every created segment bone name;
    - ``reparented_children``: ``{child_name: last segment name}`` for the
      non-converted children moved under the last segment of their source;
    - ``mode_changes``: number of ``mode_set`` calls performed (0, 1 or 2).

    Bones that are not bendy (``bbone_segments <= 1``) are left untouched.
    """
    specs = collect_segment_specs(arm_obj, bone_names)
    report = {
        "armature": arm_obj.name,
        "converted": [],
        "segments": {},
        "created": [],
        "reparented_children": {},
        "mode_changes": 0,
    }
    for spec in specs:
        if spec["source"] not in report["segments"]:
            report["segments"][spec["source"]] = []
            report["converted"].append(spec["source"])
        report["segments"][spec["source"]].append(spec["name"])
        report["created"].append(spec["name"])
    if not specs:
        return report

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    entered_edit = False
    if arm_obj.mode != "EDIT":
        view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        entered_edit = True
        report["mode_changes"] = 1

    try:
        edit_bones = arm_obj.data.edit_bones
        for name in report["created"]:
            if name in edit_bones:
                raise ValueError("segment bone '{0}' already exists".format(name))
        for spec in specs:
            parent_name = spec["parent"]
            if parent_name is not None and parent_name not in edit_bones:
                raise ValueError(
                    "segment '{0}': parent '{1}' not found".format(spec["name"], parent_name)
                )
            segment = edit_bones.new(spec["name"])
            segment.head = spec["head"]
            segment.tail = spec["tail"]
            segment.align_roll(spec["roll_axis"])
            if parent_name is not None:
                segment.parent = edit_bones[parent_name]
            segment.use_connect = spec["use_connect"]
            segment.use_deform = True
            segment.inherit_scale = "NONE"
        for source in report["converted"]:
            edit_bones[source].use_deform = False
        last_segment_of = {
            source: report["segments"][source][-1] for source in report["converted"]
        }
        for source, last_segment in last_segment_of.items():
            for edit_bone in edit_bones:
                if edit_bone.parent is None or edit_bone.parent.name != source:
                    continue
                if edit_bone.name in report["converted"] or edit_bone.name in report["created"]:
                    continue
                edit_bone.use_connect = False
                edit_bone.parent = edit_bones[last_segment]
                report["reparented_children"][edit_bone.name] = last_segment
    finally:
        if entered_edit:
            bpy.ops.object.mode_set(mode="OBJECT")
            report["mode_changes"] += 1
            if previous_active is not None and previous_active != arm_obj:
                view_layer.objects.active = previous_active

    return report


def _converted_sources(arm_obj, bone_names=None):
    """Bendy bones of ``arm_obj`` that still own a segment 0, i.e. converted."""
    bones = arm_obj.data.bones
    if bone_names is None:
        candidates = [bone.name for bone in bones if is_convertible_bone(bone)]
    else:
        candidates = []
        for name in bone_names:
            if name not in bones:
                raise ValueError("bone '{0}' not found in armature '{1}'".format(name, arm_obj.name))
            if is_convertible_bone(bones[name]):
                candidates.append(name)
    return [
        name for name in candidates if segment_bone_name(name, 0) in bones
    ]


def _action_fcurves(arm_obj):
    """Every F-Curve collection keyed on ``arm_obj``.

    Explicit fallback: legacy ``action.fcurves`` (Blender <= 4.3) versus the
    slot API of Blender 4.4+ (``action.layers[*].strips[*].channelbags``).
    """
    action = getattr(getattr(arm_obj, "animation_data", None), "action", None)
    if action is None:
        return []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return [legacy]
    collections = []
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channelbag in getattr(strip, "channelbags", ()):
                collections.append(channelbag.fcurves)
    return collections


def _remove_segment_keyframes(arm_obj, segment_names):
    """Delete the keyframes keyed on the given segment bones.

    Returns the number of F-Curves removed: a rig that was never baked has no
    animation data and simply reports zero.
    """
    prefixes = tuple('pose.bones["{0}"]'.format(name) for name in segment_names)
    removed = 0
    for fcurves in _action_fcurves(arm_obj):
        doomed = [fcurve for fcurve in fcurves if fcurve.data_path.startswith(prefixes)]
        for fcurve in doomed:
            fcurves.remove(fcurve)
            removed += 1
    return removed


def _remove_segment_constraints(arm_obj, segment_names):
    """Delete the follow constraints of the given segment bones.

    Returns the number of constraints removed. The constraint name is imported
    here because :mod:`core.bake` imports this module.
    """
    from .bake import CONSTRAINT_NAME

    removed = 0
    for name in segment_names:
        pose_bone = arm_obj.pose.bones.get(name)
        if pose_bone is None:
            continue
        constraint = pose_bone.constraints.get(CONSTRAINT_NAME)
        if constraint is None:
            continue
        pose_bone.constraints.remove(constraint)
        removed += 1
    return removed


def _revert_children(edit_bones, source, segments, sources):
    """Reparent the children of the last segment of ``source`` back to it.

    Segments of ``source`` are about to be deleted and are skipped; a
    ``<bone>_seg_00`` whose bone is not being reverted keeps its parent, it
    belongs to a chain that stays converted. Returns the moved child names.
    """
    last_bone = edit_bones.get(segments[-1])
    if last_bone is None:
        return []
    own = set(segments)
    moved = []
    for edit_bone in edit_bones:
        if edit_bone.parent is None or edit_bone.parent.name != last_bone.name:
            continue
        if edit_bone.name in own:
            continue
        if edit_bone.name.endswith("_seg_00") and edit_bone.name[: -len("_seg_00")] not in sources:
            continue
        edit_bone.use_connect = False
        edit_bone.parent = edit_bones[source]
        moved.append(edit_bone.name)
    return moved


def _merge_segment_weights(mesh_obj, source, segments):
    """Sum the weights of ``segments`` back onto the ``source`` group.

    The transfer clears the source group, so the total of every vertex is
    written on it (created when missing) and the segment groups are then
    deleted from the mesh. Returns the number of weighted vertices.
    """
    segment_indices = set()
    for name in segments:
        group = mesh_obj.vertex_groups.get(name)
        if group is not None:
            segment_indices.add(group.index)
    if not segment_indices:
        return 0
    totals = {}
    for vertex in mesh_obj.data.vertices:
        total = 0.0
        for element in vertex.groups:
            if element.group in segment_indices and element.weight > 0.0:
                total += float(element.weight)
        if total > 0.0:
            totals[vertex.index] = total
    indices = sorted(totals)
    if indices:
        target = mesh_obj.vertex_groups.get(source)
        if target is None:
            target = mesh_obj.vertex_groups.new(name=source)
        target.remove(indices)
        for vertex_index in indices:
            target.add([vertex_index], totals[vertex_index], "REPLACE")
    for name in segments:
        group = mesh_obj.vertex_groups.get(name)
        if group is not None:
            mesh_obj.vertex_groups.remove(group)
    return len(indices)


def revert_segments_to_bbones(arm_obj, bone_names=None):
    """Undo :func:`convert_bbones_to_segments` on the converted bendy bones.

    Every bendy bone that still owns a segment 0 (``<name>_seg_00``) gets the
    deformation back: the children of its last segment return under the source
    bone, ``use_deform`` is set to ``True`` again and all the ``*_seg_XX``
    bones are deleted in one single OBJECT -> EDIT -> OBJECT transition. The
    follow constraints and the keyframes of the segments are dropped first, so
    the rig never keeps animation on dead bones.

    For every rigged mesh (``find_rigged_meshes``, imported here to avoid a
    circular import) the weights of the segment groups are summed per vertex
    and written back on the source group, then the segment groups are removed
    from the mesh.

    ``bone_names`` restricts the revert to the given bones (unknown names raise
    ``ValueError``); a bendy bone that was never converted is skipped. Returns
    a report dict with ``armature``, ``reverted`` (source names) and
    ``removed_segments`` (deleted segment bone names).
    """
    sources = _converted_sources(arm_obj, bone_names)
    report = {"armature": arm_obj.name, "reverted": [], "removed_segments": []}
    if not sources:
        return report

    counts = {source: int(arm_obj.data.bones[source].bbone_segments) for source in sources}
    segments_of = {
        source: [segment_bone_name(source, index) for index in range(counts[source])]
        for source in sources
    }
    all_segments = [name for source in sources for name in segments_of[source]]

    _remove_segment_constraints(arm_obj, all_segments)
    _remove_segment_keyframes(arm_obj, all_segments)

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    entered_edit = False
    if arm_obj.mode != "EDIT":
        view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        entered_edit = True

    try:
        edit_bones = arm_obj.data.edit_bones
        sources_set = set(sources)
        for source in sources:
            segments = segments_of[source]
            _revert_children(edit_bones, source, segments, sources_set)
            source_bone = edit_bones.get(source)
            if source_bone is not None:
                source_bone.use_deform = True
            for name in segments:
                edit_bone = edit_bones.get(name)
                if edit_bone is None:
                    continue
                edit_bones.remove(edit_bone)
                report["removed_segments"].append(name)
            report["reverted"].append(source)
    finally:
        if entered_edit:
            bpy.ops.object.mode_set(mode="OBJECT")
            if previous_active is not None and previous_active != arm_obj:
                view_layer.objects.active = previous_active

    from .weights import find_rigged_meshes  # local: core.weights imports this module

    for mesh_obj in find_rigged_meshes(arm_obj):
        for source in sources:
            _merge_segment_weights(mesh_obj, source, segments_of[source])

    return report
