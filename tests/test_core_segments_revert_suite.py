# -*- coding: utf-8 -*-
"""Headless self-contained suite for the public core API of Fase 1.

Companion of ``tests/run.py``: it rebuilds the same in-memory fixture
(``make_fixture.build``) and covers EVERY public function of ``core/segments.py``
(``is_convertible_bone``, ``segment_bone_name``, ``collect_segment_specs``,
``convert_bbones_to_segments``) and of ``core/revert.py``
(``revert_segments_to_bbones``). It never imports ``tests/run.py`` (that module
executes its own runner on import) and never touches the add-on UI code.

Usage:
    blender -b --python tests/test_core_segments_revert_suite.py

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


def _add_tip_child(arm_obj, parent_name, child_name="TipChild"):
    """Add a plain (non-bbone) child bone to the fixture before a conversion."""
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


def _add_extra_bone(arm_obj, name, head, tail, parent_name=None, bbone_segments=1, deform=True):
    """Add an extra bone (bendy or not) to the fixture, then back to OBJECT."""
    import bpy

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit_bones = arm_obj.data.edit_bones
        bone = edit_bones.new(name)
        bone.head = head
        bone.tail = tail
        if parent_name is not None:
            bone.parent = edit_bones[parent_name]
            bone.use_connect = False
        bone.bbone_segments = bbone_segments
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        if previous_active is not None and previous_active != arm_obj:
            view_layer.objects.active = previous_active
    arm_obj.data.bones[name].use_deform = deform
    return name


def _original_parent_map(arm_obj):
    """Return {bone_name: parent_name or None} from the current rig."""
    return {
        bone.name: getattr(bone.parent, "name", None)
        for bone in arm_obj.data.bones
    }


def test_segment_bone_name():
    """Formato `_seg_00` a due cifre e nessuna collisione coi nomi originali."""
    core = _core()
    _scene, arm_obj, _ = build()

    if core.segment_bone_name("BendyA.000", 0) != "BendyA.000_seg_00":
        raise AssertionError("indice 0 non e' `_seg_00`")
    if core.segment_bone_name("BendyA.000", 7) != "BendyA.000_seg_07":
        raise AssertionError("indice 7 non e' `_seg_07`")
    if core.segment_bone_name("BendyC.003", 9) != "BendyC.003_seg_09":
        raise AssertionError("indice 9 non e' zero-padded `_seg_09`")
    if core.segment_bone_name("Hip", 0) != "Hip_seg_00":
        raise AssertionError("nome con punto non gestito")
    try:
        core.segment_bone_name("BendyA.000", -1)
    except ValueError:
        pass
    else:
        raise AssertionError("indice negativo non solleva ValueError")

    original_names = {bone.name for bone in arm_obj.data.bones}
    seg_names = [core.segment_bone_name(src, i) for src in original_names for i in range(8)]
    collisions = [name for name in seg_names if name in original_names]
    if collisions:
        raise AssertionError("collisione tra segmenti e nomi originali: {0}".format(sorted(collisions)))
    if len(set(seg_names)) != len(seg_names):
        raise AssertionError("nomi segmento duplicati")
    return "segment_bone_name ok: 2 cifre, nessuna collisione, ValueError su indice negativo"


def test_is_convertible_bone():
    """True su bendy deform, False su non-deform/normale/MCH non deform."""
    core = _core()
    _scene, arm_obj, _ = build()

    for name in _source_names():
        if not core.is_convertible_bone(arm_obj.data.bones[name]):
            raise AssertionError("bendy deform {0} non convertibile".format(name))
    if core.is_convertible_bone(arm_obj.data.bones[HIP_NAME]):
        raise AssertionError("Hip (bbone_segments<=1) convertibile")

    _add_extra_bone(
        arm_obj, "MCH_Helper", (0.5, 0.0, 1.2), (0.5, 0.0, 1.8),
        parent_name=HIP_NAME, bbone_segments=8, deform=False,
    )
    mch = arm_obj.data.bones["MCH_Helper"]
    if core.is_convertible_bone(mch):
        raise AssertionError("MCH_Helper non deform convertibile con deform_only=True")
    if not core.is_convertible_bone(mch, deform_only=False):
        raise AssertionError("MCH_Helper non convertibile con deform_only=False")

    _add_extra_bone(
        arm_obj, "PlainBone", (0.5, 0.25, 1.2), (0.5, 0.25, 1.8),
        parent_name=HIP_NAME, bbone_segments=1, deform=True,
    )
    if core.is_convertible_bone(arm_obj.data.bones["PlainBone"]):
        raise AssertionError("osso normale (bbone_segments<=1) convertibile")
    return "is_convertible_bone ok: bendy deform si, non-deform/normale/MCH no"


def test_collect_segment_specs():
    """12 sorgenti x 8 specs, parent corretto, use_connect=False, head sulla curva."""
    core = _core()
    _scene, arm_obj, _ = build()
    tolerance = core.HEAD_MATCH_TOLERANCE

    specs = core.collect_segment_specs(arm_obj)
    if len(specs) != _segment_count():
        raise AssertionError("specs {0} != {1}".format(len(specs), _segment_count()))
    if len({spec["name"] for spec in specs}) != len(specs):
        raise AssertionError("nomi spec duplicati")

    by_source = {}
    for spec in specs:
        by_source.setdefault(spec["source"], []).append(spec)

    for source in _source_names():
        chain = by_source[source]
        if len(chain) != BBONE_SEGMENTS:
            raise AssertionError("{0}: {1} specs != 8".format(source, len(chain)))
        original_parent = _original_parent_map(arm_obj)[source]
        for spec in chain:
            if spec["name"] != core.segment_bone_name(source, spec["index"]):
                raise AssertionError("{0}: nome spec non derivato".format(source))
            if spec["use_connect"] is not False:
                raise AssertionError("{0}: use_connect non False".format(spec["name"]))
            pose_bone = arm_obj.pose.bones[source]
            matrix = arm_obj.data.bones[source].matrix_local @ pose_bone.bbone_segment_matrix(spec["index"], rest=True)
            expected_head = matrix.to_translation()
            delta = (spec["head"] - expected_head).length
            if delta > tolerance:
                raise AssertionError(
                    "{0}: head dista {1:.2e} dalla curva bbone (tolleranza {2})".format(
                        spec["name"], delta, tolerance))
        first = chain[0]
        if original_parent in _source_names():
            # Il parent e' anch'esso una sorgente bendy convertita: la catena
            # continua sull'ULTIMO segmento del parent (non sul parent stesso).
            expected_first_parent = core.segment_bone_name(original_parent, BBONE_SEGMENTS - 1)
        else:
            # Parent non bendy (o assente): si mantiene il parent originale.
            expected_first_parent = original_parent
        if first["parent"] != expected_first_parent:
            raise AssertionError(
                "{0}: primo segmento parent {1} != {2}".format(source, first["parent"], expected_first_parent))
        for index in range(1, BBONE_SEGMENTS):
            expected_parent = core.segment_bone_name(source, index - 1)
            if chain[index]["parent"] != expected_parent:
                raise AssertionError(
                    "{0}: segmento {1} parent {2} != {3}".format(
                        source, index, chain[index]["parent"], expected_parent))

    chain_a = _source_names()[:BONES_PER_CHAIN]
    restricted = core.collect_segment_specs(arm_obj, bone_names=chain_a)
    if len(restricted) != BONES_PER_CHAIN * BBONE_SEGMENTS:
        raise AssertionError("bone_names: {0} specs != {1}".format(len(restricted), BONES_PER_CHAIN * BBONE_SEGMENTS))
    try:
        core.collect_segment_specs(arm_obj, bone_names=["NonEsiste"])
    except ValueError:
        pass
    else:
        raise AssertionError("bone_names inesistente non solleva ValueError")
    return "collect_segment_specs ok: {0} specs, parent e head verificati (toll. {1})".format(
        len(specs), tolerance)


def test_convert_report_flags_and_mode_changes():
    """Report (converted=12, created=96, mode_changes<=2), deform flags, figli."""
    core = _core()
    _scene, arm_obj, _ = build()
    _add_tip_child(arm_obj, "{0}B.003".format(CHAIN_PREFIX), "TipChild")
    last = BBONE_SEGMENTS - 1

    report = core.convert_bbones_to_segments(arm_obj)
    if len(report["converted"]) != 12:
        raise AssertionError("converted {0} != 12".format(len(report["converted"])))
    if len(report["created"]) != _segment_count():
        raise AssertionError("created {0} != {1}".format(len(report["created"]), _segment_count()))
    if not (1 <= report["mode_changes"] <= 2):
        raise AssertionError("mode_changes {0} fuori da [1,2]".format(report["mode_changes"]))
    for source in _source_names():
        if len(report["segments"].get(source, [])) != BBONE_SEGMENTS:
            raise AssertionError("{0}: {1} segmenti nel report".format(source, len(report["segments"].get(source, []))))

    for name in _source_names():
        if arm_obj.data.bones[name].use_deform:
            raise AssertionError("sorgente {0} ancora use_deform=True".format(name))
    for name in report["created"]:
        if not arm_obj.data.bones[name].use_deform:
            raise AssertionError("segmento {0} non use_deform=True".format(name))
        if not name.startswith(name.split("_seg_")[0] + "_seg_"):
            raise AssertionError("nome segmento {0} non derivato dalla sorgente".format(name))
    original_names = set(_source_names()) | {HIP_NAME}
    crash = [name for name in report["created"] if name in original_names]
    if crash:
        raise AssertionError("segmenti che collidono con nomi originali: {0}".format(sorted(crash)))

    tip_parent = getattr(arm_obj.data.bones["TipChild"].parent, "name", None)
    expected_tip = core.segment_bone_name("{0}B.003".format(CHAIN_PREFIX), last)
    if tip_parent != expected_tip:
        raise AssertionError("TipChild parent {0} != ultimo segmento {1}".format(tip_parent, expected_tip))
    if report["reparented_children"].get("TipChild") != expected_tip:
        raise AssertionError("report reparented_children non registra TipChild")
    return ("convert ok: converted=12, created=96, mode_changes={0}, sorgenti "
            "non-deform, segmenti deform, TipChild sull'ultimo segmento".format(report["mode_changes"]))


def test_convert_inherits_use_deform():
    """I segmenti ereditano use_deform della sorgente (anche False)."""
    core = _core()
    _scene, arm_obj, _ = build()
    _add_extra_bone(
        arm_obj, "PassiveBone", (0.5, 0.0, 1.2), (0.5, 0.0, 1.8),
        parent_name=HIP_NAME, bbone_segments=8, deform=False,
    )

    report = core.convert_bbones_to_segments(arm_obj, deform_only=False)
    if "PassiveBone" not in report["converted"]:
        raise AssertionError("PassiveBone non convertita con deform_only=False")
    if len(report["converted"]) != 13:
        raise AssertionError("converted {0} != 13".format(len(report["converted"])))
    if len(report["created"]) != 13 * BBONE_SEGMENTS:
        raise AssertionError("created {0} != 104".format(len(report["created"])))
    for source in _source_names():
        if arm_obj.data.bones[source].use_deform:
            raise AssertionError("sorgente {0} ancora deform".format(source))
    for index in range(BBONE_SEGMENTS):
        name = core.segment_bone_name("PassiveBone", index)
        if arm_obj.data.bones[name].use_deform:
            raise AssertionError("segmento {0} deve ereditare use_deform=False".format(name))
    return "convert ok: use_deform ereditato (PassiveBone False, sorgenti deform True)"


def test_convert_reparent_children_false():
    """reparent_children=False lascia i figli sotto la sorgente originale."""
    core = _core()
    _scene, arm_obj, _ = build()
    _add_tip_child(arm_obj, "{0}B.003".format(CHAIN_PREFIX), "TipChild")

    report = core.convert_bbones_to_segments(arm_obj, reparent_children=False)
    tip_parent = getattr(arm_obj.data.bones["TipChild"].parent, "name", None)
    if tip_parent != "{0}B.003".format(CHAIN_PREFIX):
        raise AssertionError("TipChild reparentato a {0} nonostante reparent_children=False".format(tip_parent))
    if report["reparented_children"]:
        raise AssertionError("report reparented_children non vuoto: {0}".format(report["reparented_children"]))
    return "convert ok: reparent_children=False lascia i figli alle sorgenti"


def test_revert_full_cycle():
    """Dopo convert+revert: 0 segmenti residui, sorgenti deform, rig identico."""
    core = _core()
    _scene, arm_obj, _ = build()
    _add_tip_child(arm_obj, "{0}B.003".format(CHAIN_PREFIX), "TipChild")
    before_names = sorted(bone.name for bone in arm_obj.data.bones)
    before_parents = _original_parent_map(arm_obj)

    report_convert = core.convert_bbones_to_segments(arm_obj)
    if len(report_convert["converted"]) != 12:
        raise AssertionError("converted {0} != 12".format(len(report_convert["converted"])))

    revert = core.revert_segments_to_bbones(arm_obj)
    if len(revert["reverted"]) != 12:
        raise AssertionError("reverted {0} != 12".format(len(revert["reverted"])))
    if len(revert["removed_segments"]) != _segment_count():
        raise AssertionError("removed_segments {0} != {1}".format(len(revert["removed_segments"]), _segment_count()))
    leftover = [bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name]
    if leftover:
        raise AssertionError("segmenti residui dopo revert: {0}".format(sorted(leftover)))
    for name in _source_names():
        if not arm_obj.data.bones[name].use_deform:
            raise AssertionError("sorgente {0} non ripristinata deform".format(name))
    after_names = sorted(bone.name for bone in arm_obj.data.bones)
    if after_names != before_names:
        raise AssertionError("nomi rig cambiati: {0} -> {1}".format(before_names, after_names))
    after_parents = _original_parent_map(arm_obj)
    if after_parents != before_parents:
        diff = {k: (before_parents[k], after_parents[k]) for k in before_parents if before_parents[k] != after_parents[k]}
        raise AssertionError("parentele cambiate dopo revert: {0}".format(diff))
    tip_parent = getattr(arm_obj.data.bones["TipChild"].parent, "name", None)
    if tip_parent != "{0}B.003".format(CHAIN_PREFIX):
        raise AssertionError("TipChild parent {0} != {1}B.003".format(tip_parent, CHAIN_PREFIX))
    return "revert ok: {0} sorgenti ripristinate, {1} segmenti rimossi, rig identico".format(
        len(revert["reverted"]), len(revert["removed_segments"]))


def test_revert_bone_names_limit():
    """bone_names limita il revert ai soli selezionati (catena A)."""
    core = _core()
    _scene, arm_obj, _ = build()
    chain_a = ["{0}A.{1:03d}".format(CHAIN_PREFIX, seg) for seg in range(BONES_PER_CHAIN)]
    chain_bc = [
        "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
        for letter in ("B", "C")
        for seg in range(BONES_PER_CHAIN)
    ]

    core.convert_bbones_to_segments(arm_obj)
    revert = core.revert_segments_to_bbones(arm_obj, bone_names=chain_a)
    if len(revert["reverted"]) != len(chain_a):
        raise AssertionError("reverted {0} != {1}".format(len(revert["reverted"]), len(chain_a)))
    if len(revert["removed_segments"]) != len(chain_a) * BBONE_SEGMENTS:
        raise AssertionError("removed_segments {0} != 32".format(len(revert["removed_segments"])))
    for name in chain_a:
        if not arm_obj.data.bones[name].use_deform:
            raise AssertionError("catena A {0} non ripristinata".format(name))
    for name in chain_bc:
        if arm_obj.data.bones[name].use_deform:
            raise AssertionError("catena B/C {0} ripristinata per errore".format(name))
    leftover = [bone.name for bone in arm_obj.data.bones if "_seg_" in bone.name]
    if len(leftover) != len(chain_bc) * BBONE_SEGMENTS:
        raise AssertionError("leftover {0} != 64".format(len(leftover)))
    for name in leftover:
        if not name.startswith(("BendyB.", "BendyC.")):
            raise AssertionError("segmento estraneo rimasto: {0}".format(name))
    return "revert ok: bone_names limita a catena A ({0} segmenti B/C rimasti)".format(len(leftover))


def test_revert_unknown_bone_name_value_error():
    """Nome inesistente in bone_names solleva ValueError."""
    core = _core()
    _scene, arm_obj, _ = build()
    core.convert_bbones_to_segments(arm_obj)
    try:
        core.revert_segments_to_bbones(arm_obj, bone_names=["NonEsiste"])
    except ValueError:
        pass
    else:
        raise AssertionError("bone_names inesistente non solleva ValueError")
    # Hip non e' bendy: nessun revert, nessun errore.
    empty = core.revert_segments_to_bbones(arm_obj, bone_names=[HIP_NAME])
    if empty["reverted"] or empty["removed_segments"]:
        raise AssertionError("Hip (non bendy) revertito per errore")
    return "revert ok: ValueError su nome inesistente, Hip non-bendy saltato"


def main():
    import bpy

    tests = [
        test_segment_bone_name,
        test_is_convertible_bone,
        test_collect_segment_specs,
        test_convert_report_flags_and_mode_changes,
        test_convert_inherits_use_deform,
        test_convert_reparent_children_false,
        test_revert_full_cycle,
        test_revert_bone_names_limit,
        test_revert_unknown_bone_name_value_error,
    ]
    for test in tests:
        check(test.__name__, test)

    print("BTOB core segments/revert suite addon={0} blender={1}".format(
        os.path.basename(ROOT), bpy.app.version_string))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
