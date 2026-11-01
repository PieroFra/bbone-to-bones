# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake of the segment bone animation of the converted chains.

Fase 3 of the plan. Once :func:`core.segments.convert_bbones_to_segments` and
:func:`core.weights.transfer_bbone_weights` have replaced the bbones with plain
bones, the segments have no animation of their own: they only follow the
original bbones when they are posed manually (Fase 2). This module makes the
animation part of the rig instead.

The bake is a two-step contract:

1. every segment gets a ``COPY_TRANSFORMS`` constraint named
   :data:`CONSTRAINT_NAME` on its source bbone, with ``use_bbone_shape`` and
   ``head_tail = index / count`` so the constraint samples the bbone segment
   the plain bone replaces;
2. ``bpy.ops.nla.bake`` (visual keying, selected segments only) turns those
   constrained transforms into keyframes and clears the constraints.

A constraint only carries location/rotation/scale, not the shear implied by a
non-uniform rest scale (Chain C), so the baked curves are then overwritten with
the exact matrices of :func:`core.weights.pose_segments_from_bbones`, keyed on
every sampled frame. The result matches the posed bbones within
``core.POSE_MATCH_MAX_ERROR`` without calling the posing helper at playback.

Selection is the only version-sensitive bit: Blender 4.2 exposes
``PoseBone.select``, newer builds move the flag on the bone, hence
:func:`_set_pose_bone_selected` always checks both with ``hasattr``.
"""

import bpy

from .segments import is_convertible_bone, segment_bone_name
from .weights import pose_segments_from_bbones

# Name of the temporary follow constraint created and cleared by the bake.
CONSTRAINT_NAME = "BTOB_FollowBBone"


def _set_pose_bone_selected(pose_bone, selected):
    """Select or deselect ``pose_bone`` with an explicit 4.2 / 5.x fallback.

    Blender 4.2 stores the pose selection on ``PoseBone.select``; Blender 5.x
    moves it to ``Bone.select``. Both are set when they exist, never by version
    check.
    """
    if hasattr(pose_bone, "select"):
        pose_bone.select = bool(selected)
    if hasattr(pose_bone.bone, "select"):
        pose_bone.bone.select = bool(selected)


def _source_names(arm_obj, bone_names=None):
    """Return the convertible source bones, in armature order.

    ``bone_names`` restricts the work to the given bones; unknown names raise
    ``ValueError`` and names that are not bendy bones are skipped.
    """
    bones = arm_obj.data.bones
    if bone_names is None:
        return [bone.name for bone in bones if is_convertible_bone(bone)]
    sources = []
    for name in bone_names:
        if name not in bones:
            raise ValueError(
                "bone '{0}' not found in armature '{1}'".format(name, arm_obj.name)
            )
        if is_convertible_bone(bones[name]):
            sources.append(name)
    return sources


def _segment_specs(arm_obj, bone_names=None):
    """Yield ``(source, index, count, segment_name)`` for every segment bone."""
    bones = arm_obj.data.bones
    for source in _source_names(arm_obj, bone_names):
        count = int(bones[source].bbone_segments)
        for index in range(count):
            yield source, index, count, segment_bone_name(source, index)


def select_only_segment_bones(arm_obj, bone_names=None):
    """Deselect every pose bone, then select only the converted segments.

    Returns the list of selected segment names, in chain order. Segments that
    do not exist yet (armature not converted) are simply skipped.
    """
    for pose_bone in arm_obj.pose.bones:
        _set_pose_bone_selected(pose_bone, False)
    selected = []
    for _source, _index, _count, name in _segment_specs(arm_obj, bone_names):
        pose_bone = arm_obj.pose.bones.get(name)
        if pose_bone is None:
            continue
        _set_pose_bone_selected(pose_bone, True)
        selected.append(name)
    return selected


def add_bbone_follow_constraints(arm_obj, bone_names=None):
    """Constrain every segment bone on the bbone segment it replaces.

    The constraint is created once (or reused when one named
    :data:`CONSTRAINT_NAME` already exists) and is always refreshed with
    ``target = arm_obj``, ``subtarget = source``, ``use_bbone_shape = True`` and
    ``head_tail = index / count``. Returns a report dict with ``armature``,
    ``constrained`` (segment names carrying the constraint) and ``missing``
    (segments that do not exist).
    """
    report = {"armature": arm_obj.name, "constrained": [], "missing": []}
    for source, index, count, name in _segment_specs(arm_obj, bone_names):
        pose_bone = arm_obj.pose.bones.get(name)
        if pose_bone is None:
            report["missing"].append(name)
            continue
        constraint = pose_bone.constraints.get(CONSTRAINT_NAME)
        if constraint is not None and constraint.type != "COPY_TRANSFORMS":
            pose_bone.constraints.remove(constraint)
            constraint = None
        if constraint is None:
            constraint = pose_bone.constraints.new("COPY_TRANSFORMS")
            constraint.name = CONSTRAINT_NAME
        constraint.target = arm_obj
        constraint.subtarget = source
        constraint.use_bbone_shape = True
        constraint.head_tail = float(index) / float(count)
        report["constrained"].append(name)
    return report


def remove_bbone_follow_constraints(arm_obj, bone_names=None):
    """Remove the follow constraints from the segment bones.

    Returns the number of constraints removed. Segments that do not exist or
    carry no constraint named :data:`CONSTRAINT_NAME` are skipped.
    """
    removed = 0
    for _source, _index, _count, name in _segment_specs(arm_obj, bone_names):
        pose_bone = arm_obj.pose.bones.get(name)
        if pose_bone is None:
            continue
        constraint = pose_bone.constraints.get(CONSTRAINT_NAME)
        if constraint is None:
            continue
        pose_bone.constraints.remove(constraint)
        removed += 1
    return removed


def _keyframe_pose_bone(pose_bone, frame):
    """Insert the exact location/rotation/scale keys of ``pose_bone`` at ``frame``.

    The rotation channel follows ``rotation_mode``: quaternions when the bone
    uses ``QUATERNION``, Euler angles otherwise, so the keyed value is the one
    the rig actually evaluates.
    """
    pose_bone.keyframe_insert("location", frame=frame)
    if pose_bone.rotation_mode == "QUATERNION":
        pose_bone.keyframe_insert("rotation_quaternion", frame=frame)
    else:
        pose_bone.keyframe_insert("rotation_euler", frame=frame)
    pose_bone.keyframe_insert("scale", frame=frame)


def bake_segments_animation(
    arm_obj,
    frame_start=None,
    frame_end=None,
    step=1,
    bone_names=None,
    remove_constraints=True,
):
    """Bake the bbone motion of the segments into plain keyframes.

    ``frame_start`` / ``frame_end`` default to the scene range. The armature is
    switched to POSE mode with only the segment bones selected, the follow
    constraints of :func:`add_bbone_follow_constraints` are baked with visual
    keying into the current action, and the constraints are cleared by the
    bake. With ``remove_constraints`` the exact matrices of
    :func:`core.weights.pose_segments_from_bbones` are then keyed on every
    sampled frame, which also compensates the non-uniform rest scale of the
    bendy bones.

    The previous mode, the active object and the current frame are restored
    before returning. The report dict carries ``armature``, ``frame_start``,
    ``frame_end``, ``step``, ``baked`` (keyed segment names) and
    ``constraints_removed``.
    """
    scene = bpy.context.scene
    start = int(scene.frame_start if frame_start is None else frame_start)
    end = int(scene.frame_end if frame_end is None else frame_end)
    step = int(step)
    if step <= 0:
        raise ValueError("step must be >= 1 (got {0})".format(step))
    if end < start:
        raise ValueError(
            "frame_end {0} is before frame_start {1}".format(end, start)
        )

    previous_frame = scene.frame_current
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_mode = arm_obj.mode

    add_bbone_follow_constraints(arm_obj, bone_names=bone_names)
    view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    selected = []
    constraints_removed = 0
    entered_pose = False
    try:
        if arm_obj.mode != "POSE":
            bpy.ops.object.mode_set(mode="POSE")
            entered_pose = True
        selected = select_only_segment_bones(arm_obj, bone_names=bone_names)
        bpy.ops.nla.bake(
            frame_start=start,
            frame_end=end,
            step=step,
            only_selected=True,
            visual_keying=True,
            clear_constraints=bool(remove_constraints),
            use_current_action=True,
            bake_types={"POSE"},
        )
        if remove_constraints:
            constraints_removed = remove_bbone_follow_constraints(
                arm_obj, bone_names=bone_names
            )
            for frame in range(start, end + 1, step):
                scene.frame_set(frame)
                pose_segments_from_bbones(arm_obj, bone_names=bone_names)
                for name in selected:
                    pose_bone = arm_obj.pose.bones.get(name)
                    if pose_bone is not None:
                        _keyframe_pose_bone(pose_bone, frame)
    finally:
        if entered_pose:
            bpy.ops.object.mode_set(mode=previous_mode)
        if previous_active is not None and previous_active != arm_obj:
            view_layer.objects.active = previous_active
        scene.frame_set(previous_frame)

    return {
        "armature": arm_obj.name,
        "frame_start": start,
        "frame_end": end,
        "step": step,
        "baked": list(selected),
        "constraints_removed": constraints_removed,
    }
