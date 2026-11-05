# -*- coding: utf-8 -*-
"""Headless test suite dedicated to core/export.py (Fase 4).

Companion of ``tests/run.py``: it rebuilds the same in-memory fixture
(``make_fixture.build``) and covers every public function of
``core.export``: ``EXPORT_PRESETS`` / ``DEFAULT_MAX_INFLUENCES`` constants,
``build_export_kwargs`` (preset flags, user overrides, path handling),
``disable_preserve_volume``, ``limit_vertex_influences`` and the validation
smoke-test of ``export_rig``. It never imports ``tests/run.py`` (that module
executes its own runner on import) and never touches the add-on code.

Usage:
    blender -b --python tests/test_core_export_suite.py

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


def _armature_modifier(mesh_obj, arm_obj):
    """The ARMATURE modifier of ``mesh_obj`` pointing at ``arm_obj``."""
    for mod in mesh_obj.modifiers:
        if mod.type == "ARMATURE" and mod.object == arm_obj:
            return mod
    raise AssertionError("{0}: no armature modifier for {1}".format(mesh_obj.name, arm_obj.name))


def test_export_constants():
    """DEFAULT_MAX_INFLUENCES and EXPORT_PRESETS expected keys."""
    core = _core()
    if core.DEFAULT_MAX_INFLUENCES != 4:
        raise AssertionError(
            "DEFAULT_MAX_INFLUENCES {0} != 4".format(core.DEFAULT_MAX_INFLUENCES)
        )
    required = {"UNITY", "UNREAL", "GODOT"}
    missing = sorted(required - set(core.EXPORT_PRESETS))
    if missing:
        raise AssertionError("EXPORT_PRESETS missing {0}".format(missing))
    if not set(core.EXPORT_PRESETS).issubset(
        {"UNITY", "UNREAL", "GODOT", "UNITY_GLTF", "UNREAL_GLTF"}
    ):
        raise AssertionError("unexpected EXPORT_PRESETS keys: {0}".format(core.EXPORT_PRESETS))
    return "constants: max_influences={0}, presets={1}".format(
        core.DEFAULT_MAX_INFLUENCES, ", ".join(core.EXPORT_PRESETS)
    )


def test_export_preset_formats():
    """Format per preset: FBX for Unity/UE, GLTF for Godot and the GLTF twins."""
    core = _core()
    cases = {
        "UNITY": "FBX",
        "UNREAL": "FBX",
        "GODOT": "GLTF",
        "UNITY_GLTF": "GLTF",
        "UNREAL_GLTF": "GLTF",
    }
    for preset, expected_fmt in cases.items():
        fmt, kwargs = core.build_export_kwargs(preset, "out.fbx")
        if fmt != expected_fmt:
            raise AssertionError(
                "{0} format {1} != {2}".format(preset, fmt, expected_fmt)
            )
        if kwargs["filepath"] != "out.fbx":
            raise AssertionError("{0} filepath changed to {1}".format(preset, kwargs["filepath"]))
    return "formats: " + ", ".join("{0}={1}".format(k, v) for k, v in cases.items())


def test_export_unity_kwargs():
    """Unity preset: FBX defaults, -Z forward / Y up, Y/X bone axes."""
    core = _core()
    _fmt, kwargs = core.build_export_kwargs("UNITY", "rig.fbx")
    expected = {
        "filepath": "rig.fbx",
        "object_types": {"ARMATURE", "MESH"},
        "use_armature_deform_only": True,
        "add_leaf_bones": False,
        "bake_anim": True,
        "bake_anim_simplify_factor": 0.0,
        "apply_scale_options": "FBX_SCALE_UNITS",
        "axis_forward": "-Z",
        "axis_up": "Y",
        "primary_bone_axis": "Y",
        "secondary_bone_axis": "X",
        "bake_space_transform": False,
    }
    for key, value in expected.items():
        if kwargs.get(key) != value:
            raise AssertionError("UNITY {0}={1} != {2}".format(key, kwargs.get(key), value))
    return "UNITY kwargs OK"


def test_export_unreal_kwargs():
    """Unreal preset: FBX base flags plus FACE smooth type."""
    core = _core()
    fmt, kwargs = core.build_export_kwargs("UNREAL", "rig.fbx")
    if fmt != "FBX":
        raise AssertionError("UNREAL format {0} != FBX".format(fmt))
    if kwargs.get("mesh_smooth_type") != "FACE":
        raise AssertionError("UNREAL mesh_smooth_type {0} != FACE".format(kwargs.get("mesh_smooth_type")))
    if kwargs.get("axis_forward") != "-Z" or kwargs.get("axis_up") != "Y":
        raise AssertionError("UNREAL axes wrong: {0}/{1}".format(kwargs.get("axis_forward"), kwargs.get("axis_up")))
    if kwargs.get("primary_bone_axis") != "Y" or kwargs.get("secondary_bone_axis") != "X":
        raise AssertionError("UNREAL bone axes wrong")
    return "UNREAL kwargs OK"


def test_export_godot_kwargs():
    """Godot preset: glTF, deform bones, influences cap, GLB vs separate."""
    core = _core()
    fmt, kwargs = core.build_export_kwargs("GODOT", "rig.glb")
    if fmt != "GLTF":
        raise AssertionError("GODOT format {0} != GLTF".format(fmt))
    if kwargs.get("export_format") != "GLB":
        raise AssertionError("GODOT .glb export_format {0} != GLB".format(kwargs.get("export_format")))
    for key in ("export_def_bones", "export_skins", "export_yup"):
        if kwargs.get(key) is not True:
            raise AssertionError("GODOT {0}={1} != True".format(key, kwargs.get(key)))
    if kwargs.get("export_all_influences") is not False:
        raise AssertionError("GODOT export_all_influences must be False")
    if kwargs.get("export_influence_nb") != core.DEFAULT_MAX_INFLUENCES:
        raise AssertionError(
            "GODOT export_influence_nb {0} != {1}".format(
                kwargs.get("export_influence_nb"), core.DEFAULT_MAX_INFLUENCES
            )
        )
    # A hand-written path with another extension keeps the preset format: the
    # glTF exporter falls back to separate files instead of trusting .fbx.
    fmt, kwargs = core.build_export_kwargs("GODOT", "rig.fbx")
    if kwargs.get("export_format") != "GLTF_SEPARATE":
        raise AssertionError("GODOT non-glb export_format {0} != GLTF_SEPARATE".format(kwargs.get("export_format")))
    return "GODOT kwargs OK"


def test_export_user_overrides():
    """User overrides reach the right keyword for both exporters."""
    core = _core()
    _fmt, kwargs = core.build_export_kwargs(
        "GODOT", "rig.glb", max_influences=2, export_all_actions=True
    )
    if kwargs.get("export_influence_nb") != 2:
        raise AssertionError("GODOT override influence_nb {0} != 2".format(kwargs.get("export_influence_nb")))
    if kwargs.get("export_animation_mode") != "ACTIONS":
        raise AssertionError("GODOT override animation mode {0} != ACTIONS".format(kwargs.get("export_animation_mode")))
    _fmt, kwargs = core.build_export_kwargs(
        "UNITY", "rig.fbx", use_selection=False, add_leaf_bones=True, export_all_actions=True
    )
    if kwargs.get("use_selection") is not False:
        raise AssertionError("UNITY use_selection override lost")
    if kwargs.get("add_leaf_bones") is not True:
        raise AssertionError("UNITY add_leaf_bones override lost")
    if kwargs.get("bake_anim_use_all_actions") is not True:
        raise AssertionError("UNITY export_all_actions override lost")
    return "overrides OK"


def test_export_handwritten_paths_kept():
    """Paths typed by hand with other extensions are never rewritten."""
    core = _core()
    for preset, path in (("UNITY", "out.glb"), ("UNREAL", "out.gltf"), ("GODOT", "out.abc")):
        _fmt, kwargs = core.build_export_kwargs(preset, path)
        if kwargs["filepath"] != path:
            raise AssertionError("{0}: filepath {1} != {2}".format(preset, kwargs["filepath"], path))
    _fmt, kwargs = core.build_export_kwargs("GODOT", "hand.glb")
    if kwargs["filepath"] != "hand.glb" or kwargs["export_format"] != "GLB":
        raise AssertionError("GODOT hand-written .glb lost")
    return "hand-written paths intact"


def test_export_unknown_preset():
    """An unknown preset raises a clean ValueError."""
    core = _core()
    try:
        core.build_export_kwargs("STEAM", "out.fbx")
    except ValueError:
        return "unknown preset raises ValueError"
    raise AssertionError("unknown preset must raise ValueError")


def test_disable_preserve_volume():
    """Armature modifiers switch off Dual Quaternion; already-off is not reported."""
    core = _core()
    _scene, arm_obj, meshes = build()
    mesh = meshes[0]
    mod = _armature_modifier(mesh, arm_obj)
    mod.use_deform_preserve_volume = True
    changed = core.disable_preserve_volume(arm_obj, mesh_objs=[mesh])
    if changed != [mesh.name]:
        raise AssertionError("changed {0} != [{1}]".format(changed, mesh.name))
    if mod.use_deform_preserve_volume:
        raise AssertionError("preserve_volume still True after disable")
    if core.disable_preserve_volume(arm_obj, mesh_objs=[mesh]) != []:
        raise AssertionError("already-off modifier reported again")
    return "preserve_volume disabled on {0}".format(mesh.name)


def test_limit_vertex_influences_caps_and_normalizes():
    """Six deform groups per vertex are capped to four and renormalised to 1.0."""
    core = _core()
    _scene, arm_obj, meshes = build()
    mesh = meshes[0]
    bone_names = [
        "BendyA.000", "BendyA.001", "BendyA.002",
        "BendyA.003", "BendyB.000", "BendyB.001",
    ]
    weights = [0.30, 0.25, 0.20, 0.15, 0.07, 0.03]
    groups = {}
    for name in bone_names:
        existing = mesh.vertex_groups.get(name)
        groups[name] = existing if existing is not None else mesh.vertex_groups.new(name=name)
    total = len(mesh.data.vertices)
    for v in range(total):
        for name, weight in zip(bone_names, weights):
            groups[name].add([v], weight, "REPLACE")

    report = core.limit_vertex_influences(arm_obj, mesh_objs=[mesh], max_influences=4)
    if report["capped_vertices"] != total:
        raise AssertionError("capped {0} != {1}".format(report["capped_vertices"], total))
    if report["meshes"] != [mesh.name]:
        raise AssertionError("meshes {0} != [{1}]".format(report["meshes"], mesh.name))
    for v in mesh.data.vertices:
        deform = [
            (element.group, element.weight)
            for element in v.groups
            if mesh.vertex_groups[element.group].name in bone_names
        ]
        if len(deform) > 4:
            raise AssertionError("vertex {0} still has {1} deform groups".format(v.index, len(deform)))
        total_weight = sum(weight for _g, weight in deform)
        if abs(total_weight - 1.0) > 1e-4:
            raise AssertionError(
                "vertex {0} total {1:.6f} != 1.0".format(v.index, total_weight)
            )
    return "capped {0} vertices to 4 influences, normalized".format(total)


def test_limit_vertex_influences_mesh_without_groups():
    """A mesh with no vertex groups is returned untouched, no failure."""
    import bpy

    core = _core()
    _scene, arm_obj, _ = build()
    data = bpy.data.meshes.new("NoGroupsMesh")
    data.vertices.add(8)
    obj = bpy.data.objects.new("NoGroupsObj", data)
    _scene.collection.objects.link(obj)
    report = core.limit_vertex_influences(arm_obj, mesh_objs=[obj], max_influences=4)
    if report["capped_vertices"] != 0:
        raise AssertionError("capped {0} != 0".format(report["capped_vertices"]))
    if report["meshes"] != [obj.name]:
        raise AssertionError("meshes {0} != [{1}]".format(report["meshes"], obj.name))
    if len(obj.vertex_groups) != 0:
        raise AssertionError("vertex groups appeared on an empty mesh")
    return "mesh without groups OK"


def test_export_rig_validation_smoke():
    """export_rig rejects a missing armature with a clean error; no file is written."""
    core = _core()
    _scene, arm_obj, meshes = build()
    tmp = os.path.join(tempfile.gettempdir(), "btob_never_written.fbx")
    if os.path.exists(tmp):
        os.remove(tmp)
    # A non-armature object as ``arm_obj``: clean AttributeError, no export.
    try:
        core.export_rig(meshes[0], tmp)
    except (AttributeError, TypeError, ValueError):
        pass
    else:
        raise AssertionError("export_rig with a mesh as armature must raise")
    if os.path.exists(tmp):
        os.remove(tmp)
        raise AssertionError("export_rig wrote a file during the validation smoke test")
    # ``None`` armature also raises a clean error.
    try:
        core.export_rig(None, tmp)
    except (AttributeError, TypeError, ValueError):
        pass
    else:
        raise AssertionError("export_rig(None, ...) must raise")
    return "validation smoke: missing armature raises clean error, no file written"


def main():
    import bpy

    tests = [
        test_export_constants,
        test_export_preset_formats,
        test_export_unity_kwargs,
        test_export_unreal_kwargs,
        test_export_godot_kwargs,
        test_export_user_overrides,
        test_export_handwritten_paths_kept,
        test_export_unknown_preset,
        test_disable_preserve_volume,
        test_limit_vertex_influences_caps_and_normalizes,
        test_limit_vertex_influences_mesh_without_groups,
        test_export_rig_validation_smoke,
    ]
    for test in tests:
        check(test.__name__, test)

    print("BTOB export suite addon={0} blender={1}".format(os.path.basename(ROOT), bpy.app.version_string))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
