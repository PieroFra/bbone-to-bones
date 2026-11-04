# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers for the operators of BBone to Bones."""

import bpy

from .. import core


class _Progress:
    """Progress bar wrapper that never fails headless.

    ``window_manager.progress_begin`` is safe in background mode on some
    builds and missing on others, so every call is guarded: a missing progress
    bar must never abort the conversion.
    """

    def __init__(self, total):
        self.total = max(1, int(total))
        self.wm = None

    def __enter__(self):
        try:
            self.wm = bpy.context.window_manager
            self.wm.progress_begin(0, self.total)
        except Exception:  # noqa: BLE001  (headless: no progress bar at all)
            self.wm = None
        return self

    def update(self, step):
        """Move the bar to ``step`` (0..total), clamped and guarded."""
        if self.wm is None:
            return
        try:
            self.wm.progress_update(min(max(int(step), 0), self.total))
        except Exception:  # noqa: BLE001  (a broken bar is not an error)
            self.wm = None

    def __exit__(self, exc_type, exc_value, traceback):
        if self.wm is not None:
            try:
                self.wm.progress_end()
            except Exception:  # noqa: BLE001
                pass
        return False


def _require_armature(op, context):
    """Return the active ARMATURE object, or report the error and return None."""
    arm_obj = context.active_object
    if arm_obj is None or arm_obj.type != "ARMATURE":
        op.report({"ERROR"}, "Select an Armature object first")
        return None
    return arm_obj


def _settings(context):
    """Return the scene settings of the add-on."""
    settings = getattr(context.scene, "bbone_to_bones_settings", None)
    if settings is None:
        raise RuntimeError("BBone to Bones settings missing: register the add-on first")
    return settings


def _is_bone_selected(arm_obj, bone_name):
    """True when the bone or its pose bone is selected (4.2 / 5.x safe)."""
    pose_bone = arm_obj.pose.bones.get(bone_name)
    if pose_bone is not None and bool(getattr(pose_bone, "select", False)):
        return True
    bone = arm_obj.data.bones.get(bone_name)
    return bone is not None and bool(getattr(bone, "select", False))


def _bendy_bone_names(arm_obj, selected_only=False, deform_only=True):
    """Names of the bendy bones (``bbone_segments > 1``) of ``arm_obj``.

    The conversion clears ``use_deform`` on the source bone, so a bone that
    already owns its segment 0 still counts as a candidate. With
    ``selected_only`` a bone is kept when it is selected itself or when at
    least one of the segment bones it was converted into is selected.
    """
    bones = arm_obj.data.bones
    names = [
        bone.name
        for bone in bones
        if core.is_convertible_bone(bone, deform_only=deform_only)
        or (
            core.is_convertible_bone(bone, deform_only=False)
            and core.segment_bone_name(bone.name, 0) in bones
        )
    ]
    if not selected_only:
        return names
    kept = []
    for name in names:
        if _is_bone_selected(arm_obj, name):
            kept.append(name)
            continue
        count = int(getattr(arm_obj.data.bones[name], "bbone_segments", 1))
        if any(
            _is_bone_selected(arm_obj, core.segment_bone_name(name, index))
            for index in range(max(1, count))
        ):
            kept.append(name)
    return kept


def _converted_bone_names(arm_obj, selected_only=False, deform_only=True):
    """Bendy bones that already own a segment 0, i.e. are already converted."""
    bones = arm_obj.data.bones
    return [
        name
        for name in _bendy_bone_names(
            arm_obj, selected_only=selected_only, deform_only=deform_only
        )
        if core.segment_bone_name(name, 0) in bones
    ]


def _pending_bone_names(arm_obj, selected_only=False, deform_only=True):
    """Bendy bones still waiting for the conversion."""
    converted = set(
        _converted_bone_names(
            arm_obj, selected_only=selected_only, deform_only=deform_only
        )
    )
    return [
        name
        for name in _bendy_bone_names(
            arm_obj, selected_only=selected_only, deform_only=deform_only
        )
        if name not in converted
    ]


def _bake_range(context, settings):
    """``(start, end)`` of the bake: the scene range or the custom one."""
    if settings.use_scene_frame_range:
        return int(context.scene.frame_start), int(context.scene.frame_end)
    return int(settings.frame_start), int(settings.frame_end)


def _sample_count(frame_start, frame_end, step):
    """Frames sampled by the bake, used as progress total."""
    return len(range(int(frame_start), int(frame_end) + 1, max(1, int(step))))
