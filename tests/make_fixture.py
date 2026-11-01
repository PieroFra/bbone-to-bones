# -*- coding: utf-8 -*-
"""Deterministic headless fixture for BBone to Bones tests.

Builds, in memory (with read_factory_settings use_empty), the test scene
required by the project plan:

- one armature: object `RigTest`, armature data `ArmDataTest`;
- one static parent bone `Hip` (no bendy bones on it);
- THREE bendy chains (4 bones each, 8 bbone segments per bone):
  * Chain A (`BendyA.000`..`BendyA.003`): straight, default curve/ease/roll;
  * Chain B (`BendyB.000`..`BendyB.003`): curved offset (bend != 0), 30-degree
    pose bend keyed at frame 30;
  * Chain C (`BendyC.000`..`BendyC.003`): roll variance (non-zero roll per
    bone + bbone rollin/rolout) and non-uniform bbone scale;
- two meshes linked to the armature:
  * object `BodyHigh` with mesh data `MeshHighData` (object name != mesh data
    name), parented to the armature with a NON-identical matrix_world
    (translation + rotation + non-uniform scale) and an armature modifier;
  * object `BodyLow` with mesh data `BodyLow` (names equal), parented with
    identity matrix and an armature modifier;
- vertex groups on both meshes for the Chain A bones, all verts assigned to
  `BendyA.000` (weight 1.0);
- a 30-frame animation (scene.frame_start=1, scene.frame_end=30) keying the
  rotation of the three bendy root bones and the bbone bend of Chain B.

Usage (headless):
    blender -b --python tests/make_fixture.py            # build + validate report
    blender -b --python tests/make_fixture.py -- save    # + save tests/fixture.blend
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CHAIN_PREFIX = "Bendy"
CHAIN_NAMES = ("A", "B", "C")
BONES_PER_CHAIN = 4
BBONE_SEGMENTS = 8
HIP_NAME = "Hip"
SCENE_FRAME_START = 1
SCENE_FRAME_END = 30

PAIRS = (
    # (object name, mesh data name, non-identical matrix)
    ("BodyHigh", "MeshHighData", True),
    ("BodyLow", "BodyLow", False),
)


def _chain_origin(index):
    """Spread the chains apart on X so bend curves never overlap."""
    return -2.0 + index * 2.0


def _build_armature(scene):
    """Create the armature object, the Hip bone and the three bendy chains."""
    import bpy

    arm_data = bpy.data.armatures.new("ArmDataTest")
    arm_obj = bpy.data.objects.new("RigTest", arm_data)
    scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = arm_data.edit_bones

    hip = edit_bones.new(HIP_NAME)
    hip.head = (0.0, 0.0, 1.2)
    hip.tail = (0.0, 0.0, 1.8)

    for index, letter in enumerate(CHAIN_NAMES):
        origin_x = _chain_origin(index)
        previous = None
        for seg in range(BONES_PER_CHAIN):
            name = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
            bone = edit_bones.new(name)
            z0 = 2.0 + seg * 0.6
            bone.head = (origin_x, 0.0, z0)
            bone.tail = (origin_x, 0.0, z0 + 0.6)
            if letter == "C":
                # Roll variance exercises Fase 2 equivalence (roll handling).
                bone.roll = math.radians(15.0 * (seg + 1))
            if previous is None:
                # Chain A root stays unparented; B and C roots go under Hip.
                if letter in ("B", "C"):
                    bone.parent = hip
                    bone.use_connect = True
            else:
                bone.parent = previous
                bone.use_connect = True
            previous = bone

    bpy.ops.object.mode_set(mode="OBJECT")

    # Bendy parameters on the (non-pose) bone data.
    for index, letter in enumerate(CHAIN_NAMES):
        for seg in range(BONES_PER_CHAIN):
            name = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
            bone = arm_data.bones[name]
            bone.bbone_segments = BBONE_SEGMENTS
        if letter == "B":
            # Bend offset on the whole chain via the root bone.
            arm_data.bones["{0}B.000".format(CHAIN_PREFIX)].bbone_curveinx = 0.8
        if letter == "C":
            for seg in range(BONES_PER_CHAIN):
                name = "{0}C.{1:03d}".format(CHAIN_PREFIX, seg)
                bone = arm_data.bones[name]
                bone.bbone_scalein = (0.80, 1.00, 1.25)
                bone.bbone_scaleout = (1.10, 1.00, 0.90)
                bone.bbone_rollin = math.radians(20.0 + 5.0 * seg)
                bone.bbone_rollout = math.radians(-10.0 - 3.0 * seg)

    return arm_data, arm_obj


def _build_mesh(scene, arm_obj, obj_name, mesh_name, non_identity):
    """Create one mesh object parented to the armature with an armature modifier."""
    import bpy
    from mathutils import Matrix

    mesh_data = bpy.data.meshes.new(mesh_name)
    side = 5
    verts = [
        (float(u) * 0.2 - 0.4, float(v) * 0.1 - 0.2, 2.0 + float(w) * 0.15)
        for u in range(side)
        for v in range(2)
        for w in range(2)
    ]
    faces = [
        (u * 4 + 0, u * 4 + 1, (u + 1) * 4 + 1, (u + 1) * 4 + 0)
        for u in range(side - 1)
    ] + [
        (u * 4 + 2, u * 4 + 3, (u + 1) * 4 + 3, (u + 1) * 4 + 2)
        for u in range(side - 1)
    ]
    mesh_data.from_pydata(verts, [], faces)
    for poly in mesh_data.polygons:
        poly.use_smooth = True
    mesh_data.validate()
    mesh_data.update()

    mesh_obj = bpy.data.objects.new(obj_name, mesh_data)
    scene.collection.objects.link(mesh_obj)
    if non_identity:
        from mathutils import Euler

        mesh_obj.location = (1.2, 0.0, 0.5)
        mesh_obj.rotation_euler = Euler((0.2, 0.0, 0.3), "XYZ")
        mesh_obj.scale = (1.1, 1.0, 0.9)
    mesh_obj.parent = arm_obj

    modifier = mesh_obj.modifiers.new(name="ArmRig", type="ARMATURE")
    modifier.object = arm_obj

    # Vertex groups for the Chain A bones; every vertex weighted on the root.
    for seg in range(BONES_PER_CHAIN):
        group_name = "{0}A.{1:03d}".format(CHAIN_PREFIX, seg)
        if group_name not in mesh_obj.vertex_groups:
            mesh_obj.vertex_groups.new(name=group_name)
    root_group = mesh_obj.vertex_groups["{0}A.000".format(CHAIN_PREFIX)]
    root_group.add(list(range(len(verts))), 1.0, "REPLACE")

    # Sanity: non_identity => matrix_world must differ from identity.
    bpy.context.view_layer.update()
    identity = Matrix.Identity(4)
    if non_identity:
        delta = max(
            abs(mesh_obj.matrix_world[i][j] - identity[i][j])
            for i in range(4)
            for j in range(4)
        )
        if delta <= 1e-9:
            raise RuntimeError("matrix_world is supposed to be non-identical")
    return mesh_obj


def _build_animation(scene, arm_obj):
    """Key the bendy roots' rotation (frames 1 and 30) and Chain B's bend."""
    import bpy

    for letter in CHAIN_NAMES:
        name = "{0}{1}.000".format(CHAIN_PREFIX, letter)
        pose_bone = arm_obj.pose.bones[name]
        pose_bone.rotation_mode = "XYZ"
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
    pose_bone_b = arm_obj.pose.bones["{0}B.000".format(CHAIN_PREFIX)]

    scene.frame_set(SCENE_FRAME_START)
    for letter in CHAIN_NAMES:
        bone = arm_obj.pose.bones["{0}{1}.000".format(CHAIN_PREFIX, letter)]
        bone.keyframe_insert("rotation_euler", frame=SCENE_FRAME_START)
    pose_bone_b.keyframe_insert("bbone_curveinx", frame=SCENE_FRAME_START)

    scene.frame_set(SCENE_FRAME_END)
    import math

    for letter in CHAIN_NAMES:
        bone = arm_obj.pose.bones["{0}{1}.000".format(CHAIN_PREFIX, letter)]
        bone.rotation_euler = (0.0, math.radians(30.0), 0.0)
        bone.keyframe_insert("rotation_euler", frame=SCENE_FRAME_END)
    # Pose bbone bend animates on top of the data bend (0.8 stays in the data
    # block): equivalent does not overwrite the data block value.
    pose_bone_b.bbone_curveinx = 1.4
    pose_bone_b.keyframe_insert("bbone_curveinx", frame=SCENE_FRAME_END)

    # Interpolation mode Linear for a monotonic curve between the keys.
    def _fcurves(action):
        """Explicit fallback: legacy fcurves (<=4.3) vs slot API (4.4+/5.x)."""
        legacy = getattr(action, "fcurves", None)
        if legacy is not None:
            return legacy
        curves = []
        for layer in action.layers:
            for strip in layer.strips:
                for channelbag in strip.channelbags:
                    curves.extend(channelbag.fcurves)
        return curves

    for action in bpy.data.actions:
        for fcurve in _fcurves(action):
            for kp in fcurve.keyframe_points:
                kp.interpolation = "LINEAR"
    scene.frame_set(SCENE_FRAME_START)


def build():
    """Build the whole fixture scene in memory and return the key objects."""
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start = SCENE_FRAME_START
    scene.frame_end = SCENE_FRAME_END

    arm_data, arm_obj = _build_armature(scene)
    mesh_objs = [
        _build_mesh(scene, arm_obj, obj_name, mesh_name, non_identity)
        for (obj_name, mesh_name, non_identity) in PAIRS
    ]
    _build_animation(scene, arm_obj)
    return scene, arm_obj, mesh_objs


def main():
    import bpy

    argv = sys.argv
    save_flag = "--" in argv and "save" in argv[argv.index("--") + 1:]
    scene, arm_obj, mesh_objs = build()
    if save_flag:
        fixture_path = os.path.join(HERE, "fixture.blend")
        bpy.ops.wm.save_as_mainfile(filepath=fixture_path)
        print("FIXTURE saved -> {0}".format(fixture_path))
    print("FIXTURE bones={0} meshes={1} frames={2}..{3}".format(
        len(arm_obj.data.bones), len(mesh_objs), scene.frame_start, scene.frame_end))


if __name__ == "__main__":
    main()
