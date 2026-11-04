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


def is_convertible_bone(bone, deform_only=True):
    """True when ``bone`` is a bendy bone with more than one segment."""
    if int(getattr(bone, "bbone_segments", 1)) <= 1:
        return False
    if deform_only and not bool(getattr(bone, "use_deform", True)):
        return False
    return True


def _segment_matrices(bone, pose_bone, count):
    """Armature-space matrices of the ``count`` rest segments of ``bone``."""
    return [
        bone.matrix_local @ pose_bone.bbone_segment_matrix(index, rest=True)
        for index in range(count)
    ]


def collect_segment_specs(arm_obj, bone_names=None, deform_only=True):
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
    ``deform_only`` skips bones whose ``use_deform`` is off.
    """
    bones = arm_obj.data.bones
    if bone_names is None:
        sources = [
            bone.name for bone in bones if is_convertible_bone(bone, deform_only=deform_only)
        ]
    else:
        sources = []
        for name in bone_names:
            if name not in bones:
                raise ValueError("bone '{0}' not found in armature '{1}'".format(name, arm_obj.name))
            if is_convertible_bone(bones[name], deform_only=deform_only):
                sources.append(name)

    if sources:
        # Freshly edited ``bbone_segments`` need a depsgraph update before
        # ``bbone_segment_matrix`` can be queried, otherwise Blender raises
        # "out of date B-Bone segment data".
        bpy.context.view_layer.update()

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


def _has_local_transform_constraint(arm_obj, bone_name):
    """True when ``bone_name`` inherits a transform in its own local space.

    Rigs such as GeorgeRIG (or the ones generated by A.C.T.D.) drive deforming
    children like ``DEF_Forearm.L`` with a ``COPY_TRANSFORMS`` constraint in
    ``LOCAL`` space towards a mechanism bone. Reparenting such a child to the
    last segment rotates the basis of its ``LOCAL`` space and the constraint
    applies the rotation twice, so the child must keep its parent.
    """
    types = ("COPY_TRANSFORMS", "COPY_ROTATION", "COPY_LOCATION", "COPY_SCALE", "CHILD_OF")
    spaces = ("LOCAL", "LOCAL_WITH_PARENT")
    pose_bone = arm_obj.pose.bones.get(bone_name)
    if pose_bone is None:
        return False
    for constraint in pose_bone.constraints:
        if getattr(constraint, "mute", False):
            continue
        if constraint.type not in types:
            continue
        if getattr(constraint, "owner_space", "") in spaces:
            return True
    return False


def convert_bbones_to_segments(arm_obj, bone_names=None, deform_only=True, reparent_children=True):
    """Replace every bendy bone of ``arm_obj`` with a chain of plain bones.

    One single OBJECT -> EDIT -> OBJECT transition for the whole conversion.
    Returns a report dict:

    - ``converted``: source bone names (their ``use_deform`` is now ``False``);
    - ``segments``: ``{source: [segment names, in order]}``;
    - ``created``: every created segment bone name;
    - ``reparented_children``: ``{child_name: first segment name}`` for the
      non-converted children moved under the first segment of their source;
    - ``mode_changes``: number of ``mode_set`` calls performed (0, 1 or 2).

    Bones that are not bendy (``bbone_segments <= 1``) are left untouched.
    ``deform_only`` skips bones whose ``use_deform`` is off; the original
    ``use_deform`` of every source is copied on its segments.
    ``reparent_children`` moves the children of each source under its first
    segment (the head, which does not bend), except the ones driven by a
    local transform constraint (see :func:`_has_local_transform_constraint`).
    """
    specs = collect_segment_specs(arm_obj, bone_names, deform_only=deform_only)
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

    source_was_deform = {
        s: bool(getattr(arm_obj.data.bones[s], "use_deform", True))
        for s in report["converted"]
    }
    skip_reparent = {
        bone.name
        for bone in arm_obj.data.bones
        if _has_local_transform_constraint(arm_obj, bone.name)
    }

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
            segment.use_deform = source_was_deform.get(spec["source"], True)
            segment.inherit_scale = "NONE"
            source_ebone = edit_bones[spec["source"]]
            for coll in getattr(source_ebone, "collections", ()):
                try:
                    coll.assign(segment)
                except Exception:
                    pass
        for source in report["converted"]:
            edit_bones[source].use_deform = False
        last_segment_of = {
            source: report["segments"][source][-1] for source in report["converted"]
        }
        if reparent_children:
            for source, last_segment in last_segment_of.items():
                for edit_bone in edit_bones:
                    if edit_bone.parent is None or edit_bone.parent.name != source:
                        continue
                    if edit_bone.name in report["converted"] or edit_bone.name in report["created"]:
                        continue
                    if edit_bone.name in skip_reparent:
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

    # BoneCollection.assign() only accepts a Bone, not an EditBone: the
    # collections are inherited again once the armature is back in OBJECT mode.
    for spec in specs:
        source_bone = arm_obj.data.bones.get(spec["source"])
        segment_bone = arm_obj.data.bones.get(spec["name"])
        if source_bone is None or segment_bone is None:
            continue
        for coll in getattr(source_bone, "collections", ()):
            try:
                coll.assign(segment_bone)
            except Exception:
                pass

    return report
