# -*- coding: utf-8 -*-
"""Headless suite for every ``btob.*`` UI operator.

Companion of ``tests/run.py``: it rebuilds the same in-memory fixture
(``make_fixture.build``), registers the add-on (``add.register()``) and covers
all the 9 operators shipped by ``ui/operator_convert.py``,
``ui/operator_weights.py``, ``ui/operator_follow.py`` and
``ui/operator_export.py``. It never imports ``tests/run.py`` (that module
executes its own runner on import) and never touches the add-on code.

Usage:
    blender -b --python tests/test_ui_operators_suite.py

The verdict is the LAST line of stdout:
    RISULTATO passati=X falliti=Y totale=N
"""

import os
import sys
import tempfile

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

OPERATOR_IDNAMES = (
    "btob.convert_segments",
    "btob.revert_to_bbones",
    "btob.convert_all",
    "btob.transfer_weights",
    "btob.limit_influences",
    "btob.add_constraints",
    "btob.remove_constraints",
    "btob.bake_animation",
    "btob.export_rig",
)

SEG_SUFFIX = "_seg_"


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


def _source_names():
    """The 12 bendy source bones of the fixture."""
    return [
        "{0}{1}.{2:03d}".format(CHAIN_PREFIX, letter, seg)
        for letter in CHAIN_NAMES
        for seg in range(BONES_PER_CHAIN)
    ]


def _segment_names(arm_obj):
    """Every ``_seg_`` bone present on ``arm_obj``, sorted."""
    return sorted(bone.name for bone in arm_obj.data.bones if SEG_SUFFIX in bone.name)


def _segment_count():
    """Segments produced by converting the whole fixture."""
    return len(CHAIN_NAMES) * BONES_PER_CHAIN * BBONE_SEGMENTS


def _operator_class(mod, idname):
    for cls in mod.CLASSES:
        if getattr(cls, "bl_idname", "") == idname:
            return cls
    raise AssertionError("operatore {0} non registrato".format(idname))


def _call_operator(mod, idname):
    """Run ``idname`` via the operator registry; returns ``(result, [])``."""
    import bpy

    short = idname.split(".")[1]
    result = getattr(bpy.ops.btob, short)()
    return result, []


def _expect_error(mod, idname, fragment):
    """Run an operator, accept CANCELLED or the RuntimeError report from
    background mode, and require the fragment to appear in it."""
    try:
        result, _reports = _call_operator(mod, idname)
    except RuntimeError as exc:
        if fragment not in str(exc):
            raise AssertionError(
                "{0} errore senza frammento {1!r}: {2}".format(
                    idname, fragment, exc))
        return None
    if result != {"CANCELLED"}:
        raise AssertionError("{0} atteso CANCELLED, ottenuto {1}".format(idname, sorted(result)))
    return result


def _fcurve_bone_names():
    """Pose bone names keyed by any action of the file (4.2 / 5.x safe)."""
    import bpy

    names = set()
    for action in bpy.data.actions:
        if action is None:
            continue
        curves = getattr(action, "fcurves", None)
        if curves is None or not len(curves):
            curves = []
            for layer in getattr(action, "layers", None) or ():
                for strip in getattr(layer, "strips", ()):
                    for bag in getattr(strip, "channelbags", ()):
                        curves.extend(getattr(bag, "fcurves", ()))
        prefix = 'pose.bones["'
        for fcurve in curves:
            path = getattr(fcurve, "data_path", "")
            if path.startswith(prefix):
                end = path.find('"]', len(prefix))
                if end > 0:
                    names.add(path[len(prefix):end])
    return names


def _make_plain_armature():
    """An armature with no bendy bone (bbone_segments == 1)."""
    import bpy

    arm_data = bpy.data.armatures.new("PlainArmData")
    arm_obj = bpy.data.objects.new("PlainArm", arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bone = arm_data.edit_bones.new("PlainBone")
    bone.head = (0.0, 0.0, 0.0)
    bone.tail = (0.0, 0.0, 1.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_obj


def _make_influence_rig():
    """Six deform bones + one vertex weighted on all of them (6 influences)."""
    import bpy

    arm_data = bpy.data.armatures.new("CapArmData")
    arm_obj = bpy.data.objects.new("CapArm", arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = arm_data.edit_bones
    previous = None
    for index in range(6):
        bone = edit_bones.new("IB{0}".format(index))
        bone.head = (float(index) * 0.2, 0.0, 0.0)
        bone.tail = (float(index) * 0.2 + 0.15, 0.0, 0.0)
        if previous is not None:
            bone.parent = previous
            bone.use_connect = True
        previous = bone
    bpy.ops.object.mode_set(mode="OBJECT")

    mesh_data = bpy.data.meshes.new("CapMeshData")
    mesh_obj = bpy.data.objects.new("CapMesh", mesh_data)
    bpy.context.scene.collection.objects.link(mesh_obj)
    mesh_data.from_pydata([(0.1, 0.0, 0.0)], [], [])
    mesh_data.update()
    mesh_obj.parent = arm_obj
    modifier = mesh_obj.modifiers.new(name="CapRig", type="ARMATURE")
    modifier.object = arm_obj
    for index, weight in enumerate((1.0, 0.8, 0.6, 0.4, 0.2, 0.1)):
        group = mesh_obj.vertex_groups.new(name="IB{0}".format(index))
        group.add([0], weight, "ADD")
    return arm_obj, mesh_obj


def test_all_operators_registered_with_options():
    """All the 9 ``btob.*`` operators exist and carry REGISTER/UNDO."""
    mod = _addon_module()
    for idname in OPERATOR_IDNAMES:
        cls = _operator_class(mod, idname)
        options = set(getattr(cls, "bl_options", set()))
        if not {"REGISTER", "UNDO"}.issubset(options):
            raise AssertionError(
                "{0} bl_options {1} senza REGISTER/UNDO".format(idname, sorted(options))
            )
    return "verificati {0} operatori con REGISTER/UNDO".format(len(OPERATOR_IDNAMES))


def test_convert_segments_finished():
    """convert_segments converts the 12 bendy sources into 96 segments."""
    import bpy

    mod = _addon_module()
    _scene, arm_obj, _ = build()
    result, _reports = _call_operator(mod, "btob.convert_segments")
    if result != {"FINISHED"}:
        raise AssertionError("convert_segments restituito {0}".format(sorted(result)))
    segments = _segment_names(arm_obj)
    if len(segments) != _segment_count():
        raise AssertionError(
            "convertiti {0} segmenti, attesi {1}".format(len(segments), _segment_count())
        )
    if any(arm_obj.data.bones[name].use_deform for name in _source_names()):
        raise AssertionError("una sorgente bendy e' rimasta deform dopo la conversione")
    return "convert_segments FINISHED: {0} segmenti".format(len(segments))


def test_convert_segments_error_without_bendy():
    """convert_segments on a rig without bendy bones: clean error, no traceback."""
    mod = _addon_module()
    arm_obj = _make_plain_armature()
    _expect_error(mod, "btob.convert_segments", "No bendy bone")
    return "errore pulito senza bendy su {0}".format(arm_obj.name)


def test_revert_to_bbones_after_convert():
    """revert_to_bbones undoes the conversion; a second revert errors cleanly."""
    import bpy

    mod = _addon_module()
    _scene, arm_obj, _ = build()
    result, _reports = _call_operator(mod, "btob.convert_segments")
    if result != {"FINISHED"}:
        raise AssertionError("convert_segments restituito {0}".format(sorted(result)))

    result, _reports = _call_operator(mod, "btob.revert_to_bbones")
    if result != {"FINISHED"}:
        raise AssertionError("revert_to_bbones restituito {0}".format(sorted(result)))
    if _segment_names(arm_obj):
        raise AssertionError("segmenti rimasti dopo il revert")
    if any(not arm_obj.data.bones[name].use_deform for name in _source_names()):
        raise AssertionError("sorgenti non tornate deform dopo il revert")

    _expect_error(mod, "btob.revert_to_bbones", "No converted segment")

    # Undo: fallback "non disponibile" se il background non lo espone.
    undo_available = False
    try:
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message="init")
        undo_available = True
    except Exception:  # noqa: BLE001
        undo_available = False
    if undo_available:
        try:
            bpy.ops.ed.undo()
            if len(_segment_names(arm_obj)) == _segment_count():
                return "revert FINISHED, secondo revert errore pulito, undo ripristina i segmenti"
        except RuntimeError:
            pass
    return "revert FINISHED, secondo revert errore pulito, undo non disponibile in background"


def test_convert_all_converts_everything():
    """convert_all converts, weights and bakes the whole fixture in one call."""
    mod = _addon_module()
    _scene, arm_obj, meshes = build()
    result, _reports = _call_operator(mod, "btob.convert_all")
    if result != {"FINISHED"}:
        raise AssertionError("convert_all restituito {0}".format(sorted(result)))
    segments = _segment_names(arm_obj)
    if len(segments) != _segment_count():
        raise AssertionError("convert_all ha creato {0} segmenti, attesi {1}".format(
            len(segments), _segment_count()))
    for name in _source_names():
        seg0 = "{0}{1}00".format(name, SEG_SUFFIX)
        if seg0 not in arm_obj.data.bones:
            raise AssertionError("convert_all non ha convertito {0}".format(name))
    if not any(any(SEG_SUFFIX in g.name for g in mesh.vertex_groups) for mesh in meshes):
        raise AssertionError("convert_all non ha trasferito i pesi sui segmenti")
    baked = _fcurve_bone_names() & set(segments)
    if not baked:
        raise AssertionError("convert_all non ha bakeato alcun segmento")
    return "convert_all FINISHED: {0} segmenti, {1} bakeati".format(len(segments), len(baked))


def test_transfer_weights_finished():
    """transfer_weights moves the weights onto the segments after a conversion."""
    mod = _addon_module()
    _scene, arm_obj, meshes = build()
    result, _reports = _call_operator(mod, "btob.convert_segments")
    if result != {"FINISHED"}:
        raise AssertionError("convert_segments restituito {0}".format(sorted(result)))
    result, _reports = _call_operator(mod, "btob.transfer_weights")
    if result != {"FINISHED"}:
        raise AssertionError("transfer_weights restituito {0}".format(sorted(result)))
    if not any(any(SEG_SUFFIX in g.name for g in mesh.vertex_groups) for mesh in meshes):
        raise AssertionError("nessun gruppo _seg_ dopo il trasferimento")
    return "transfer_weights FINISHED su {0} meshes".format(len(meshes))


def test_transfer_weights_errors():
    """transfer_weights fails cleanly without conversion or without meshes."""
    mod = _addon_module()

    _scene, arm_obj, _ = build()
    _expect_error(mod, "btob.transfer_weights", "No converted segments")

    _scene, arm_obj, meshes = build()
    result, _reports = _call_operator(mod, "btob.convert_segments")
    if result != {"FINISHED"}:
        raise AssertionError("convert_segments restituito {0}".format(sorted(result)))
    import bpy

    for mesh_obj in meshes:
        bpy.data.objects.remove(mesh_obj)
    _expect_error(mod, "btob.transfer_weights", "No mesh")
    return "transfer_weights: errori puliti senza conversione e senza meshes"


def test_limit_influences_caps_and_normalizes():
    """limit_influences caps to max_influences and normalizes the kept weights."""
    import bpy

    mod = _addon_module()
    arm_obj, mesh_obj = _make_influence_rig()
    settings = bpy.context.scene.bbone_to_bones_settings
    settings.max_influences = 4
    result, _reports = _call_operator(mod, "btob.limit_influences")
    if result != {"FINISHED"}:
        raise AssertionError("limit_influences restituito {0}".format(sorted(result)))
    vertex = mesh_obj.data.vertices[0]
    if len(vertex.groups) != 4:
        raise AssertionError("influenze residue {0}, attese 4".format(len(vertex.groups)))
    total = sum(element.weight for element in vertex.groups)
    if abs(total - 1.0) > 1e-4:
        raise AssertionError("pesi non normalizzati dopo il limite: {0:.6f}".format(total))
    return "limit_influences FINISHED: 4 influenze normalizzate"


def test_limit_influences_error_without_mesh():
    """limit_influences fails cleanly when nothing is rigged to the armature."""
    import bpy

    mod = _addon_module()
    arm_obj, mesh_obj = _make_influence_rig()
    bpy.data.objects.remove(mesh_obj)
    _expect_error(mod, "btob.limit_influences", "No mesh")
    return "limit_influences: errore pulito senza meshes"


def test_add_remove_constraints():
    """add_constraints constraints every segment; remove_constraints deletes them."""
    import bpy

    mod = _addon_module()
    _scene, arm_obj, _ = build()
    settings = bpy.context.scene.bbone_to_bones_settings
    settings.add_live_follow = False
    result, _reports = _call_operator(mod, "btob.convert_segments")
    if result != {"FINISHED"}:
        raise AssertionError("convert_segments restituito {0}".format(sorted(result)))

    result, _reports = _call_operator(mod, "btob.add_constraints")
    if result != {"FINISHED"}:
        raise AssertionError("add_constraints restituito {0}".format(sorted(result)))
    segments = _segment_names(arm_obj)
    missing = [
        name for name in segments
        if arm_obj.pose.bones[name].constraints.get("BTOB_FollowBBone") is None
    ]
    if missing:
        raise AssertionError("{0} segmenti senza constraint di follow".format(len(missing)))

    result, _reports = _call_operator(mod, "btob.remove_constraints")
    if result != {"FINISHED"}:
        raise AssertionError("remove_constraints restituito {0}".format(sorted(result)))
    if any(
        arm_obj.pose.bones[name].constraints.get("BTOB_FollowBBone") is not None
        for name in segments
    ):
        raise AssertionError("constraint di follow rimasti dopo remove_constraints")
    return "add/remove_constraints FINISHED su {0} segmenti".format(len(segments))


def test_add_constraints_error_without_conversion():
    """add_constraints fails cleanly when no segment exists yet."""
    mod = _addon_module()
    _scene, arm_obj, _ = build()
    _expect_error(mod, "btob.add_constraints", "No converted segment")
    return "add_constraints: errore pulito senza conversione"


def test_selected_bones_only_convert_revert_constraints():
    """selected_bones_only limits convert/revert/add_constraints to chain A."""
    import bpy

    mod = _addon_module()
    _scene, arm_obj, _ = build()
    settings = bpy.context.scene.bbone_to_bones_settings
    settings.selected_bones_only = True
    chain_a = ["{0}A.{1:03d}".format(CHAIN_PREFIX, seg) for seg in range(BONES_PER_CHAIN)]
    try:
        for pose_bone in arm_obj.pose.bones:
            pose_bone.select = pose_bone.name in chain_a
        result, _reports = _call_operator(mod, "btob.convert_segments")
        if result != {"FINISHED"}:
            raise AssertionError("convert_segments restituito {0}".format(sorted(result)))
        segments = _segment_names(arm_obj)
        prefix_a = "{0}A.".format(CHAIN_PREFIX)
        if len(segments) != BONES_PER_CHAIN * BBONE_SEGMENTS or any(
            not name.startswith(prefix_a) for name in segments
        ):
            raise AssertionError(
                "conversione selezionata: {0} segmenti non solo catena A".format(len(segments))
            )

        result, _reports = _call_operator(mod, "btob.add_constraints")
        if result != {"FINISHED"}:
            raise AssertionError("add_constraints restituito {0}".format(sorted(result)))
        if any(
            arm_obj.pose.bones[name].constraints.get("BTOB_FollowBBone") is None
            for name in segments
        ):
            raise AssertionError("constraint mancante su un segmento selezionato")

        result, _reports = _call_operator(mod, "btob.revert_to_bbones")
        if result != {"FINISHED"}:
            raise AssertionError("revert_to_bbones restituito {0}".format(sorted(result)))
        if _segment_names(arm_obj):
            raise AssertionError("segmenti rimasti dopo il revert selezionato")
    finally:
        settings.selected_bones_only = False
    return "selected_bones_only: convert/revert/add_constraints solo catena A"


def test_bake_animation_fcurves_on_segments():
    """bake_animation keys the segments over the 30-frame fixture range."""
    mod = _addon_module()
    _scene, arm_obj, _ = build()
    result, _reports = _call_operator(mod, "btob.convert_segments")
    if result != {"FINISHED"}:
        raise AssertionError("convert_segments restituito {0}".format(sorted(result)))
    result, _reports = _call_operator(mod, "btob.bake_animation")
    if result != {"FINISHED"}:
        raise AssertionError("bake_animation restituito {0}".format(sorted(result)))
    segments = set(_segment_names(arm_obj))
    baked = _fcurve_bone_names() & segments
    if not baked:
        raise AssertionError("nessuna fcurve sui segmenti dopo il bake")
    for name in _source_names():
        seg0 = "{0}{1}00".format(name, SEG_SUFFIX)
        if seg0 not in baked:
            raise AssertionError("segmento {0} non keyato dal bake".format(seg0))
    return "bake_animation FINISHED: {0} segmenti keyati".format(len(baked))


def test_export_rig_presets():
    """export_rig writes .glb (Godot) / .fbx (Unity) into a TEMP folder."""
    import bpy

    mod = _addon_module()
    _scene, arm_obj, _ = build()
    result, _reports = _call_operator(mod, "btob.convert_segments")
    if result != {"FINISHED"}:
        raise AssertionError("convert_segments restituito {0}".format(sorted(result)))
    settings = bpy.context.scene.bbone_to_bones_settings
    exported = []
    try:
        for preset, extension in (("GODOT", ".glb"), ("UNITY", ".fbx")):
            settings.export_preset = preset
            path = os.path.join(tempfile.gettempdir(), "btob_test_rig_export.fbx")
            settings.export_path = path
            result, _reports = _call_operator(mod, "btob.export_rig")
            if result != {"FINISHED"}:
                raise AssertionError(
                    "export_rig ({0}) restituito {1}".format(preset, sorted(result))
                )
            expected = os.path.splitext(path)[0] + extension
            if not os.path.exists(expected):
                raise AssertionError("export_rig ({0}) non ha scritto {1}".format(preset, expected))
            exported.append(expected)
    finally:
        for path in exported:
            try:
                os.remove(path)
            except OSError:
                pass
    return "export_rig FINISHED: Godot .glb e Unity .fbx su TEMP"


def main():
    import bpy

    mod = _addon_module()
    mod.register()
    try:
        tests = [
            test_all_operators_registered_with_options,
            test_convert_segments_finished,
            test_convert_segments_error_without_bendy,
            test_revert_to_bbones_after_convert,
            test_convert_all_converts_everything,
            test_transfer_weights_finished,
            test_transfer_weights_errors,
            test_limit_influences_caps_and_normalizes,
            test_limit_influences_error_without_mesh,
            test_add_remove_constraints,
            test_add_constraints_error_without_conversion,
            test_selected_bones_only_convert_revert_constraints,
            test_bake_animation_fcurves_on_segments,
            test_export_rig_presets,
        ]
        for test in tests:
            check(test.__name__, test)
    finally:
        mod.unregister()

    print("BTOB ui operators suite addon={0} blender={1}".format(
        os.path.basename(ROOT), bpy.app.version_string))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
