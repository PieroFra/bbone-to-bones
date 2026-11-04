# SPDX-License-Identifier: GPL-3.0-or-later
"""Export operator of BBone to Bones."""

import os
import tempfile

import bpy

from .. import core
from .operator_common import _Progress, _require_armature, _settings
from .properties import with_preset_extension


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

    def invoke(self, context, event):
        if self.filepath:
            return self.execute(context)
        settings = _settings(context)
        if (
            not bpy.app.background
            and hasattr(context, "window_manager")
            and (
                not settings.export_path
                or (
                    settings.export_path == "rig_export.fbx"
                    and not bpy.data.is_saved
                )
            )
        ):
            self.filepath = with_preset_extension(
                settings.export_path or "rig_export.fbx", settings.export_preset
            )
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        return self.execute(context)

    def execute(self, context):
        arm_obj = _require_armature(self, context)
        if arm_obj is None:
            return {"CANCELLED"}
        try:
            settings = _settings(context)
            raw_path = settings.export_path
            if self.filepath:
                settings.export_path = with_preset_extension(
                    self.filepath, settings.export_preset
                )
                path = settings.export_path
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
