# SPDX-License-Identifier: GPL-3.0-or-later
"""Revert chains of segment bones back to the original bendy bones.

The inverse of :mod:`core.segments` (Fase 1 revert): every bendy bone that
still owns a segment 0 (``<name>_seg_00``) gets the deformation back, its
segments are deleted and the skin weights of the segment groups are summed
back on the source group.
"""

import bpy

from .segments import is_convertible_bone, segment_bone_name


def _converted_sources(arm_obj, bone_names=None):
    """Bendy bones of ``arm_obj`` that still own a segment 0, i.e. converted."""
    bones = arm_obj.data.bones
    if bone_names is None:
        candidates = [bone.name for bone in bones if is_convertible_bone(bone, deform_only=False)]
    else:
        candidates = []
        for name in bone_names:
            if name not in bones:
                raise ValueError("bone '{0}' not found in armature '{1}'".format(name, arm_obj.name))
            if is_convertible_bone(bones[name], deform_only=False):
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
    if legacy is not None and len(legacy) > 0:
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
    """Reparent the children of ``source``'s segments back to it.

    Segments of ``source`` are about to be deleted and are skipped; a
    ``<bone>_seg_00`` whose bone is not being reverted keeps its parent, it
    belongs to a chain that stays converted. Returns the moved child names.
    """
    own = set(segments)
    moved = []
    for edit_bone in edit_bones:
        if edit_bone.parent is None or edit_bone.parent.name not in own:
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
    deformation back: the children of its segments return under the source
    bone, ``use_deform`` is restored from the segments (``True`` when any
    segment deformed) and all the ``*_seg_XX``
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

    had_deform = {
        s: any(bool(getattr(arm_obj.data.bones.get(seg), "use_deform", False)) for seg in segments_of[s])
        for s in sources
    }

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
                source_bone.use_deform = had_deform.get(source, True)
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
