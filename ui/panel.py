# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel of BBone to Bones.

The panel only draws: it reads the active armature and the scene settings and
calls the operators of ui/operators.py. Every visible line stays short (at most
28 characters) so the labels fit any Sidebar width.
"""

import bpy

# The panel lives in its own tab alone.
DEFAULT_CATEGORY = "BBone to Bones"


def _iter_action_fcurves(action):
    """Yield the F-Curves of an action, legacy (4.2) or slotted (5.x) layout."""
    legacy = getattr(action, "fcurves", None)
    if legacy:
        yield from legacy
        return
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channelbag in getattr(strip, "channelbags", ()):
                yield from getattr(channelbag, "fcurves", ())


def _has_baked_segments(action):
    """True when an action keys at least one ``_seg_`` segment channel."""
    return any("_seg_" in fcurve.data_path for fcurve in _iter_action_fcurves(action))


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
        self.draw_pipeline(layout, arm_obj, settings)
        self.draw_segments(layout, arm_obj, settings)
        self.draw_follow(layout, arm_obj, settings)
        self.draw_export(layout, arm_obj, settings)
        self.draw_suite_bridge(layout)

    def _rig_state(self, arm_obj, settings):
        """Collect the rig facts shared by the status box and the buttons.

        ``deform_bbones`` counts bendy bones that deform or are already
        converted, ``skipped_bbones`` the ones left out (e.g. MCH bones),
        ``converted_bbones`` the ones with a ``_seg_00`` child and
        ``pending_bbones`` the candidates still to convert.
        """
        bones = arm_obj.data.bones
        deform_bbones = 0
        skipped_bbones = 0
        converted_bbones = 0
        pending_bbones = 0
        for bone in bones:
            if int(getattr(bone, "bbone_segments", 1)) <= 1:
                continue
            converted = "{0}_seg_00".format(bone.name) in bones
            if converted:
                converted_bbones += 1
            if bone.use_deform or converted:
                deform_bbones += 1
            else:
                skipped_bbones += 1
            if not converted and (
                settings is None
                or not settings.deform_bones_only
                or bone.use_deform
            ):
                pending_bbones += 1
        segments = sum(1 for bone in bones if "_seg_" in bone.name)
        has_follow = any(
            constraint.name == "BTOB_FollowBBone"
            for pose_bone in arm_obj.pose.bones
            if "_seg_" in pose_bone.name
            for constraint in pose_bone.constraints
        )
        is_baked = False
        if segments > 0 and not has_follow:
            animation_data = arm_obj.animation_data
            action = animation_data.action if animation_data is not None else None
            if action is not None:
                is_baked = _has_baked_segments(action)
        return {
            "deform_bbones": deform_bbones,
            "skipped_bbones": skipped_bbones,
            "converted_bbones": converted_bbones,
            "pending_bbones": pending_bbones,
            "segments": segments,
            "has_follow": has_follow,
            "is_baked": is_baked,
        }

    def draw_status(self, layout, arm_obj):
        """Armature name, bendy bones left, segments created and rigged meshes."""
        state = self._rig_state(arm_obj, None)
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
        if state["skipped_bbones"] > 0:
            box.label(
                text="Deform BBones: {0} ({1} skip)".format(
                    state["deform_bbones"], state["skipped_bbones"]
                )
            )
        else:
            box.label(text="Deform BBones: {0}".format(state["deform_bbones"]))
        segments = state["segments"]
        if segments == 0:
            box.label(text="Segments: 0 (Ready)")
        elif state["has_follow"]:
            box.label(text="Segments: {0} (Follow: ON)".format(segments))
        elif state["is_baked"]:
            box.label(text="Segments: {0} (Baked: YES)".format(segments))
        else:
            box.label(text="Segments: {0} (Static)".format(segments))
        box.label(text="Rigged meshes: {0}".format(meshes))

    def draw_pipeline(self, layout, arm_obj, settings):
        """One button for segments, weights and bake, plus non-destructive revert."""
        state = self._rig_state(arm_obj, settings)
        box = layout.box()
        col = box.column(align=True)
        col.label(text="One-Click Pipeline", icon="PLAY")
        row_conv = col.row(align=True)
        row_conv.enabled = state["pending_bbones"] > 0
        row_conv.operator("btob.convert_all", text="Convert All", icon="PLAY")
        row_rev = col.row(align=True)
        row_rev.enabled = state["segments"] > 0
        row_rev.operator("btob.revert_to_bbones", text="Revert to BBones", icon="LOOP_BACK")

    def draw_segments(self, layout, arm_obj, settings):
        """Conversion, weight transfer and influence cap."""
        state = self._rig_state(arm_obj, settings)
        box = layout.box()
        col = box.column(align=True)
        col.label(text="1. Segments & Weights", icon="BONE_DATA")
        col.prop(settings, "deform_bones_only", text="Deform Bones Only")
        col.prop(settings, "selected_bones_only", text="Selected Bones Only")
        col.prop(settings, "add_live_follow", text="Live Follow Preview")
        if state["pending_bbones"] == 0 and state["converted_bbones"] > 0:
            row_done = col.row(align=True)
            row_done.enabled = False
            row_done.operator(
                "btob.convert_segments",
                text="All {0} BBones Converted".format(state["converted_bbones"]),
                icon="CHECKMARK",
            )
        else:
            row_conv = col.row(align=True)
            row_conv.enabled = state["pending_bbones"] > 0
            row_conv.operator("btob.convert_segments", text="Convert Segments")
        row_tw = col.row(align=True)
        row_tw.enabled = state["segments"] > 0
        row_tw.operator("btob.transfer_weights", text="Transfer Weights")
        col.prop(settings, "normalize_deform")
        col.prop(settings, "remove_source_weights")
        col.operator("btob.limit_influences", text="Limit Influences")
        col.prop(settings, "max_influences")

    def draw_follow(self, layout, arm_obj, settings):
        """Follow constraints and the bake range."""
        state = self._rig_state(arm_obj, settings)
        box = layout.box()
        col = box.column(align=True)
        col.label(text="2. Live Follow & Bake", icon="CONSTRAINT_BONE")
        row_af = col.row(align=True)
        row_af.enabled = state["segments"] > 0
        row_af.operator("btob.add_constraints", text="Add Follow")
        row_rf = col.row(align=True)
        row_rf.enabled = state["segments"] > 0 and state["has_follow"]
        row_rf.operator("btob.remove_constraints", text="Remove Follow")
        col.prop(settings, "use_scene_frame_range")
        sub = col.column(align=True)
        sub.enabled = not settings.use_scene_frame_range
        sub.prop(settings, "frame_start")
        sub.prop(settings, "frame_end")
        col.prop(settings, "frame_step")
        col.prop(settings, "bake_all_actions", text="All Actions")
        col.prop(settings, "remove_constraints", text="Remove After Bake")
        row_bake = col.row(align=True)
        row_bake.enabled = state["segments"] > 0
        row_bake.operator("btob.bake_animation", text="Bake Animation")

    def draw_export(self, layout, arm_obj, settings):
        """Engine preset, path and the export button."""
        box = layout.box()
        col = box.column(align=True)
        col.label(text="3. Export", icon="EXPORT")
        col.prop(settings, "export_preset", text="Preset")
        col.prop(settings, "export_path", text="")
        col.prop(settings, "add_leaf_bones")
        col.prop(settings, "disable_preserve_volume", text="Linear Skin (LBS)")
        col.operator("btob.export_rig", text="Export Rig", icon="EXPORT")

    def draw_suite_bridge(self, layout):
        """Quick handoff buttons when CTRL_DEF or ACTD are active."""
        has_ctrl = getattr(bpy.types, "CTRLDEF_PT_panel", None) is not None
        has_actd = getattr(bpy.types, "ACTD_PT_MainPanel", None) is not None
        if not has_ctrl and not has_actd:
            return
        column = layout.column(align=True)
        column.label(text="Rigging Suite", icon="LINKED")
        if has_ctrl:
            try:
                column.operator("ctrl_def.generate", text="Generate CTRL")
            except (ValueError, TypeError, RuntimeError):
                pass
            try:
                column.operator("ctrl_def.bind_actd", text="Bind CTRL to DEF")
            except (ValueError, TypeError, RuntimeError):
                pass
        if has_actd:
            try:
                column.operator("actd.apply_transforms", text="Apply ACTD")
            except (ValueError, TypeError, RuntimeError):
                pass

