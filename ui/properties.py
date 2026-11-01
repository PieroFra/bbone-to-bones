# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings of BBone to Bones: the PropertyGroup stored on the Scene.

Every value here is drawn by ui/panel.py and read by ui/operators.py; nothing
in this module touches the rig itself.
"""

import bpy


class BBoneToBonesSettings(bpy.types.PropertyGroup):
    """Options of the conversion pipeline, one instance per scene."""

    normalize_deform: bpy.props.BoolProperty(
        name="Normalize Deform Weights",
        description="Scale the deform weights of every vertex back to 1.0",
        default=True,
    )
    remove_source_weights: bpy.props.BoolProperty(
        name="Clear Source Weights",
        description="Clear the weights left on the bendy bones after the transfer",
        default=True,
    )
    use_scene_frame_range: bpy.props.BoolProperty(
        name="Use Scene Frame Range",
        description="Bake the scene frame range instead of the custom one",
        default=True,
    )
    frame_start: bpy.props.IntProperty(
        name="Start Frame",
        description="First frame of the custom bake range",
        default=1,
        min=0,
    )
    frame_end: bpy.props.IntProperty(
        name="End Frame",
        description="Last frame of the custom bake range",
        default=30,
        min=0,
    )
    frame_step: bpy.props.IntProperty(
        name="Frame Step",
        description="Sample every N frames while baking",
        default=1,
        min=1,
        max=100,
    )
    remove_constraints: bpy.props.BoolProperty(
        name="Remove Constraints After Bake",
        description="Delete the follow constraints once the bake is keyed",
        default=True,
    )
    export_preset: bpy.props.EnumProperty(
        name="Engine Preset",
        description="Export flags of the target engine",
        items=(
            ("UNITY", "Unity (FBX)", "FBX preset for Unity"),
            ("UNREAL", "Unreal (FBX)", "FBX preset for Unreal Engine"),
            ("GODOT", "Godot (glTF)", "glTF preset for Godot"),
        ),
        default="UNITY",
    )
    max_influences: bpy.props.IntProperty(
        name="Max Influences",
        description="Maximum number of deforming groups per vertex",
        default=4,
        min=1,
        max=8,
    )
    add_leaf_bones: bpy.props.BoolProperty(
        name="Add Leaf Bones",
        description="Add the leaf bones of the FBX exporter (usually unwanted)",
        default=False,
    )
    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="File written by the export operator",
        subtype="FILE_PATH",
        default="//rig_export.fbx",
    )
