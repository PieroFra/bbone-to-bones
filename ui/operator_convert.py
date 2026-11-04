# SPDX-License-Identifier: GPL-3.0-or-later
"""Conversion operators of BBone to Bones: segments, revert and all-in-one."""

import bpy

from .. import core
from .operator_common import (
    _Progress,
    _bake_range,
    _bendy_bone_names,
    _pending_bone_names,
    _require_armature,
    _settings,
)


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
            deform_only = bool(getattr(settings, "deform_bones_only", True))
            if not _bendy_bone_names(
                arm_obj, selected_only=selected_only, deform_only=deform_only
            ):
                self.report({"ERROR"}, "No bendy bone with more than one segment in this armature")
                return {"CANCELLED"}
            pending = _pending_bone_names(
                arm_obj, selected_only=selected_only, deform_only=deform_only
            )
            if not pending:
                self.report({"ERROR"}, "Every bendy bone is already converted")
                return {"CANCELLED"}
            with _Progress(len(pending)) as progress:
                report = core.convert_bbones_to_segments(
                    arm_obj, bone_names=pending, deform_only=deform_only
                )
                progress.update(len(pending))
            if bool(getattr(settings, "add_live_follow", True)) and report["converted"]:
                core.add_bbone_follow_constraints(
                    arm_obj, bone_names=report["converted"]
                )
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
            deform_only = bool(getattr(settings, "deform_bones_only", True))
            pending = _pending_bone_names(
                arm_obj,
                selected_only=settings.selected_bones_only,
                deform_only=deform_only,
            )
            if not pending:
                raise ValueError("No bendy bone left to convert")
            meshes = core.find_rigged_meshes(arm_obj)
            if not meshes:
                raise ValueError("No mesh is rigged to this armature")
            frame_start, frame_end = _bake_range(context, settings)
            with _Progress(3) as progress:
                progress.update(1)
                conversion = core.convert_bbones_to_segments(
                    arm_obj, bone_names=pending, deform_only=deform_only
                )
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
