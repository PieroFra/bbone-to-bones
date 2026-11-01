# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel of BBone to Bones.

The panel only draws: it reads the active armature and the scene settings and
calls the operators of ui/operators.py. Every visible line stays short (at most
28 characters) so the labels fit any Sidebar width.
"""

import bpy


class VIEW3D_PT_BBoneToBones(bpy.types.Panel):
    """Rig status plus the four sections of the pipeline."""

    bl_label = "BBone to Bones"
    bl_idname = "VIEW3D_PT_BBoneToBones"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BBone to Bones"

    def draw(self, context):
        layout = self.layout
        arm_obj = context.active_object
        if arm_obj is None or arm_obj.type != "ARMATURE":
            layout.label(text="Select an Armature first", icon="ERROR")
            return
        settings = getattr(context.scene, "bbone_to_bones_settings", None)
        if settings is None:
            layout.label(text="Add-on not registered", icon="ERROR")
            return

        self.draw_status(layout, arm_obj)
        self.draw_segments(layout, settings)
        self.draw_follow(layout, settings)
        self.draw_pipeline(layout, arm_obj)
        self.draw_export(layout, settings)

    def draw_status(self, layout, arm_obj):
        """Armature name, bendy bones left, segments created and rigged meshes."""
        bones = arm_obj.data.bones
        bendy = sum(1 for bone in bones if int(getattr(bone, "bbone_segments", 1)) > 1)
        segments = sum(1 for bone in bones if "_seg_" in bone.name)
        meshes = sum(
            1
            for obj in bpy.context.scene.objects
            if obj.type == "MESH"
            and (
                any(m.type == "ARMATURE" and m.object == arm_obj for m in obj.modifiers)
                or (obj.parent == arm_obj and obj.parent_type == "ARMATURE")
            )
        )
        box = layout.box()
        box.label(text=arm_obj.name, icon="ARMATURE_DATA")
        box.label(text="Bendy bones: {0}".format(bendy))
        box.label(text="Segments: {0}".format(segments))
        box.label(text="Rigged meshes: {0}".format(meshes))

    def draw_segments(self, layout, settings):
        """Conversion, weight transfer and influence cap."""
        column = layout.column(align=True)
        column.label(text="Segments & Weights")
        column.operator("btob.convert_segments", text="Convert Segments")
        column.operator("btob.transfer_weights", text="Transfer Weights")
        column.prop(settings, "normalize_deform")
        column.prop(settings, "remove_source_weights")
        column.operator("btob.limit_influences", text="Limit Influences")
        column.prop(settings, "max_influences")

    def draw_follow(self, layout, settings):
        """Follow constraints and the bake range."""
        column = layout.column(align=True)
        column.label(text="Follow & Bake")
        column.operator("btob.add_constraints", text="Add Follow")
        column.operator("btob.remove_constraints", text="Remove Follow")
        column.prop(settings, "use_scene_frame_range")
        sub = column.column(align=True)
        sub.enabled = not settings.use_scene_frame_range
        sub.prop(settings, "frame_start")
        sub.prop(settings, "frame_end")
        column.prop(settings, "frame_step")
        column.prop(settings, "remove_constraints", text="Remove After Bake")
        column.operator("btob.bake_animation", text="Bake Animation")

    def draw_pipeline(self, layout, arm_obj):
        """One button for segments, weights and bake, plus non-destructive revert."""
        segments = sum(1 for bone in arm_obj.data.bones if "_seg_" in bone.name)
        column = layout.column(align=True)
        column.label(text="One-Click Pipeline")
        column.operator("btob.convert_all", text="Convert All", icon="PLAY")
        sub = column.column(align=True)
        sub.enabled = segments > 0
        sub.operator("btob.revert_to_bbones", text="Revert to BBones", icon="LOOP_BACK")

    def draw_export(self, layout, settings):
        """Engine preset, path and the export button."""
        column = layout.column(align=True)
        column.label(text="Export")
        column.prop(settings, "export_preset", text="Preset")
        column.prop(settings, "export_path", text="")
        column.prop(settings, "add_leaf_bones")
        column.operator("btob.export_rig", text="Export Rig")
