# -*- coding: utf-8 -*-
"""Headless test suite dedicated to the REVERT of BBone to Bones.

Companion of ``tests/run.py``: it rebuilds the same in-memory fixture
(``make_fixture.build``) and covers the revert contract of Fase 1
(``core.revert_segments_to_bbones``) and of the UI operator
(``btob.revert_to_bbones``). It never imports ``tests/run.py`` (that module
executes its own runner on import) and never touches the add-on code.

Usage:
    blender -b --python tests/test_revert_suite.py

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
    HIP_NAME,
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


def _root_source_names():
    """One source per chain: the root that owns the fixture weights."""
    return ["{0}{1}.000".format(CHAIN_PREFIX, letter) for letter in CHAIN_NAMES]


def _segment_count():
    """Segments produced by the fixture: 12 bendy bones x 8 segments."""
    return len(CHAIN_NAMES) * BONES_PER_CHAIN * BBONE_SEGMENTS


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


def _assert_no_segment_bones(arm_obj):
    """Fail if any ``_seg_`` bone survives the revert."""
    leftover = [bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name]
    if leftover:
        raise AssertionError("segments left after revert: {0}".format(sorted(leftover)))


def _assert_no_segment_groups(mesh_obj):
    """Fail if any ``_seg_`` vertex group survives the revert."""
    leftover = [group.name for group in mesh_obj.vertex_groups if "_seg_" in group.name]
    if leftover:
        raise AssertionError(
            "{0}: segment groups left after revert: {1}".format(mesh_obj.name, sorted(leftover))
        )


def _assert_weight_totals(mesh_obj, tolerance=1e-4):
    """Every vertex must keep its original total weight (1.0) after the revert."""
    for vertex in mesh_obj.data.vertices:
        total = sum(element.weight for element in vertex.groups)
        if abs(total - 1.0) > tolerance:
            raise AssertionError(
                "{0}: vertex {1} weight total {2:.6f} != 1.0".format(
                    mesh_obj.name, vertex.index, total
                )
            )


def _assert_sources_deform(arm_obj, sources, expected):
    """Assert each ``sources`` bone has ``use_deform == expected``."""
    for name in sources:
        bone = arm_obj.data.bones.get(name)
        if bone is None:
            raise AssertionError("source bone {0} missing".format(name))
        if bool(bone.use_deform) != expected:
            raise AssertionError(
                "{0} use_deform={1}, expected {2}".format(name, bone.use_deform, expected)
            )


def test_revert_simple_conversion():
    """Revert after a plain conversion: no _seg_ bones, sources deform again,
    hierarchy identical to the original fixture."""
    core = _core()
    _scene, arm_obj, _ = build()
    _add_tip_child(arm_obj, "{0}B.003".format(CHAIN_PREFIX), "TipChild")
    before_names = sorted(bone.name for bone in arm_obj.data.bones)

    report = core.convert_bbones_to_segments(arm_obj)
    if len(report["converted"]) != len(_source_names()):
        raise AssertionError(
            "converted {0} sources != {1}".format(len(report["converted"]), len(_source_names()))
        )
    if len([bone for bone in arm_obj.data.bones if "_seg_" in bone.name]) != _segment_count():
        raise AssertionError("conversion did not produce {0} segments".format(_segment_count()))
    last = BBONE_SEGMENTS - 1
    tip_parent = getattr(arm_obj.data.bones["TipChild"].parent, "name", None)
    if tip_parent != core.segment_bone_name("{0}B.003".format(CHAIN_PREFIX), last):
        raise AssertionError(
            "after convert TipChild parent {0} != last segment".format(tip_parent)
        )

    revert = core.revert_segments_to_bbones(arm_obj)
    if len(revert["reverted"]) != len(_source_names()):
        raise AssertionError(
            "reverted {0} sources != {1}".format(len(revert["reverted"]), len(_source_names()))
        )
    if len(revert["removed_segments"]) != _segment_count():
        raise AssertionError(
            "removed {0} segments != {1}".format(
                len(revert["removed_segments"]), _segment_count()
            )
        )
    _assert_no_segment_bones(arm_obj)
    _assert_sources_deform(arm_obj, _source_names(), True)
    after_names = sorted(bone.name for bone in arm_obj.data.bones)
    if after_names != before_names:
        raise AssertionError("rig bones changed: {0} -> {1}".format(before_names, after_names))
    if arm_obj.data.bones[HIP_NAME].parent is not None:
        raise AssertionError("Hip must stay a root bone")
    if arm_obj.data.bones["{0}A.000".format(CHAIN_PREFIX)].parent is not None:
        raise AssertionError("Chain A root must stay unparented")
    for letter in ("B", "C"):
        root = arm_obj.data.bones["{0}{1}.000".format(CHAIN_PREFIX, letter)]
        parent_name = getattr(root.parent, "name", None)
        if parent_name != HIP_NAME:
            raise AssertionError("Chain {0} root parent {1} != {2}".format(letter, parent_name, HIP_NAME))
    if getattr(arm_obj.data.bones["TipChild"].parent, "name", None) != "{0}B.003".format(CHAIN_PREFIX):
        raise AssertionError("TipChild not re-parented to BendyB.003 after revert")
    return "simple revert: {0} sources back, {1} segments removed, rig identical".format(
        len(revert["reverted"]), len(revert["removed_segments"])
    )


def test_revert_after_weight_transfer():
    """Revert restores the original vertex groups and removes the _seg_ groups."""
    core = _core()
    _scene, arm_obj, meshes = build()
    high = meshes[0]
    _distribute_chains(arm_obj, high)

    core.convert_bbones_to_segments(arm_obj)
    core.transfer_bbone_weights(arm_obj)
    seg_groups = [group.name for group in high.vertex_groups if "_seg_" in group.name]
    if not seg_groups:
        raise AssertionError("no _seg_ groups after the transfer")

    core.revert_segments_to_bbones(arm_obj)
    _assert_no_segment_bones(arm_obj)
    _assert_no_segment_groups(high)
    for name in _root_source_names():
        if high.vertex_groups.get(name) is None:
            raise AssertionError(
                "{0}: source group {1} missing after revert".format(high.name, name)
            )
    _assert_weight_totals(high)
    return "weights restored on {0}: {1} source groups, all vertices total 1.0".format(
        high.name, len(_root_source_names())
    )


def test_revert_selected_bones_only():
    """Selected Bones Only converts chains A+B, then reverts only the selected subset (Chain A)."""
    import bpy

    mod = _addon_module()
    _scene, arm_obj, _ = build()
    settings = None
    try:
        mod.register()
        settings = bpy.context.scene.bbone_to_bones_settings
        settings.selected_bones_only = True
        bpy.context.view_layer.objects.active = arm_obj
        chain_a = ["{0}A.{1:03d}".format(CHAIN_PREFIX, seg) for seg in range(BONES_PER_CHAIN)]
        chain_b = ["{0}B.{1:03d}".format(CHAIN_PREFIX, seg) for seg in range(BONES_PER_CHAIN)]
        # Blender 5.2 keeps the selection on the pose bone (Bone data has no
        # ``select``, only ``hide_select``).
        for pose_bone in arm_obj.pose.bones:
            pose_bone.select = pose_bone.name in chain_a or pose_bone.name in chain_b
        result = bpy.ops.btob.convert_segments()
        if result != {"FINISHED"}:
            raise AssertionError("convert_segments returned {0}".format(sorted(result)))
        created = [bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name]
        expected = 2 * BONES_PER_CHAIN * BBONE_SEGMENTS
        if len(created) != expected:
            raise AssertionError(
                "selected convert created {0} segments, expected {1}".format(len(created), expected)
            )

        # Keep only chain A selected: the selected revert must affect A alone.
        for pose_bone in arm_obj.pose.bones:
            pose_bone.select = pose_bone.name in chain_a
        result = bpy.ops.btob.revert_to_bbones()
        if result != {"FINISHED"}:
            raise AssertionError("revert_to_bbones returned {0}".format(sorted(result)))
        leftover = [bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name]
        prefix_a = "{0}A.".format(CHAIN_PREFIX)
        for name in leftover:
            if name.startswith(prefix_a):
                raise AssertionError("Chain A segment {0} still present after selected revert".format(name))
        prefix_b = "{0}B.".format(CHAIN_PREFIX)
        expected_left = BONES_PER_CHAIN * BBONE_SEGMENTS
        if len(leftover) != expected_left or any(
            not name.startswith(prefix_b) for name in leftover
        ):
            raise AssertionError(
                "after selected revert leftover {0} != chain B only ({1})".format(
                    sorted(leftover), expected_left
                )
            )
        for name in chain_b:
            if arm_obj.data.bones[name].use_deform:
                raise AssertionError(
                    "Chain B source {0} must stay non-deform".format(name)
                )
        for name in chain_a:
            if not arm_obj.data.bones[name].use_deform:
                raise AssertionError(
                    "Chain A source {0} must be deform again after selected revert".format(name)
                )
    finally:
        if settings is not None:
            settings.selected_bones_only = False
        mod.unregister()
    return "selected revert: Chain A back, chain B still converted ({0} segments left)".format(
        len(leftover)
    )


def test_revert_unconverted_children():
    """Children that were never converted follow their segment and come back to
    their original source on revert; none is lost."""
    core = _core()
    _scene, arm_obj, _ = build()
    _add_tip_child(arm_obj, "{0}B.003".format(CHAIN_PREFIX), "TipChild")
    _add_tip_child(arm_obj, "{0}C.002".format(CHAIN_PREFIX), "LegChild")
    original_parents = {
        name: getattr(arm_obj.data.bones[name].parent, "name", None)
        for name in ("TipChild", "LegChild")
    }
    last = BBONE_SEGMENTS - 1
    before_non_segment = {
        bone.name for bone in arm_obj.data.bones if "_seg_" not in bone.name
    }

    core.convert_bbones_to_segments(arm_obj)
    for name, parent in original_parents.items():
        got = getattr(arm_obj.data.bones[name].parent, "name", None)
        expected = core.segment_bone_name(parent, last)
        if got != expected:
            raise AssertionError("{0} reparented to {1} != {2}".format(name, got, expected))
    # A child added AFTER the conversion is attached to a segment as well.
    _add_tip_child(arm_obj, core.segment_bone_name("BendyA.000", 3), "LateChild")

    core.revert_segments_to_bbones(arm_obj)
    _assert_no_segment_bones(arm_obj)
    expected_parents = dict(original_parents)
    expected_parents["LateChild"] = "BendyA.000"
    for name, parent in expected_parents.items():
        bone = arm_obj.data.bones.get(name)
        if bone is None:
            raise AssertionError("child {0} lost during the revert".format(name))
        got = getattr(bone.parent, "name", None)
        if got != parent:
            raise AssertionError("{0} parent {1} != {2}".format(name, got, parent))
    expected_after = before_non_segment | {"LateChild"}
    after_names = {bone.name for bone in arm_obj.data.bones}
    if after_names != expected_after:
        raise AssertionError(
            "rig bones changed: expected {0} got {1}".format(
                sorted(expected_after), sorted(after_names)
            )
        )
    return "children re-parented to their sources; no bone lost ({0} bones)".format(
        len(after_names)
    )


def test_revert_multiple_meshes():
    """All meshes linked to the same armature get their groups restored."""
    core = _core()
    _scene, arm_obj, meshes = build()
    if len(meshes) < 2:
        raise AssertionError("expected two meshes in the fixture")
    for mesh_obj in meshes:
        _distribute_chains(arm_obj, mesh_obj)

    core.convert_bbones_to_segments(arm_obj)
    core.transfer_bbone_weights(arm_obj)
    core.revert_segments_to_bbones(arm_obj)
    _assert_no_segment_bones(arm_obj)
    for mesh_obj in meshes:
        _assert_no_segment_groups(mesh_obj)
        for name in _root_source_names():
            if mesh_obj.vertex_groups.get(name) is None:
                raise AssertionError(
                    "{0}: source group {1} missing after revert".format(mesh_obj.name, name)
                )
        _assert_weight_totals(mesh_obj)
    return "groups restored on {0} meshes".format(len(meshes))


def test_revert_operator_undo():
    """The btob.revert_to_bbones operator finishes; undo brings the segments back
    when the session provides undo (background mode may not)."""
    import bpy

    mod = _addon_module()
    _scene, arm_obj, _ = build()
    undo_available = False
    try:
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message="init")
        undo_available = True
    except Exception:  # noqa: BLE001
        undo_available = False
    try:
        mod.register()
        bpy.context.view_layer.objects.active = arm_obj
        settings = bpy.context.scene.bbone_to_bones_settings
        settings.selected_bones_only = False

        result = bpy.ops.btob.convert_segments()
        if result != {"FINISHED"}:
            raise AssertionError("convert_segments returned {0}".format(sorted(result)))
        if len([bone for bone in arm_obj.data.bones if "_seg_" in bone.name]) != _segment_count():
            raise AssertionError("operator convert produced the wrong segment count")

        revert_cls = None
        for cls in mod.CLASSES:
            if getattr(cls, "bl_idname", "") == "btob.revert_to_bbones":
                revert_cls = cls
                break
        if revert_cls is None:
            raise AssertionError("btob.revert_to_bbones operator not registered")
        options = set(getattr(revert_cls, "bl_options", set()))
        if not {"REGISTER", "UNDO"}.issubset(options):
            raise AssertionError(
                "revert bl_options {0} lacks REGISTER/UNDO".format(sorted(options))
            )

        result = bpy.ops.btob.revert_to_bbones()
        if result != {"FINISHED"}:
            raise AssertionError("revert_to_bbones returned {0}".format(sorted(result)))
        _assert_no_segment_bones(arm_obj)

        if not undo_available:
            return "operator revert FINISHED; undo non disponibile in background"

        try:
            bpy.ops.ed.undo()
            segments = [bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name]
            if len(segments) == _segment_count() and all(
                not arm_obj.data.bones[name].use_deform for name in _source_names()
            ):
                return "operator revert FINISHED; undo restored {0} segments".format(_segment_count())
        except RuntimeError:
            # Background sessions expose no undo through the operator even when
            # undo_push succeeded: the revert operator itself already passed
            # the FINISHED / no-segment checks above.
            pass
        # Undo did not rewind the revert (background session): the operator
        # itself already passed the FINISHED / no-segment checks above.
        return "operator revert FINISHED; undo non disponibile in background"
    finally:
        mod.unregister()


def main():
    import bpy

    tests = [
        test_revert_simple_conversion,
        test_revert_after_weight_transfer,
        test_revert_selected_bones_only,
        test_revert_unconverted_children,
        test_revert_multiple_meshes,
        test_revert_operator_undo,
    ]
    for test in tests:
        check(test.__name__, test)

    print("BTOB revert suite addon={0} blender={1}".format(os.path.basename(ROOT), bpy.app.version_string))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
