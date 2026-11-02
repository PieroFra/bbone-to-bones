# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel of BBone to Bones.

The panel only draws: it reads the active armature and the scene settings and
calls the operators of ui/operators.py. Every visible line stays short (at most
28 characters) so the labels fit any Sidebar width.
"""

import bpy

# The panel lives in its own tab alone, or shares the tab with the companion
# add-ons of the suite when at least one of them is active.
DEFAULT_CATEGORY = "BBone to Bones"
SUITE_CATEGORY = "Rigging Suite"


class VIEW3D_PT_BBoneToBones(bpy.types.Panel):
    """Rig status plus the four sections of the pipeline."""

    bl_label = "BBone to Bones"
    bl_idname = "VIEW3D_PT_BBoneToBones"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = DEFAULT_CATEGORY

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
        self.draw_suite_bridge(layout)

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
        column.prop(settings, "selected_bones_only")
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

    def draw_suite_bridge(self, layout):
        """Quick handoff buttons when CTRL_DEF or ACTD are active."""
        has_ctrl = getattr(bpy.types, "CTRLDEF_PT_panel", None) is not None
        has_actd = getattr(bpy.types, "ACTD_PT_MainPanel", None) is not None
        if not has_ctrl and not has_actd:
            return
        column = layout.column(align=True)
        column.label(text="Rigging Suite", icon="LINKED")
        if has_ctrl:
            column.operator("ctrl_def.generate", text="Generate CTRL")
            column.operator("ctrl_def.bind_actd", text="Bind CTRL to DEF")
        if has_actd:
            column.operator("actd.apply_transforms", text="Apply ACTD")


def sync_rigging_suite_tabs(unregistering=False):
    """Move the panels of the suite under one tab when companions are active."""
    ctrl_cls = getattr(bpy.types, "CTRLDEF_PT_panel", None)
    actd_names = (
        "ACTD_PT_MainPanel",
        "ACTD_PT_SubPanel_Advanced",
        "ACTD_PT_SubPanel_Collections",
        "ACTD_PT_SubPanel_Baking",
        "ACTD_PT_SubPanel_Presets",
    )
    actd_classes = [getattr(bpy.types, name, None) for name in actd_names]
    actd_classes = [cls for cls in actd_classes if cls is not None]

    active_count = (
        int(ctrl_cls is not None)
        + int(bool(actd_classes))
        + (0 if unregistering else 1)
    )
    use_suite = active_count >= 2

    def _rebind_panels(classes, category, top_order=None):
        """Re-register the panels under another category, only when needed."""
        registered = [cls for cls in classes if getattr(cls, "is_registered", False)]
        if not registered:
            return
        same_category = all(
            getattr(cls, "bl_category", None) == category for cls in registered
        )
        same_order = all(
            getattr(cls, "bl_order", None) == top_order
            for cls in registered
            if top_order is not None and not getattr(cls, "bl_parent_id", "")
        )
        if same_category and same_order:
            return
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        for cls in registered:
            cls.bl_category = category
            if top_order is not None and not getattr(cls, "bl_parent_id", ""):
                cls.bl_order = top_order
        for cls in registered:
            bpy.utils.register_class(cls)

    if ctrl_cls is not None:
        _rebind_panels(
            [ctrl_cls],
            SUITE_CATEGORY if use_suite else "DEF Ctrl",
            top_order=10 if use_suite else 0,
        )
    if actd_classes:
        _rebind_panels(
            actd_classes,
            SUITE_CATEGORY if use_suite else "Auto Copy Transforms",
            top_order=20 if use_suite else 0,
        )
    if not unregistering and getattr(VIEW3D_PT_BBoneToBones, "is_registered", False):
        _rebind_panels(
            [VIEW3D_PT_BBoneToBones],
            SUITE_CATEGORY if use_suite else DEFAULT_CATEGORY,
            top_order=30 if use_suite else 0,
        )
    if unregistering:
        VIEW3D_PT_BBoneToBones.bl_category = DEFAULT_CATEGORY
    return SUITE_CATEGORY if use_suite else DEFAULT_CATEGORY
