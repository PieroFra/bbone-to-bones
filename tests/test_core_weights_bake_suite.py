# -*- coding: utf-8 -*-
"""Headless test suite for the core weights (Fase 2) and bake (Fase 3) modules.

Companion of ``tests/run.py``: it rebuilds the same in-memory fixture
(``make_fixture.build``) and covers every public function of
``core/weights.py`` (``find_rigged_meshes``, ``vertex_coords_in_armature_space``,
``split_bbone_weight``, ``transfer_bbone_weights``, ``pose_segments_from_bbones``)
and of ``core/bake.py`` (``select_only_segment_bones``,
``add_bbone_follow_constraints``, ``remove_bbone_follow_constraints``,
``collect_armature_actions``, ``assign_armature_action``,
``bake_segments_animation``, ``CONSTRAINT_NAME``). It never imports
``tests/run.py`` (that module executes its own runner on import) and never
touches the add-on UI code.

Usage:
    blender -b --python tests/test_core_weights_bake_suite.py

The verdict is the LAST line of stdout:
    RISULTATO passati=X falliti=Y totale=N
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RESULTS = []

sys.path.insert(0, HERE)
from make_fixture import (  # noqa: E402
    BBONE_SEGMENTS,
    BONES_PER_CHAIN,
    CHAIN_NAMES,
    CHAIN_PREFIX,
    build,
)


def check(name, fn):
    """Record a check result without aborting the rest."""
    try:
        detail = fn()
        RESULTS.append((name, True, detail or ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, "{0}: {1}".format(type(exc).__name__, exc)))


def _addon_module():
    """Load the add-on package from ROOT (never a stale copy in AppData)."""
    import importlib

    package_dir = os.path.dirname(ROOT)
    pkg_name = os.path.basename(ROOT)
    if sys.path[:1] != [package_dir]:
        if package_dir in sys.path:
            sys.path.remove(package_dir)
        sys.path.insert(0, package_dir)
    existing = sys.modules.get(pkg_name)
    if existing is not None:
        mod_file = os.path.abspath(getattr(existing, "__file__", "") or "")
        if not mod_file.startswith(os.path.abspath(ROOT)):
            for key in [k for k in list(sys.modules) if k == pkg_name or k.startswith(pkg_name + ".")]:
                del sys.modules[key]
    return importlib.import_module(pkg_name)


def _core():
    """Import the headless core package from ROOT."""
    _addon_module()
    import importlib

    return importlib.import_module("{0}.core".format(os.path.basename(ROOT)))


def _source_names():
    """The 12 bendy source bones of the fixture."""
    return [
        "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
        for letter in CHAIN_NAMES
        for seg in range(BONES_PER_CHAIN)
    ]


def _segment_count():
    """Segments produced by the fixture: 12 bendy bones x 8 segments."""
    return len(CHAIN_NAMES) * BONES_PER_CHAIN * BBONE_SEGMENTS


def _segment_names(arm_obj):
    """Return the name of every ``*_seg_XX`` bone of ``arm_obj``."""
    return sorted(bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name)


def _action_fcurves(action):
    """Return the F-Curves of ``action`` with the legacy/slotted fallback."""
    if action is None:
        return []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None and len(legacy) > 0:
        return list(legacy)
    collected = []
    for layer in getattr(action, "layers", None) or ():
        for strip in getattr(layer, "strips", ()):
            for bag in getattr(strip, "channelbags", ()):
                collected.extend(getattr(bag, "fcurves", ()))
    return collected


def _fcurve_bone_name(data_path):
    """Return the pose bone name of a ``pose.bones["name"]...`` path, else None."""
    prefix = 'pose.bones["'
    if not data_path.startswith(prefix):
        return None
    end = data_path.find('"]', len(prefix))
    if end < 0:
        return None
    return data_path[len(prefix):end]


def test_find_rigged_meshes():
    """The fixture armature pulls exactly the two meshes; a bare armature finds none."""
    import bpy

    core = _core()
    scene, arm_obj, meshes = build()
    found = core.find_rigged_meshes(arm_obj)
    if len(found) != 2:
        raise AssertionError("found {0} rigged meshes, expected 2".format(len(found)))
    names = sorted(obj.name for obj in found)
    if names != ["BodyHigh", "BodyLow"]:
        raise AssertionError("rigged meshes {0} != BodyHigh/BodyLow".format(names))

    empty_data = bpy.data.armatures.new("EmptyArmData")
    empty_obj = bpy.data.objects.new("EmptyRig", empty_data)
    scene.collection.objects.link(empty_obj)
    if core.find_rigged_meshes(empty_obj):
        raise AssertionError("bare armature must find 0 rigged meshes")
    return "find_rigged_meshes: 2 fixture meshes, 0 on a bare armature"


def test_vertex_coords_in_armature_space():
    """Coordinates are in armature space: world transform round-trips to the mesh."""
    core = _core()
    _scene, arm_obj, meshes = build()
    high = meshes[0]
    coords = core.vertex_coords_in_armature_space(high, arm_obj)
    if not coords or len(coords) != len(high.data.vertices):
        raise AssertionError("expected 1 coord per vertex")
    for vertex, coord in zip(high.data.vertices, coords):
        world = arm_obj.matrix_world @ coord
        expected = high.matrix_world @ vertex.co
        if (world - expected).length > 1e-5:
            raise AssertionError("vertex {0} not in armature space".format(vertex.index))
    return "vertex_coords_in_armature_space: {0} verts round-trip".format(len(coords))


def test_split_bbone_weight():
    """Split keeps the blend on the next segment, never on the last one."""
    core = _core()
    if core.split_bbone_weight(1.0, 3, 0.25, BBONE_SEGMENTS) != {3: 0.75, 4: 0.25}:
        raise AssertionError("regular blend split wrong")
    if core.split_bbone_weight(1.0, 7, 0.5, BBONE_SEGMENTS) != {7: 1.0}:
        raise AssertionError("last segment must keep the full weight")
    if core.split_bbone_weight(1.0, 3, 0.0, BBONE_SEGMENTS) != {3: 1.0}:
        raise AssertionError("zero blend must stay on the segment")
    if core.split_bbone_weight(0.5, 3, 1.0, BBONE_SEGMENTS) != {4: 0.5}:
        raise AssertionError("full blend must move everything to the next segment")
    if core.split_bbone_weight(1.0, 3, -0.5, BBONE_SEGMENTS) != {3: 1.0}:
        raise AssertionError("negative blend must clamp to 0")
    if core.split_bbone_weight(1.0, 3, 1.5, BBONE_SEGMENTS) != {4: 1.0}:
        raise AssertionError("blend > 1 must clamp to 1")
    for bad in (
        (1.0, 3, 0.25, 0),
        (1.0, 8, 0.25, BBONE_SEGMENTS),
    ):
        try:
            core.split_bbone_weight(*bad)
        except ValueError:
            continue
        raise AssertionError("split with {0} must raise ValueError".format(bad))
    return "split_bbone_weight: blend, last segment, clamping and bounds ok"


def test_transfer_bbone_weights():
    """After the convert the _seg_ groups exist, deform totals stay 1.0 and the
    mask group is left untouched (normalisation touches deform groups only)."""
    core = _core()
    _scene, arm_obj, meshes = build()
    for mesh in meshes:
        group = mesh.vertex_groups.new(name="MaskWeight")
        group.add(list(range(len(mesh.data.vertices))), 0.25, "REPLACE")

    core.convert_bbones_to_segments(arm_obj)
    transfer = core.transfer_bbone_weights(arm_obj)
    if len(transfer["meshes"]) != 2:
        raise AssertionError("transfer touched {0} meshes, expected 2".format(len(transfer["meshes"])))
    if "BendyA.000" not in transfer["sources"]:
        raise AssertionError("BendyA.000 was not transferred")
    if not transfer["segments"]:
        raise AssertionError("no segment groups written")

    for mesh in meshes:
        group_by_index = {group.index: group.name for group in mesh.vertex_groups}
        for vertex in mesh.data.vertices:
            deform_total = sum(
                element.weight
                for element in vertex.groups
                if "_seg_" in group_by_index[element.group]
            )
            if abs(deform_total - 1.0) > core.POSE_MATCH_MAX_ERROR:
                raise AssertionError(
                    "{0}: vertex {1} deform total {2:.6f} != 1.0".format(
                        mesh.name, vertex.index, deform_total
                    )
                )
            mask_total = sum(
                element.weight
                for element in vertex.groups
                if group_by_index[element.group] == "MaskWeight"
            )
            if abs(mask_total - 0.25) > 1e-6:
                raise AssertionError(
                    "{0}: vertex {1} mask total {2:.6f} != 0.25".format(
                        mesh.name, vertex.index, mask_total
                    )
                )
    return "transfer: {0} segment groups, deform totals 1.0, mask untouched".format(
        len(transfer["segments"])
    )


def test_pose_segments_from_bbones():
    """Every segment is posed from the rest bbone curve (rest=True path)."""
    core = _core()
    _scene, arm_obj, _ = build()
    core.convert_bbones_to_segments(arm_obj)
    report = core.pose_segments_from_bbones(arm_obj)
    if report["missing"]:
        raise AssertionError("missing segments: {0}".format(sorted(report["missing"])))
    if len(report["posed"]) != _segment_count():
        raise AssertionError(
            "posed {0} segments != {1}".format(len(report["posed"]), _segment_count())
        )
    return "pose_segments_from_bbones: {0} segments posed".format(len(report["posed"]))


def test_select_only_segment_bones():
    """Selection ends with only the converted segments selected."""
    core = _core()
    _scene, arm_obj, _ = build()
    core.convert_bbones_to_segments(arm_obj)
    seg_names = set(_segment_names(arm_obj))
    selected = core.select_only_segment_bones(arm_obj)
    if set(selected) != seg_names:
        raise AssertionError("selected {0} != segments {1}".format(sorted(selected), sorted(seg_names)))
    for pose_bone in arm_obj.pose.bones:
        is_selected = getattr(pose_bone, "select", False) or getattr(pose_bone.bone, "select", False)
        if bool(is_selected) != (pose_bone.name in seg_names):
            raise AssertionError(
                "{0} selected={1}, expected {2}".format(
                    pose_bone.name, is_selected, pose_bone.name in seg_names
                )
            )
    return "select_only_segment_bones: {0} segments selected".format(len(selected))


def test_add_remove_follow_constraints():
    """Constraints named CONSTRAINT_NAME are added once per segment and removed
    completely by remove_bbone_follow_constraints."""
    core = _core()
    _scene, arm_obj, _ = build()
    core.convert_bbones_to_segments(arm_obj)
    seg_names = _segment_names(arm_obj)

    added = core.add_bbone_follow_constraints(arm_obj)
    if added["missing"] or len(added["constrained"]) != len(seg_names):
        raise AssertionError(
            "constrained {0} != {1} segments".format(len(added["constrained"]), len(seg_names))
        )
    for name in seg_names:
        constraints = [
            c for c in arm_obj.pose.bones[name].constraints
            if c.name == core.CONSTRAINT_NAME
        ]
        if len(constraints) != 1 or constraints[0].type != "COPY_TRANSFORMS":
            raise AssertionError("{0} must carry one COPY_TRANSFORMS follow".format(name))

    core.add_bbone_follow_constraints(arm_obj)
    for name in seg_names:
        constraints = [
            c for c in arm_obj.pose.bones[name].constraints
            if c.name == core.CONSTRAINT_NAME
        ]
        if len(constraints) != 1:
            raise AssertionError("re-adding must not duplicate the constraint on {0}".format(name))

    removed = core.remove_bbone_follow_constraints(arm_obj)
    if removed != len(seg_names):
        raise AssertionError("removed {0} constraints != {1}".format(removed, len(seg_names)))
    for name in seg_names:
        if arm_obj.pose.bones[name].constraints.get(core.CONSTRAINT_NAME) is not None:
            raise AssertionError("{0} still carries the follow constraint".format(name))
    return "follow constraints: {0} added (idempotent) and {1} removed".format(len(seg_names), removed)


def test_collect_and_assign_armature_actions():
    """collect_armature_actions finds the fixture action; assign makes it active."""
    import bpy

    core = _core()
    _scene, arm_obj, _ = build()
    actions = core.collect_armature_actions(arm_obj)
    if not actions:
        raise AssertionError("no armature action found on the fixture")
    action = bpy.data.actions.new("BTOB_TestAction")
    core.assign_armature_action(arm_obj, action)
    if arm_obj.animation_data.action != action:
        raise AssertionError("assign_armature_action did not activate the action")
    actions_after = core.collect_armature_actions(arm_obj)
    if action not in actions_after:
        raise AssertionError("assigned action not collected")
    return "actions: {0} found, assigned action collected".format(len(actions_after))


def test_bake_segments_animation():
    """Baking over the 30 fixture frames keys every segment and clears the
    follow constraints; the active action carries segment F-Curves."""
    core = _core()
    _scene, arm_obj, _ = build()
    core.convert_bbones_to_segments(arm_obj)
    seg_names = _segment_names(arm_obj)

    report = core.bake_segments_animation(arm_obj)
    if not report["baked"]:
        raise AssertionError("bake reported no baked segments")
    for name in seg_names:
        if arm_obj.pose.bones[name].constraints.get(core.CONSTRAINT_NAME) is not None:
            raise AssertionError("{0} still carries the follow constraint after bake".format(name))
    action = arm_obj.animation_data.action
    curves = _action_fcurves(action)
    curve_bones = set()
    for curve in curves:
        name = _fcurve_bone_name(curve.data_path)
        if name is not None:
            curve_bones.add(name)
    missing = set(seg_names) - curve_bones
    if missing:
        raise AssertionError("segments without F-Curves after bake: {0}".format(sorted(missing)))
    return "bake: {0} segments keyed on {1} frames, no residual constraints".format(
        len(report["baked"]), report["frame_end"] - report["frame_start"] + 1
    )


def main():
    import bpy

    tests = [
        test_find_rigged_meshes,
        test_vertex_coords_in_armature_space,
        test_split_bbone_weight,
        test_transfer_bbone_weights,
        test_pose_segments_from_bbones,
        test_select_only_segment_bones,
        test_add_remove_follow_constraints,
        test_collect_and_assign_armature_actions,
        test_bake_segments_animation,
    ]
    for test in tests:
        check(test.__name__, test)

    print("BTOB core weights/bake suite addon={0} blender={1}".format(
        os.path.basename(ROOT), bpy.app.version_string
    ))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
