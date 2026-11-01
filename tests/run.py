# -*- coding: utf-8 -*-
"""Headless test runner for BBone to Bones.

It rebuilds the fixture in memory (no binary .blend needed) and runs the
project checks of the current phase contract. Designed to be extended one
check per feature (Fase 1 heads, Fase 2 pose equivalence, Fase 3 animation
frame sweep, Fase 4 reimport compare).

Usage:
    blender -b --python tests/run.py                  # full run
    blender -b --python tests/run.py -- save-fixture  # + save tests/fixture.blend

The verdict is the LAST line of stdout:
    RISULTATO passati=X falliti=Y totale=N
always with exit code 0 (parse the verdict from the log, do not trust the
exit code).
"""

import os
import sys
import tomllib  # Python 3.11+ ships inside Blender 4.2+/5.x

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RESULTS = []

sys.path.insert(0, HERE)
from make_fixture import (  # noqa: E402
    BBONE_SEGMENTS,
    BONES_PER_CHAIN,
    CHAIN_NAMES,
    CHAIN_PREFIX,
    HIP_NAME,
    PAIRS,
    SCENE_FRAME_END,
    SCENE_FRAME_START,
    build,
)


def check(name, fn):
    """Record a check result without aborting the rest."""
    try:
        detail = fn()
        RESULTS.append((name, True, detail or ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, "{0}: {1}".format(type(exc).__name__, exc)))


# --- checks -----------------------------------------------------------------


def _chain_bones(arm_obj, letter):
    return [
        "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg) for seg in range(BONES_PER_CHAIN)
    ]


def do_chains(scene, arm_obj):
    """Counts and bbone segments."""
    expected_bones = 1 + len(CHAIN_NAMES) * BONES_PER_CHAIN
    if len(arm_obj.data.bones) != expected_bones:
        raise AssertionError("bone count {0} != {1}".format(len(arm_obj.data.bones), expected_bones))
    for letter in CHAIN_NAMES:
        for name in _chain_bones(arm_obj, letter):
            bone = arm_obj.data.bones[name]
            if getattr(bone, "bbone_segments", 0) != BBONE_SEGMENTS:
                raise AssertionError("{0} bbone_segments={1}".format(name, getattr(bone, "bbone_segments", 0)))
    return "{0} bendy bones, segments={1}".format(expected_bones - 1, BBONE_SEGMENTS)


def do_hierarchy(scene, arm_obj):
    """Hip parents B/C roots; each chain is parented and connected."""
    if arm_obj.data.bones[HIP_NAME].parent is not None:
        raise AssertionError("Hip must be a root bone")
    hip_bone = arm_obj.data.bones[HIP_NAME]
    for letter in CHAIN_NAMES:
        bones = _chain_bones(arm_obj, letter)
        root = arm_obj.data.bones[bones[0]]
        root_parent_name = getattr(root.parent, "name", None)
        if letter in ("B", "C") and root_parent_name != HIP_NAME:
            raise AssertionError(
                "root of Chain {0} must be parented to {1} (actual parent={2})".format(letter, HIP_NAME, root_parent_name)
            )
        if letter == "A" and root.parent is not None:
            raise AssertionError("root of Chain A must be unparented")
        for seg in range(1, BONES_PER_CHAIN):
            bone = arm_obj.data.bones[bones[seg]]
            if bone.parent != arm_obj.data.bones[bones[seg - 1]]:
                raise AssertionError("chain {0} broken at segment {1}".format(letter, seg))
            pose_bone = arm_obj.pose.bones[bones[seg]]
            if not pose_bone.bone.use_connect:
                raise AssertionError("{0} not connected".format(bones[seg]))
    return "Hip parents B/C, chains connected"


def do_curve_offset(scene, arm_obj):
    """Chain B carries a bend offset; Chain A is straight (risk: ease/roll)."""
    root_b = arm_obj.data.bones["{0}B.000".format(CHAIN_PREFIX)]
    bend = getattr(root_b, "bbone_curveinx", 0.0)
    if abs(bend) < 1e-6:
        raise AssertionError("Chain B bend offset missing")
    root_a = arm_obj.data.bones["{0}A.000".format(CHAIN_PREFIX)]
    if abs(getattr(root_a, "bbone_curveinx", 0.0)) > 1e-9:
        raise AssertionError("Chain A must stay straight")
    return "Chain B bend={0:.3f}".format(bend)


def do_roll_scale(scene, arm_obj):
    """Chain C must carry roll variance and non-uniform bbone scale."""
    for seg in range(BONES_PER_CHAIN):
        name = "{0}C.{1:03d}".format(CHAIN_PREFIX, seg)
        bone = arm_obj.data.bones[name]
        if abs(bone.bbone_scalein[0] - 0.80) > 1e-6 or abs(bone.bbone_scalein[2] - 1.25) > 1e-6:
            raise AssertionError("{0} bbone_scalein missing".format(name))
        if abs(bone.bbone_rollin) < 1e-9:
            raise AssertionError("{0} bbone_rollin missing".format(name))
    return "roll + scale variance on Chain C"


def do_meshes(scene, arm_obj):
    """Exactly the two planned meshes, with the naming trap on BodyHigh."""
    mesh_objs = [o for o in scene.collection.objects if o.type == "MESH"]
    expected = {obj_name for (obj_name, _, _) in PAIRS}
    if {o.name for o in mesh_objs} != expected:
        raise AssertionError("mesh objects {0} != {1}".format({o.name for o in mesh_objs}, expected))
    high = scene.collection.objects["BodyHigh"]
    if high.data.name == "BodyHigh":
        raise AssertionError("object name must differ from mesh data name")
    if high.parent is not arm_obj:
        raise AssertionError("BodyHigh must be parented to the armature")
    if high.modifiers.get("ArmRig") is None:
        raise AssertionError("BodyHigh armature modifier missing")
    return "2 meshes; BodyHigh uses data '{0}'".format(high.data.name)


def do_transforms(scene):
    """BodyHigh has a non-identical matrix_world; BodyLow identity."""
    import bpy

    bpy.context.view_layer.update()
    high = scene.collection.objects["BodyHigh"]
    low = scene.collection.objects["BodyLow"]
    identity_block = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    high_is = tuple(high.matrix_world[i][j] for i in range(4) for j in range(4))
    low_is = tuple(low.matrix_world[i][j] for i in range(4) for j in range(4))
    diffs = [abs(a - b) for a, b in zip(high_is, identity_block)]
    if max(diffs) <= 1e-9:
        raise AssertionError("BodyHigh matrix_world is supposedly non-identical")
    low_delta = max(abs(a - b) for a, b in zip(low_is, identity_block))
    if low_delta > 1e-9:
        raise AssertionError("BodyLow matrix_world must be identical (delta={0:.2e})".format(low_delta))
    return "BodyHigh transform delta={0:.3f}".format(max(diffs))


def do_weights(scene):
    """Vertex groups for Chain A exist on both meshes, all verts weighted."""
    for (obj_name, _, _) in PAIRS:
        obj = scene.collection.objects[obj_name]
        for seg in range(BONES_PER_CHAIN):
            group_name = "{0}A.{1:03d}".format(CHAIN_PREFIX, seg)
            if group_name not in obj.vertex_groups:
                raise AssertionError("{0}: missing group {1}".format(obj_name, group_name))
        group_index = obj.vertex_groups["{0}A.000".format(CHAIN_PREFIX)].index
        assigned = sum(
            1
            for vertex in obj.data.vertices
            if any(g.group == group_index for g in vertex.groups)
        )
        if assigned != len(obj.data.vertices):
            raise AssertionError("{0}: expected all vertices weighted, got {1}".format(obj_name, assigned))
    return "groups present on {0} meshes".format(len(PAIRS))


def do_animation(scene, arm_obj):
    """Frame range 1..30 and the posed state actually changes over time."""
    import bpy

    if (scene.frame_start, scene.frame_end) != (SCENE_FRAME_START, SCENE_FRAME_END):
        raise AssertionError("frame range wrong")

    def posed_marker():
        """Deformed-space probe: first vertex of the rigged BodyHigh."""
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = scene.collection.objects["BodyHigh"].evaluated_get(depsgraph)
        vertex = evaluated.data.vertices[0]
        return (vertex.co.x, vertex.co.y, vertex.co.z)

    scene.frame_set(SCENE_FRAME_START)
    first = posed_marker()
    scene.frame_set(SCENE_FRAME_END)
    last = posed_marker()
    scene.frame_set(SCENE_FRAME_START)
    move = max(abs(a - b) for a, b in zip(first, last))
    if move <= 1e-4:
        raise AssertionError("animation does not change the posed child (move={0:.6f})".format(move))
    return "posed child moves {0:.4f} along 30 frames".format(move)


def do_registration():
    """The package imports, registers and unregisters itself."""
    import importlib

    package_dir = os.path.dirname(ROOT)
    package_name = os.path.basename(ROOT)
    if package_dir not in sys.path:
        sys.path.insert(0, package_dir)
    mod = importlib.import_module(package_name)
    try:
        mod.register()
    finally:
        mod.unregister()
    return "package '{0}' register/unregister ok".format(package_name)


def do_manifest():
    """blender_manifest.toml: id, GPL v3+, Blender >= 4.2."""
    manifest = tomllib.load(open(os.path.join(ROOT, "blender_manifest.toml"), "rb"))
    if manifest.get("id") != "bbone_to_bones":
        raise AssertionError("manifest id wrong")
    if "SPDX:GPL-3.0-or-later" not in manifest.get("license", []):
        raise AssertionError("license must be SPDX:GPL-3.0-or-later")
    minimum = tuple(int(p) for p in manifest["blender_version_min"].split("."))
    if minimum < (4, 2, 0):
        raise AssertionError("blender_version_min below 4.2")
    if manifest.get("type") != "add-on":
        raise AssertionError("manifest type must be add-on")
    return "manifest v{0}".format(manifest.get("version"))


def do_license():
    """Full GPL-3 text ships in the repo."""
    path = os.path.join(ROOT, "LICENSE")
    text = open(path, encoding="utf-8").read()
    if "GNU GENERAL PUBLIC LICENSE" not in text or "Version 3" not in text:
        raise AssertionError("LICENSE must contain the full GPL-3 text")
    return "LICENSE GPL-3 present"


def _core():
    """Import the headless core package (addon root on sys.path, no UI)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import core

    return core


def _segment_count():
    """Segments produced by the fixture: 12 bendy bones x 8 segments."""
    return len(CHAIN_NAMES) * BONES_PER_CHAIN * BBONE_SEGMENTS


def do_fase1_space():
    """bbone_segment_matrix is bone-local; matrix_local lifts it to armature space."""
    core = _core()
    _scene, arm_obj, _ = build()
    tolerance = core.HEAD_MATCH_TOLERANCE
    for letter in ("B", "C"):
        source = "{0}{1}.000".format(CHAIN_PREFIX, letter)
        bone = arm_obj.data.bones[source]
        pose_bone = arm_obj.pose.bones[source]
        local = pose_bone.bbone_segment_matrix(0, rest=True).to_translation()
        armature_space = (bone.matrix_local @ pose_bone.bbone_segment_matrix(0, rest=True)).to_translation()
        delta = (armature_space - bone.head_local).length
        if delta > tolerance:
            raise AssertionError(
                "{0}: matrix_local @ bbone_segment_matrix(0) head delta {1:.3e} > {2:.1e}".format(
                    source, delta, tolerance
                )
            )
        if (local - bone.head_local).length <= tolerance:
            raise AssertionError(
                "{0}: the bone-local translation must NOT be in armature space".format(source)
            )
    return "matrix_local required for B.000/C.000 (tol={0:.1e})".format(tolerance)


def do_fase1_curve():
    """Every segment sits on the rest bbone curve with the bbone roll axis."""
    core = _core()
    _scene, arm_obj, _ = build()
    tolerance = core.HEAD_MATCH_TOLERANCE
    originals = {}
    for letter in CHAIN_NAMES:
        for seg in range(BONES_PER_CHAIN):
            source = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
            bone = arm_obj.data.bones[source]
            pose_bone = arm_obj.pose.bones[source]
            count = int(bone.bbone_segments)
            matrices = [
                (bone.matrix_local @ pose_bone.bbone_segment_matrix(index, rest=True)).copy()
                for index in range(count)
            ]
            originals[source] = {
                "count": count,
                "heads": [matrix.to_translation() for matrix in matrices],
                "z_axes": [matrix.col[2].to_3d().normalized() for matrix in matrices],
            }

    report = core.convert_bbones_to_segments(arm_obj)
    if report["mode_changes"] != 2:
        raise AssertionError(
            "expected 2 mode_set calls (OBJECT -> EDIT -> OBJECT), got {0}".format(report["mode_changes"])
        )
    if sorted(report["converted"]) != sorted(originals):
        raise AssertionError(
            "converted {0} bones, expected {1}".format(len(report["converted"]), len(originals))
        )

    bones = arm_obj.data.bones
    checked = 0
    for source, data in originals.items():
        for index in range(data["count"]):
            name = core.segment_bone_name(source, index)
            if name not in bones:
                raise AssertionError("segment bone {0} missing".format(name))
            segment = bones[name]
            head_delta = (segment.head_local - data["heads"][index]).length
            if head_delta > tolerance:
                raise AssertionError(
                    "{0}: head delta {1:.3e} > {2:.1e}".format(name, head_delta, tolerance)
                )
            chord = segment.tail_local - segment.head_local
            if chord.length <= 1e-9:
                raise AssertionError("{0}: zero-length segment".format(name))
            chord.normalize()
            z_axis = segment.matrix_local.col[2].to_3d().normalized()
            orthogonal = abs(z_axis.dot(chord))
            if orthogonal > 1e-4:
                raise AssertionError(
                    "{0}: Z axis not orthogonal to the chord (dot={1:.3e})".format(name, orthogonal)
                )
            bbone_z = data["z_axes"][index]
            expected_z = bbone_z - chord * bbone_z.dot(chord)
            if expected_z.length <= 1e-9:
                raise AssertionError("{0}: degenerate bbone Z axis".format(name))
            expected_z.normalize()
            z_delta = (z_axis - expected_z).length
            if z_delta > 1e-4:
                raise AssertionError(
                    "{0}: Z axis differs from the bbone roll axis (delta={1:.3e})".format(name, z_delta)
                )
            checked += 1
    if checked != _segment_count():
        raise AssertionError("checked {0} segments, expected {1}".format(checked, _segment_count()))
    return "{0} segments on the rest curve, mode_changes=2".format(checked)


def _add_tip_child(arm_obj, parent_name, child_name="TipChild"):
    """Add a plain (non-bbone) child bone to the fixture before the conversion."""
    import bpy

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit_bones = arm_obj.data.edit_bones
        parent = edit_bones[parent_name]
        child = edit_bones.new(child_name)
        child.head = parent.tail.copy()
        child.tail = parent.tail + (parent.tail - parent.head).normalized() * 0.05
        child.parent = parent
        child.use_connect = False
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        if previous_active is not None and previous_active != arm_obj:
            view_layer.objects.active = previous_active


def do_fase1_deform():
    """Converted rig: segments deform, sources do not, parenting is chained."""
    core = _core()
    _scene, arm_obj, _ = build()
    tip_parent = "{0}B.003".format(CHAIN_PREFIX)
    _add_tip_child(arm_obj, tip_parent)
    report = core.convert_bbones_to_segments(arm_obj)
    bones = arm_obj.data.bones

    expected_bones = 2 + len(CHAIN_NAMES) * BONES_PER_CHAIN * (1 + BBONE_SEGMENTS)
    if len(bones) != expected_bones:
        raise AssertionError("bone count {0} != {1}".format(len(bones), expected_bones))
    hip = bones[HIP_NAME]
    if not hip.use_deform:
        raise AssertionError("Hip must keep use_deform=True")
    if "_seg_" in hip.name:
        raise AssertionError("Hip must not be renamed")

    last_index = BBONE_SEGMENTS - 1
    checked = 0
    for letter in CHAIN_NAMES:
        for seg in range(BONES_PER_CHAIN):
            source = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
            if bones[source].use_deform:
                raise AssertionError("{0} must keep use_deform=False".format(source))
            if seg == 0:
                expected_parent = None if letter == "A" else HIP_NAME
            else:
                previous_source = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg - 1)
                expected_parent = core.segment_bone_name(previous_source, last_index)
            for index in range(BBONE_SEGMENTS):
                name = core.segment_bone_name(source, index)
                if name not in bones:
                    raise AssertionError("segment bone {0} missing".format(name))
                segment = bones[name]
                if not segment.use_deform:
                    raise AssertionError("{0} must have use_deform=True".format(name))
                if segment.use_connect:
                    raise AssertionError("{0} must not be connected".format(name))
                expected = (
                    expected_parent if index == 0 else core.segment_bone_name(source, index - 1)
                )
                parent_name = getattr(segment.parent, "name", None)
                if parent_name != expected:
                    raise AssertionError(
                        "{0}: parent {1} != {2}".format(name, parent_name, expected)
                    )
                checked += 1
    if checked != _segment_count():
        raise AssertionError("checked {0} segments, expected {1}".format(checked, _segment_count()))

    expected_tip_parent = core.segment_bone_name(tip_parent, last_index)
    tip_parent_name = getattr(bones["TipChild"].parent, "name", None)
    if tip_parent_name != expected_tip_parent:
        raise AssertionError(
            "TipChild: parent {0} != {1}".format(tip_parent_name, expected_tip_parent)
        )
    if report["reparented_children"].get("TipChild") != expected_tip_parent:
        raise AssertionError("TipChild not reported as reparented")

    # Partial conversion: a non-converted child lands on the last segment too.
    _scene, arm_obj, _ = build()
    partial = core.convert_bbones_to_segments(arm_obj, bone_names=["{0}A.000".format(CHAIN_PREFIX)])
    partial_bones = arm_obj.data.bones
    expected_child_parent = core.segment_bone_name("{0}A.000".format(CHAIN_PREFIX), last_index)
    child_parent = getattr(partial_bones["{0}A.001".format(CHAIN_PREFIX)].parent, "name", None)
    if child_parent != expected_child_parent:
        raise AssertionError(
            "partial: BendyA.001 parent {0} != {1}".format(child_parent, expected_child_parent)
        )
    if partial["reparented_children"].get("{0}A.001".format(CHAIN_PREFIX)) != expected_child_parent:
        raise AssertionError("partial: BendyA.001 not reported as reparented")

    return "{0} segments deform, 12 sources off, Hip on, TipChild on last segment".format(checked)


def do_fase2_space_index():
    """bbone_segment_index maps the rest head to segment 0 and the tail to the last one."""
    core = _core()
    _scene, arm_obj, meshes = build()
    tolerance = 1e-5
    checked = 0
    for letter in CHAIN_NAMES:
        for seg in range(BONES_PER_CHAIN):
            name = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
            bone = arm_obj.data.bones[name]
            pose_bone = arm_obj.pose.bones[name]
            head_index, head_blend = pose_bone.bbone_segment_index(bone.head_local)
            if head_index != 0 or abs(head_blend) > tolerance:
                raise AssertionError(
                    "{0}: head index/blend {1}/{2:.3e} != 0/0".format(name, head_index, head_blend)
                )
            tail_index, tail_blend = pose_bone.bbone_segment_index(bone.tail_local)
            if tail_index != BBONE_SEGMENTS - 1 or abs(tail_blend - 1.0) > tolerance:
                raise AssertionError(
                    "{0}: tail index/blend {1}/{2:.3e} != {3}/1".format(
                        name, tail_index, tail_blend, BBONE_SEGMENTS - 1
                    )
                )
            checked += 1

    expected = [
        arm_obj.matrix_world.inverted_safe() @ meshes[0].matrix_world @ vertex.co
        for vertex in meshes[0].data.vertices
    ]
    coords = core.vertex_coords_in_armature_space(meshes[0], arm_obj)
    if len(coords) != len(expected):
        raise AssertionError("coords {0} != vertices {1}".format(len(coords), len(expected)))
    for index, (got, want) in enumerate(zip(coords, expected)):
        delta = (got - want).length
        if delta > 1e-6:
            raise AssertionError(
                "vertex {0}: armature-space delta {1:.3e} > 1.0e-06".format(index, delta)
            )
    return "{0} bbone bones map head->0 and tail->{1}, coords match".format(checked, BBONE_SEGMENTS - 1)


def do_fase2_weight_accumulation():
    """Transfer normalizes deform weights, keeps non-deform groups and clears sources."""
    core = _core()
    _scene, arm_obj, meshes = build()
    body = meshes[0]
    vertices = list(range(len(body.data.vertices)))

    pin = body.vertex_groups.get("ClothPin")
    if pin is None:
        pin = body.vertex_groups.new(name="ClothPin")
    pin.add(vertices, 0.35, "REPLACE")
    hip = body.vertex_groups.get(HIP_NAME)
    if hip is None:
        hip = body.vertex_groups.new(name=HIP_NAME)
    hip.add(vertices, 0.25, "REPLACE")
    source_name = "{0}A.000".format(CHAIN_PREFIX)
    source = body.vertex_groups.get(source_name)
    if source is None:
        raise AssertionError("{0} group missing on BodyHigh".format(source_name))
    source.add(vertices, 0.50, "REPLACE")

    core.convert_bbones_to_segments(arm_obj)
    core.transfer_bbone_weights(arm_obj)

    bones = arm_obj.data.bones
    names_by_index = {group.index: group.name for group in body.vertex_groups}
    source_index = body.vertex_groups[source_name].index
    for vertex in body.data.vertices:
        deform_total = 0.0
        pin_weight = 0.0
        for element in vertex.groups:
            name = names_by_index[element.group]
            if name == "ClothPin":
                pin_weight = float(element.weight)
                continue
            bone = bones.get(name)
            if bone is not None and bone.use_deform:
                deform_total += float(element.weight)
        if abs(deform_total - 1.0) > 1e-6:
            raise AssertionError(
                "vertex {0}: deform total {1:.6f} != 1.0".format(vertex.index, deform_total)
            )
        if abs(pin_weight - 0.35) > 1e-6:
            raise AssertionError(
                "vertex {0}: ClothPin weight {1:.6f} != 0.35".format(vertex.index, pin_weight)
            )
        if any(element.group == source_index for element in vertex.groups):
            raise AssertionError("vertex {0} still assigned to {1}".format(vertex.index, source_name))
    return "{0} vertices normalized, ClothPin untouched, source cleared".format(len(vertices))


def _distribute_chains(arm_obj, mesh_obj):
    """Move the mesh vertices onto the three chain axes and weight them on the roots."""
    from mathutils import Vector

    names = ["{0}{1}.000".format(CHAIN_PREFIX, letter) for letter in CHAIN_NAMES]
    groups = {}
    for name in names:
        group = mesh_obj.vertex_groups.get(name)
        groups[name] = group if group is not None else mesh_obj.vertex_groups.new(name=name)
    to_local = mesh_obj.matrix_world.inverted_safe() @ arm_obj.matrix_world
    total = len(mesh_obj.data.vertices)
    per_chain = [0] * len(names)
    for index in range(total):
        chain = min(index * len(names) // total, len(names) - 1)
        owner = names[chain]
        for name, group in groups.items():
            group.remove([index])
        groups[owner].add([index], 1.0, "REPLACE")
        root = arm_obj.data.bones[owner]
        bottom = root.head_local.z
        top = root.tail_local.z
        count = total // len(names) + (1 if chain < total % len(names) else 0)
        t = per_chain[chain] / float(count - 1) if count > 1 else 0.0
        per_chain[chain] += 1
        point = Vector((root.head_local.x, 0.0, bottom + (top - bottom) * t))
        mesh_obj.data.vertices[index].co = to_local @ point
    mesh_obj.data.update()


def _evaluated_vertices(mesh_obj):
    """Vertex positions of the mesh with modifiers applied, in object space."""
    import bpy

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh_obj.evaluated_get(depsgraph)
    return [vertex.co.copy() for vertex in evaluated.data.vertices]


def do_fase2_pose_equivalence():
    """Segment bones reproduce the posed bbone deformation within POSE_MATCH_MAX_ERROR."""
    import bpy

    core = _core()
    scene, arm_obj, meshes = build()
    high, low = meshes[0], meshes[1]
    _distribute_chains(arm_obj, high)
    _distribute_chains(arm_obj, low)

    scene.frame_set(SCENE_FRAME_END)
    before = (_evaluated_vertices(high), _evaluated_vertices(low))

    scene.frame_set(SCENE_FRAME_START)
    core.convert_bbones_to_segments(arm_obj)
    core.transfer_bbone_weights(arm_obj)

    scene.frame_set(SCENE_FRAME_END)
    core.pose_segments_from_bbones(arm_obj)
    bpy.context.view_layer.update()
    after = (_evaluated_vertices(high), _evaluated_vertices(low))

    max_error = 0.0
    worst = ""
    for before_coords, after_coords, mesh_obj in zip(before, after, (high, low)):
        if len(before_coords) != len(after_coords):
            raise AssertionError(
                "{0}: {1} -> {2} vertices".format(
                    mesh_obj.name, len(before_coords), len(after_coords)
                )
            )
        for index, (start, end) in enumerate(zip(before_coords, after_coords)):
            error = (start - end).length
            if error > max_error:
                max_error = error
                worst = "{0}[{1}]".format(mesh_obj.name, index)
    if max_error >= core.POSE_MATCH_MAX_ERROR:
        raise AssertionError(
            "max error {0:.3e} m at {1} >= {2:.1e}".format(
                max_error, worst, core.POSE_MATCH_MAX_ERROR
            )
        )
    return "max error {0:.2e} m over {1} meshes".format(max_error, len(before))


def _segment_bones(arm_obj, core):
    """Yield ``(source, index, segment_name)`` for every fixture segment bone."""
    for letter in CHAIN_NAMES:
        for seg in range(BONES_PER_CHAIN):
            source = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
            for index in range(BBONE_SEGMENTS):
                yield source, index, core.segment_bone_name(source, index)


def do_fase3_constraints():
    """Every converted segment follows its bbone segment through one constraint."""
    core = _core()
    _scene, arm_obj, _ = build()
    core.convert_bbones_to_segments(arm_obj)

    report = core.add_bbone_follow_constraints(arm_obj)
    if report["missing"]:
        raise AssertionError("missing segments: {0}".format(report["missing"]))
    if len(report["constrained"]) != _segment_count():
        raise AssertionError(
            "constrained {0} segments, expected {1}".format(
                len(report["constrained"]), _segment_count()
            )
        )

    checked = 0
    for source, index, name in _segment_bones(arm_obj, core):
        pose_bone = arm_obj.pose.bones[name]
        constraint = pose_bone.constraints.get(core.CONSTRAINT_NAME)
        if constraint is None:
            raise AssertionError("{0}: constraint '{1}' missing".format(name, core.CONSTRAINT_NAME))
        if constraint.type != "COPY_TRANSFORMS":
            raise AssertionError("{0}: type {1} != COPY_TRANSFORMS".format(name, constraint.type))
        if constraint.target != arm_obj:
            raise AssertionError(
                "{0}: target {1} != {2}".format(
                    name, getattr(constraint.target, "name", None), arm_obj.name
                )
            )
        if constraint.subtarget != source:
            raise AssertionError(
                "{0}: subtarget {1} != {2}".format(name, constraint.subtarget, source)
            )
        if constraint.use_bbone_shape is not True:
            raise AssertionError("{0}: use_bbone_shape is not True".format(name))
        expected = float(index) / float(BBONE_SEGMENTS)
        if abs(constraint.head_tail - expected) > 1e-6:
            raise AssertionError(
                "{0}: head_tail {1:.6f} != {2:.6f}".format(name, constraint.head_tail, expected)
            )
        checked += 1
    if checked != _segment_count():
        raise AssertionError("checked {0} segments, expected {1}".format(checked, _segment_count()))

    removed = core.remove_bbone_follow_constraints(arm_obj)
    if removed != _segment_count():
        raise AssertionError("removed {0} constraints, expected {1}".format(removed, _segment_count()))
    for _source, _index, name in _segment_bones(arm_obj, core):
        pose_bone = arm_obj.pose.bones[name]
        if pose_bone.constraints.get(core.CONSTRAINT_NAME) is not None:
            raise AssertionError("{0}: constraint left after removal".format(name))
        if len(pose_bone.constraints) != 0:
            raise AssertionError(
                "{0}: {1} constraints left".format(name, len(pose_bone.constraints))
            )
    return "{0} constraints added and removed".format(checked)


def do_fase3_bake_30_frames():
    """The baked animation reproduces the posed bbones on all 30 frames."""
    import bpy

    core = _core()
    scene, arm_obj, meshes = build()
    high, low = meshes[0], meshes[1]
    _distribute_chains(arm_obj, high)
    _distribute_chains(arm_obj, low)

    frames = list(range(SCENE_FRAME_START, SCENE_FRAME_END + 1))
    before = {}
    for frame in frames:
        scene.frame_set(frame)
        before[frame] = (_evaluated_vertices(high), _evaluated_vertices(low))
    scene.frame_set(SCENE_FRAME_START)

    core.convert_bbones_to_segments(arm_obj)
    core.transfer_bbone_weights(arm_obj)
    report = core.bake_segments_animation(
        arm_obj,
        frame_start=SCENE_FRAME_START,
        frame_end=SCENE_FRAME_END,
        remove_constraints=True,
    )
    expected_range = (SCENE_FRAME_START, SCENE_FRAME_END, 1)
    if (report["frame_start"], report["frame_end"], report["step"]) != expected_range:
        raise AssertionError("bake report range wrong: {0}".format(report))
    if len(report["baked"]) != _segment_count():
        raise AssertionError(
            "baked {0} bones, expected {1}".format(len(report["baked"]), _segment_count())
        )

    for _source, _index, name in _segment_bones(arm_obj, core):
        pose_bone = arm_obj.pose.bones[name]
        if len(pose_bone.constraints) != 0:
            raise AssertionError(
                "{0}: {1} constraints left after bake".format(name, len(pose_bone.constraints))
            )

    max_error = 0.0
    worst = ""
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        after = (_evaluated_vertices(high), _evaluated_vertices(low))
        for mesh_index, mesh_obj in enumerate((high, low)):
            before_coords = before[frame][mesh_index]
            after_coords = after[mesh_index]
            if len(before_coords) != len(after_coords):
                raise AssertionError(
                    "{0} frame {1}: {2} -> {3} vertices".format(
                        mesh_obj.name, frame, len(before_coords), len(after_coords)
                    )
                )
            for vertex_index, (start, end) in enumerate(zip(before_coords, after_coords)):
                error = (start - end).length
                if error > max_error:
                    max_error = error
                    worst = "{0}[{1}] frame {2}".format(mesh_obj.name, vertex_index, frame)
    if max_error >= core.POSE_MATCH_MAX_ERROR:
        raise AssertionError(
            "max error {0:.3e} m at {1} >= {2:.1e}".format(
                max_error, worst, core.POSE_MATCH_MAX_ERROR
            )
        )
    return "max error {0:.2e} m over {1} frames x 2 meshes".format(max_error, len(frames))


def do_fase4_influence_limit():
    """The influence cap keeps the strongest deform groups and spares ClothPin."""
    core = _core()
    _scene, arm_obj, meshes = build()
    body = meshes[0]
    core.convert_bbones_to_segments(arm_obj)

    vertices = list(range(len(body.data.vertices)))
    source = "{0}A.000".format(CHAIN_PREFIX)
    weights = (0.30, 0.25, 0.20, 0.15, 0.06, 0.04)
    deform_names = []
    for index, weight in enumerate(weights):
        name = core.segment_bone_name(source, index)
        deform_names.append(name)
        group = body.vertex_groups.get(name)
        if group is None:
            group = body.vertex_groups.new(name=name)
        group.add(vertices, weight, "REPLACE")
    pin = body.vertex_groups.get("ClothPin")
    if pin is None:
        pin = body.vertex_groups.new(name="ClothPin")
    pin.add(vertices, 0.35, "REPLACE")

    report = core.limit_vertex_influences(arm_obj, max_influences=4)
    if report["max_influences"] != 4:
        raise AssertionError("report max_influences {0} != 4".format(report["max_influences"]))
    if report["capped_vertices"] != len(vertices):
        raise AssertionError(
            "capped_vertices {0} != {1}".format(report["capped_vertices"], len(vertices))
        )

    kept_names = set(deform_names[:4])
    dropped_names = set(deform_names[4:])
    bones = arm_obj.data.bones
    names_by_index = {group.index: group.name for group in body.vertex_groups}
    for vertex in body.data.vertices:
        deform = {}
        pin_weight = None
        for element in vertex.groups:
            name = names_by_index[element.group]
            weight = float(element.weight)
            if name == "ClothPin":
                pin_weight = weight
                continue
            bone = bones.get(name)
            if bone is not None and bone.use_deform and weight > 0.0:
                deform[name] = weight
        if set(deform) != kept_names:
            raise AssertionError(
                "vertex {0}: deform groups {1} != {2}".format(
                    vertex.index, sorted(deform), sorted(kept_names)
                )
            )
        if any(name in deform for name in dropped_names):
            raise AssertionError("vertex {0}: capped group still assigned".format(vertex.index))
        total = sum(deform.values())
        if abs(total - 1.0) > 1e-6:
            raise AssertionError(
                "vertex {0}: deform total {1:.6f} != 1.0".format(vertex.index, total)
            )
        if pin_weight is None or abs(pin_weight - 0.35) > 1e-6:
            raise AssertionError(
                "vertex {0}: ClothPin weight {1} != 0.35".format(vertex.index, pin_weight)
            )
        # The kept weights keep their relative order after normalisation.
        order = [deform[name] for name in deform_names[:4]]
        if any(order[index] < order[index + 1] - 1e-9 for index in range(3)):
            raise AssertionError("vertex {0}: kept weights out of order".format(vertex.index))

    return "{0} vertices capped to 4 deform groups, ClothPin untouched".format(len(vertices))


def do_fase4_export_reimport():
    """The three presets export the converted rig and reimport bones and meshes."""
    import tempfile

    import bpy

    core = _core()
    _scene, arm_obj, meshes = build()
    core.convert_bbones_to_segments(arm_obj)
    core.transfer_bbone_weights(arm_obj)
    core.bake_segments_animation(
        arm_obj,
        frame_start=SCENE_FRAME_START,
        frame_end=SCENE_FRAME_END,
        remove_constraints=True,
    )

    sources = [
        "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
        for letter in CHAIN_NAMES
        for seg in range(BONES_PER_CHAIN)
    ]
    segments = [
        core.segment_bone_name(source, index)
        for source in sources
        for index in range(BBONE_SEGMENTS)
    ]
    mesh_names = {mesh_obj.name for mesh_obj in meshes}
    vertex_count = len(meshes[0].data.vertices)

    presets = (
        ("UNITY", "unity.fbx"),
        ("UNREAL", "unreal.fbx"),
        ("GODOT", "godot.glb"),
    )
    checked = 0
    with tempfile.TemporaryDirectory() as tmp_dir:
        for preset, filename in presets:
            path = os.path.join(tmp_dir, filename)
            report = core.export_rig(arm_obj, path, preset=preset)
            if report["preset"] != preset:
                raise AssertionError("{0}: report preset {1}".format(preset, report["preset"]))
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise AssertionError("{0}: export produced no file at {1}".format(preset, path))

            before = {obj.name for obj in _scene.objects}
            if filename.lower().endswith(".glb"):
                bpy.ops.import_scene.gltf(filepath=path)
            else:
                bpy.ops.import_scene.fbx(filepath=path)
            imported = [obj for obj in _scene.objects if obj.name not in before]

            armatures = [obj for obj in imported if obj.type == "ARMATURE"]
            if len(armatures) != 1:
                raise AssertionError(
                    "{0}: imported {1} armatures, expected 1".format(preset, len(armatures))
                )
            imported_arm = armatures[0]
            bones = imported_arm.data.bones

            for name in segments:
                if name not in bones:
                    raise AssertionError("{0}: segment bone {1} missing".format(preset, name))
            if HIP_NAME not in bones:
                raise AssertionError("{0}: {1} missing".format(preset, HIP_NAME))
            for source in sources:
                if source in bones:
                    raise AssertionError("{0}: source bbone {1} exported".format(preset, source))
            for bone in bones:
                if bone.name.endswith("_end"):
                    raise AssertionError("{0}: leaf bone {1} exported".format(preset, bone.name))

            for letter in CHAIN_NAMES:
                for seg in range(BONES_PER_CHAIN):
                    source = "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
                    chain = [
                        core.segment_bone_name(source, index)
                        for index in range(BBONE_SEGMENTS)
                    ]
                    for index in range(1, BBONE_SEGMENTS):
                        parent_name = getattr(bones[chain[index]].parent, "name", None)
                        if parent_name != chain[index - 1]:
                            raise AssertionError(
                                "{0}: {1} parent {2} != {3}".format(
                                    preset, chain[index], parent_name, chain[index - 1]
                                )
                            )
                    if seg == 0:
                        # Chain A root is a root bone; B and C hang from Hip.
                        expected_root_parent = None if letter == "A" else HIP_NAME
                    else:
                        expected_root_parent = core.segment_bone_name(
                            "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg - 1),
                            BBONE_SEGMENTS - 1,
                        )
                    root_parent = getattr(bones[chain[0]].parent, "name", None)
                    if root_parent != expected_root_parent:
                        raise AssertionError(
                            "{0}: {1} parent {2} != {3}".format(
                                preset, chain[0], root_parent, expected_root_parent
                            )
                        )

            custom_shapes = {
                pose_bone.custom_shape
                for pose_bone in imported_arm.pose.bones
                if pose_bone.custom_shape is not None
            }
            imported_meshes = {
                obj.name.split(".")[0]: obj
                for obj in imported
                if obj.type == "MESH" and obj not in custom_shapes
            }
            if set(imported_meshes) != mesh_names:
                raise AssertionError(
                    "{0}: meshes {1} != {2}".format(
                        preset, sorted(imported_meshes), sorted(mesh_names)
                    )
                )
            for name, mesh_obj in imported_meshes.items():
                count = len(mesh_obj.data.vertices)
                if count != vertex_count:
                    raise AssertionError(
                        "{0}: {1} has {2} vertices != {3}".format(preset, name, count, vertex_count)
                    )
            checked += 1

    return "{0} presets reimported: {1} segments, Hip, 2 meshes".format(checked, len(segments))


def do_fase5_ui_operators():
    """The UI operators register twice, refuse a mesh and run the whole chain."""
    import importlib
    import tempfile

    import bpy

    package_dir = os.path.dirname(ROOT)
    if package_dir not in sys.path:
        sys.path.insert(0, package_dir)
    mod = importlib.import_module(os.path.basename(ROOT))

    _scene, arm_obj, meshes = build()
    try:
        mod.register()
        mod.register()  # double register must stay idempotent
        settings = getattr(bpy.context.scene, "bbone_to_bones_settings", None)
        if settings is None:
            raise AssertionError("double register lost bbone_to_bones_settings")
        if mod.CLASSES[0].__name__ != "BBoneToBonesSettings":
            raise AssertionError(
                "CLASSES[0] is {0} != BBoneToBonesSettings".format(mod.CLASSES[0].__name__)
            )

        operator_count = 0
        for cls in mod.CLASSES:
            if not issubclass(cls, bpy.types.Operator):
                continue
            operator_count += 1
            options = set(getattr(cls, "bl_options", set()))
            if not {"REGISTER", "UNDO"}.issubset(options):
                raise AssertionError(
                    "{0} bl_options {1} lacks REGISTER/UNDO".format(cls.__name__, sorted(options))
                )
        if operator_count == 0:
            raise AssertionError("no operator found in CLASSES")

        def _run(name, call):
            result = call()
            if result != {"FINISHED"}:
                raise AssertionError("btob.{0} returned {1}".format(name, sorted(result)))

        bpy.context.view_layer.objects.active = meshes[0]
        try:
            refused = bpy.ops.btob.convert_segments()
        except RuntimeError as exc:
            if "Select an Armature object first" not in str(exc):
                raise AssertionError("unexpected error message: {0}".format(exc)) from exc
        else:
            if refused != {"CANCELLED"}:
                raise AssertionError(
                    "btob.convert_segments on a mesh returned {0}".format(sorted(refused))
                )

        bpy.context.view_layer.objects.active = arm_obj
        _run("convert_segments", lambda: bpy.ops.btob.convert_segments())
        _run("transfer_weights", lambda: bpy.ops.btob.transfer_weights())
        _run("add_constraints", lambda: bpy.ops.btob.add_constraints())
        _run("remove_constraints", lambda: bpy.ops.btob.remove_constraints())
        _run("bake_animation", lambda: bpy.ops.btob.bake_animation())
        _run("limit_influences", lambda: bpy.ops.btob.limit_influences())

        with tempfile.TemporaryDirectory() as tmp_dir:
            export_path = os.path.join(tmp_dir, "ui_export.fbx")
            _run("export_rig", lambda: bpy.ops.btob.export_rig(filepath=export_path))
            if not os.path.isfile(export_path) or os.path.getsize(export_path) == 0:
                raise AssertionError("export_rig wrote no file at {0}".format(export_path))
            size = os.path.getsize(export_path)

            # The preset update rewrites the extension of the export path.
            settings.export_path = export_path
            settings.export_preset = "GODOT"
            if not settings.export_path.endswith(".glb"):
                raise AssertionError(
                    "GODOT preset left export_path as {0}".format(settings.export_path)
                )
            settings.export_preset = "UNITY"
            if not settings.export_path.endswith(".fbx"):
                raise AssertionError(
                    "UNITY preset left export_path as {0}".format(settings.export_path)
                )

        bpy.context.view_layer.objects.active = arm_obj
        _run("revert_to_bbones", lambda: bpy.ops.btob.revert_to_bbones())
        leftover = [bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name]
        if leftover:
            raise AssertionError("revert_to_bbones left segments {0}".format(leftover))
        sources = [
            "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
            for letter in CHAIN_NAMES
            for seg in range(BONES_PER_CHAIN)
        ]
        for source_name in sources:
            bone = arm_obj.data.bones.get(source_name)
            if bone is None:
                raise AssertionError("source bone {0} missing after revert".format(source_name))
            if not bone.use_deform:
                raise AssertionError("source bone {0} kept use_deform False".format(source_name))
        body = meshes[0]
        if len(body.data.vertices) != 20:
            raise AssertionError(
                "BodyHigh has {0} vertices != 20".format(len(body.data.vertices))
            )
        root_group = body.vertex_groups.get("{0}A.000".format(CHAIN_PREFIX))
        if root_group is None:
            raise AssertionError("BendyA.000 group missing after revert")
        for vertex in body.data.vertices:
            weight = 0.0
            for element in vertex.groups:
                if element.group == root_group.index:
                    weight = element.weight
            if abs(weight - 1.0) > 1e-5:
                raise AssertionError(
                    "vertex {0} weight on BendyA.000 is {1} != 1.0".format(
                        vertex.index, weight
                    )
                )
    finally:
        mod.unregister()

    return "{0} operators, double register, mesh refused, 8 calls FINISHED, export {1} bytes".format(
        operator_count, size
    )


# --- runner -----------------------------------------------------------------


def main():
    import bpy

    argv = sys.argv
    extras = argv[argv.index("--") + 1:] if "--" in argv else []
    scene, arm_obj, _ = build()
    if "save-fixture" in extras:
        import bpy.ops  # noqa: F401

        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "fixture.blend"))

    check("catene_bbone", lambda: do_chains(scene, arm_obj))
    check("gerarchia", lambda: do_hierarchy(scene, arm_obj))
    check("curva_bend", lambda: do_curve_offset(scene, arm_obj))
    check("roll_scale", lambda: do_roll_scale(scene, arm_obj))
    check("meshes", lambda: do_meshes(scene, arm_obj))
    check("transformations", lambda: do_transforms(scene))
    check("weights", lambda: do_weights(scene))
    check("animation", lambda: do_animation(scene, arm_obj))
    check("registration", do_registration)
    check("manifest", do_manifest)
    check("license", do_license)
    check("fase1_spazio_bbone", do_fase1_space)
    check("fase1_teste_curva", do_fase1_curve)
    check("fase1_gerarchia_deform", do_fase1_deform)
    check("fase2_spazio_indice", do_fase2_space_index)
    check("fase2_accumulo_normalizzazione", do_fase2_weight_accumulation)
    check("fase2_posa_equivalenza", do_fase2_pose_equivalence)
    check("fase3_constraints", do_fase3_constraints)
    check("fase3_bake_30_frames", do_fase3_bake_30_frames)
    check("fase4_limite_influenze", do_fase4_influence_limit)
    check("fase4_export_reimport", do_fase4_export_reimport)
    check("fase5_ui_operators", do_fase5_ui_operators)

    print("BTOB addon={0} blender={1}".format(os.path.basename(ROOT), bpy.app.version_string))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


sys.exit(main())
