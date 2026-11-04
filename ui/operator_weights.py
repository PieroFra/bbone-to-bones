# SPDX-License-Identifier: GPL-3.0-or-later
"""Weight operators of BBone to Bones: transfer and influence cap."""

import bpy

from .. import core
from .operator_common import (
    _Progress,
    _converted_bone_names,
    _require_armature,
    _settings,
)


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
