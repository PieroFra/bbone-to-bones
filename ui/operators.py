# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators of BBone to Bones: thin wrappers over the core package.

Every operator validates the context, relays the outcome through the reports
and calls core; the math stays in core/.
"""

import os
import tempfile

import bpy

from .. import core
from .properties import with_preset_extension


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


def _bendy_bone_names(arm_obj, selected_only=False):
    """Names of the bendy bones (``bbone_segments > 1``) of ``arm_obj``.

    With ``selected_only`` a bone is kept when it is selected itself or when at
    least one of the segment bones it was converted into is selected.
    """
    names = [bone.name for bone in arm_obj.data.bones if core.is_convertible_bone(bone)]
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


def _converted_bone_names(arm_obj, selected_only=False):
    """Bendy bones that already own a segment 0, i.e. are already converted."""
    bones = arm_obj.data.bones
    return [
        name
        for name in _bendy_bone_names(arm_obj, selected_only=selected_only)
        if core.segment_bone_name(name, 0) in bones
    ]


def _pending_bone_names(arm_obj, selected_only=False):
    """Bendy bones still waiting for the conversion."""
    converted = set(_converted_bone_names(arm_obj, selected_only=selected_only))
    return [
        name
        for name in _bendy_bone_names(arm_obj, selected_only=selected_only)
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


class BTOB_OT_convert_segments(bpy.types.Operator):
    """Replace every bendy bone with a chain of regular bones."""

    bl_idname = "btob.convert_segments"
    bl_label = "Convert BBones to Segments"
    bl_description = "Replace every bendy bone with a chain of regular bones"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            selected_only = bool(settings.selected_bones_only)
            if not _bendy_bone_names(arm_obj, selected_only=selected_only):
                self.report({"ERROR"}, "No bendy bone with more than one segment in this armature")
                return {"CANCELLED"}
            pending = _pending_bone_names(arm_obj, selected_only=selected_only)
            if not pending:
                self.report({"ERROR"}, "Every bendy bone is already converted")
                return {"CANCELLED"}
            with _Progress(len(pending)) as progress:
                report = core.convert_bbones_to_segments(arm_obj, bone_names=pending)
                progress.update(len(pending))
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Converted {0} bendy bones into {1} segments".format(
                len(report["converted"]), len(report["created"])
            ),
        )
        return {"FINISHED"}


class BTOB_OT_transfer_weights(bpy.types.Operator):
    """Move the bendy-bone weights onto the converted segments."""

    bl_idname = "btob.transfer_weights"
    bl_label = "Transfer Skin Weights"
    bl_description = "Split the bendy-bone weights on the converted segments"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        if not _converted_bone_names(arm_obj):
            self.report({"ERROR"}, "No converted segments: convert the bendy bones first")
            return {"CANCELLED"}
        meshes = core.find_rigged_meshes(arm_obj)
        if not meshes:
            self.report({"ERROR"}, "No mesh is rigged to this armature")
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            with _Progress(len(meshes)) as progress:
                report = core.transfer_bbone_weights(
                    arm_obj,
                    mesh_objs=meshes,
                    normalize_deform=settings.normalize_deform,
                    remove_source_weights=settings.remove_source_weights,
                )
                progress.update(len(meshes))
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Transferred {0} sources on {1} meshes".format(
                len(report["sources"]), len(report["meshes"])
            ),
        )
        return {"FINISHED"}


class BTOB_OT_add_constraints(bpy.types.Operator):
    """Make every segment follow its bendy-bone segment."""

    bl_idname = "btob.add_constraints"
    bl_label = "Add Follow Constraints"
    bl_description = "Add one follow constraint per converted segment"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            sources = (
                _converted_bone_names(arm_obj, selected_only=True)
                if settings.selected_bones_only
                else None
            )
            report = core.add_bbone_follow_constraints(arm_obj, bone_names=sources)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if report["missing"] and not report["constrained"]:
            self.report({"ERROR"}, "No converted segment to constrain")
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Constrained {0} segments ({1} missing)".format(
                len(report["constrained"]), len(report["missing"])
            ),
        )
        return {"FINISHED"}


class BTOB_OT_remove_constraints(bpy.types.Operator):
    """Delete the follow constraints of the converted segments."""

    bl_idname = "btob.remove_constraints"
    bl_label = "Remove Follow Constraints"
    bl_description = "Delete the follow constraints added by the add-on"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            sources = (
                _converted_bone_names(arm_obj, selected_only=True)
                if settings.selected_bones_only
                else None
            )
            removed = core.remove_bbone_follow_constraints(arm_obj, bone_names=sources)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Removed {0} follow constraints".format(removed))
        return {"FINISHED"}


class BTOB_OT_bake_animation(bpy.types.Operator):
    """Bake the bendy-bone motion into keyframes on the segments."""

    bl_idname = "btob.bake_animation"
    bl_label = "Bake Segment Animation"
    bl_description = "Key the segment motion over the chosen frame range"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        if not _converted_bone_names(arm_obj):
            self.report({"ERROR"}, "No converted segments: convert the bendy bones first")
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            frame_start, frame_end = _bake_range(context, settings)
            step = int(settings.frame_step)
            samples = _sample_count(frame_start, frame_end, step)
            sources = (
                _converted_bone_names(arm_obj, selected_only=True)
                if settings.selected_bones_only
                else None
            )
            with _Progress(samples) as progress:
                report = core.bake_segments_animation(
                    arm_obj,
                    frame_start=frame_start,
                    frame_end=frame_end,
                    step=step,
                    bone_names=sources,
                    remove_constraints=settings.remove_constraints,
                    bake_all_actions=settings.bake_all_actions,
                )
                progress.update(samples)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Baked {0} bones on {1} samples ({2}-{3} step {4})".format(
                len(report["baked"]),
                samples,
                report["frame_start"],
                report["frame_end"],
                report["step"],
            ),
        )
        return {"FINISHED"}


class BTOB_OT_limit_influences(bpy.types.Operator):
    """Cap the deforming influences of every vertex."""

    bl_idname = "btob.limit_influences"
    bl_label = "Limit Vertex Influences"
    bl_description = "Keep only the strongest deforming groups per vertex"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        meshes = core.find_rigged_meshes(arm_obj)
        if not meshes:
            self.report({"ERROR"}, "No mesh is rigged to this armature")
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            with _Progress(len(meshes)) as progress:
                report = core.limit_vertex_influences(
                    arm_obj, max_influences=settings.max_influences
                )
                progress.update(len(meshes))
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Capped {0} vertices to {1} influences".format(
                report["capped_vertices"], report["max_influences"]
            ),
        )
        return {"FINISHED"}


class BTOB_OT_export_rig(bpy.types.Operator):
    """Export the converted rig with the flags of the chosen engine."""

    bl_idname = "btob.export_rig"
    bl_label = "Export Rig"
    bl_description = "Export the rig and its meshes with the engine preset"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(
        name="Filepath",
        description="Override the export path of the settings",
        subtype="FILE_PATH",
        default="",
    )

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            raw_path = settings.export_path
            if self.filepath:
                path = self.filepath
            else:
                if not os.path.isabs(raw_path):
                    if bpy.data.is_saved:
                        raw_path = bpy.path.abspath(raw_path)
                    else:
                        raw_path = os.path.join(tempfile.gettempdir(), raw_path)
                path = with_preset_extension(raw_path, settings.export_preset)
            if not path:
                raise ValueError("Export path is empty")
            with _Progress(1) as progress:
                report = core.export_rig(
                    arm_obj,
                    path,
                    preset=settings.export_preset,
                    add_leaf_bones=settings.add_leaf_bones,
                    max_influences=settings.max_influences,
                    export_all_actions=settings.bake_all_actions,
                    disable_preserve_vol=settings.disable_preserve_volume,
                )
                progress.update(1)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Exported {0} with preset {1} to {2}".format(
                report["format"], report["preset"], report["filepath"]
            ),
        )
        return {"FINISHED"}


class BTOB_OT_revert_to_bbones(bpy.types.Operator):
    """Delete the converted segments and give the bendy bones their skin back."""

    bl_idname = "btob.revert_to_bbones"
    bl_label = "Revert to BBones"
    bl_description = "Delete the converted segments and move their weights back on the bendy bones"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            sources = (
                _converted_bone_names(arm_obj, selected_only=True)
                if settings.selected_bones_only
                else None
            )
            report = core.revert_segments_to_bbones(arm_obj, bone_names=sources)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not report["reverted"]:
            self.report({"ERROR"}, "No converted segment to revert")
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Reverted {0} bendy bones, removed {1} segments".format(
                len(report["reverted"]), len(report["removed_segments"])
            ),
        )
        return {"FINISHED"}


class BTOB_OT_convert_all(bpy.types.Operator):
    """Run segments, weights and bake in one click."""

    bl_idname = "btob.convert_all"
    bl_label = "Convert All (Segments + Weights + Bake)"
    bl_description = "Convert the bendy bones, transfer the weights and bake the motion"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            pending = _pending_bone_names(
                arm_obj, selected_only=settings.selected_bones_only
            )
            if not pending:
                raise ValueError("No bendy bone left to convert")
            meshes = core.find_rigged_meshes(arm_obj)
            if not meshes:
                raise ValueError("No mesh is rigged to this armature")
            frame_start, frame_end = _bake_range(context, settings)
            with _Progress(3) as progress:
                progress.update(1)
                conversion = core.convert_bbones_to_segments(arm_obj, bone_names=pending)
                progress.update(2)
                weights = core.transfer_bbone_weights(
                    arm_obj,
                    mesh_objs=meshes,
                    normalize_deform=settings.normalize_deform,
                    remove_source_weights=settings.remove_source_weights,
                )
                progress.update(3)
                bake = core.bake_segments_animation(
                    arm_obj,
                    frame_start=frame_start,
                    frame_end=frame_end,
                    step=int(settings.frame_step),
                    bone_names=pending,
                    remove_constraints=settings.remove_constraints,
                    bake_all_actions=settings.bake_all_actions,
                )
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Converted {0}, weighted {1} sources, baked {2} bones".format(
                len(conversion["converted"]), len(weights["sources"]), len(bake["baked"])
            ),
        )
        return {"FINISHED"}
