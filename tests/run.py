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


def do_scaling():
    """Placeholder for the Fase 2 numeric contract (fixture-side contract only)."""
    return "deferred to Fase 2 (fixture transform available)"


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
    check("scaling", do_scaling)
    check("registration", do_registration)
    check("manifest", do_manifest)
    check("license", do_license)

    print("BTOB addon={0} blender={1}".format(os.path.basename(ROOT), bpy.app.version_string))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


sys.exit(main())
