# SPDX-License-Identifier: GPL-3.0-or-later
"""Follow-constraint operators of BBone to Bones: add, remove and bake."""

import bpy

from .. import core
from .operator_common import (
    _Progress,
    _bake_range,
    _converted_bone_names,
    _require_armature,
    _sample_count,
    _settings,
)


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
            if settings.selected_bones_only and not sources:
                self.report({"ERROR"}, "No bendy bone selected")
                return {"CANCELLED"}
            report = core.add_bbone_follow_constraints(arm_obj, bone_names=sources)
        except (ValueError, RuntimeError, AttributeError, TypeError) as exc:
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
        except (ValueError, RuntimeError, AttributeError, TypeError) as exc:
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
            if settings.selected_bones_only and not sources:
                self.report({"ERROR"}, "No bendy bone selected")
                return {"CANCELLED"}
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
        except (ValueError, RuntimeError, AttributeError, TypeError) as exc:
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
