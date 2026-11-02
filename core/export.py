# SPDX-License-Identifier: GPL-3.0-or-later
"""Export of the converted rig towards the game engines (Fase 4).

Fase 4 of the plan. The chains produced by
:func:`core.segments.convert_bbones_to_segments` carry the skin weights moved
by :func:`core.weights.transfer_bbone_weights` and the baked animation written
by :func:`core.bake.bake_segments_animation`; this module caps the number of
deforming influences per vertex and hands the result to the FBX or glTF
exporter with the flags each engine expects.

Engine presets (``EXPORT_PRESETS``):

- ``UNITY``: FBX, ``-Z`` forward / ``Y`` up, scale in Blender units;
- ``UNREAL``: FBX, the same base flags plus the ``Y``/``X`` bone axes and flat
  shading, which is what the Unreal FBX importer expects;
- ``GODOT``: glTF (``.glb`` single file, ``.gltf`` + sidecar otherwise), with
  deform bones and skins only.

Contract shared with the tests: the exporter only ever sees *deform* bones
(``use_armature_deform_only`` / ``export_def_bones``), so the bbone sources
turned ``use_deform == False`` by the conversion disappear from the exported
file, and ``add_leaf_bones=False`` keeps the ``*_end`` helper bones out of the
hierarchy. Vertex groups that are not deform bones (masks, cloth, pinning) are
read and left untouched by :func:`limit_vertex_influences`.

The operator keywords are filtered against the RNA of the installed operator
(:func:`_filter_operator_kwargs`): Blender 4.2 and 5.x do not expose the same
properties, and a single missing keyword makes the whole export fail.
"""

import bpy

from .weights import find_rigged_meshes

# Presets understood by :func:`build_export_kwargs`.
EXPORT_PRESETS = ("UNITY", "UNREAL", "GODOT", "UNITY_GLTF", "UNREAL_GLTF")

# Most engines deform a vertex with at most four bones.
DEFAULT_MAX_INFLUENCES = 4


def limit_vertex_influences(
    arm_obj,
    mesh_objs=None,
    max_influences=DEFAULT_MAX_INFLUENCES,
    normalize_deform=True,
):
    """Cap the deforming influences of every vertex of the rigged meshes.

    The weights are read in one pass per mesh. For every vertex the weights on
    the *deform* groups (the group names a bone with ``use_deform``) are
    collected; groups that are not deform bones (masks, cloth, pinning) are
    never read into the ranking and never removed.

    When a vertex has more than ``max_influences`` deform groups with a weight
    above ``0.0``, the groups are sorted by decreasing weight, the first
    ``max_influences`` are kept, the exceeding ones are removed, and with
    ``normalize_deform`` the kept weights are scaled so that they sum to
    ``1.0``. Nothing is written until the end: each affected group is rewritten
    in a single pass.

    Returns a report dict with ``armature``, ``meshes``, ``max_influences`` and
    ``capped_vertices`` (vertices that had more than ``max_influences`` deform
    groups).
    """
    max_influences = int(max_influences)
    if max_influences < 1:
        raise ValueError("max_influences must be >= 1 (got {0})".format(max_influences))
    bones = arm_obj.data.bones
    meshes = find_rigged_meshes(arm_obj) if mesh_objs is None else list(mesh_objs)
    report = {
        "armature": arm_obj.name,
        "meshes": [],
        "max_influences": max_influences,
        "capped_vertices": 0,
    }

    for mesh_obj in meshes:
        names_by_index = {group.index: group.name for group in mesh_obj.vertex_groups}
        deform_kinds = {}
        writes = {}
        removals = {}

        for vertex in mesh_obj.data.vertices:
            deform = []
            for element in vertex.groups:
                name = names_by_index.get(element.group)
                if name is None:
                    continue
                is_deform = deform_kinds.get(name)
                if is_deform is None:
                    bone = bones.get(name)
                    is_deform = bone is not None and bool(bone.use_deform)
                    deform_kinds[name] = is_deform
                weight = float(element.weight)
                if not is_deform or weight <= 0.0:
                    continue
                deform.append((name, weight))

            if len(deform) <= max_influences:
                continue

            report["capped_vertices"] += 1
            deform.sort(key=lambda item: item[1], reverse=True)
            kept = deform[:max_influences]
            dropped = deform[max_influences:]
            total = sum(weight for _name, weight in kept)
            factor = 1.0
            if normalize_deform and total > 0.0:
                factor = 1.0 / total
            for name, weight in kept:
                writes.setdefault(name, {})[vertex.index] = weight * factor
            for name, _weight in dropped:
                removals.setdefault(name, []).append(vertex.index)

        for group_name, values in writes.items():
            group = mesh_obj.vertex_groups.get(group_name)
            if group is None:
                continue
            indices = sorted(values)
            group.remove(indices)
            for vertex_index in indices:
                group.add([vertex_index], values[vertex_index], "REPLACE")
        for group_name, indices in removals.items():
            group = mesh_obj.vertex_groups.get(group_name)
            if group is not None and indices:
                group.remove(sorted(indices))

        report["meshes"].append(mesh_obj.name)

    return report


def _filter_operator_kwargs(op_callable, kwargs):
    """Keep only the keyword arguments the operator actually declares.

    ``get_rna_type().properties`` lists the operator properties of the running
    Blender build; the FBX and glTF exporters do not expose the same set on 4.2
    and 5.x, so an unknown keyword is dropped instead of failing the export.
    The fallback keeps every keyword when the RNA cannot be inspected.
    """
    get_rna_type = getattr(op_callable, "get_rna_type", None)
    if get_rna_type is None:
        return dict(kwargs)
    try:
        properties = get_rna_type().properties
    except (AttributeError, TypeError, RuntimeError):
        return dict(kwargs)
    identifiers = {prop.identifier for prop in properties}
    return {key: value for key, value in kwargs.items() if key in identifiers}


def build_export_kwargs(
    preset,
    filepath,
    use_selection=True,
    add_leaf_bones=False,
    max_influences=DEFAULT_MAX_INFLUENCES,
):
    """Return ``(format, kwargs)`` for the exporter of ``preset``.

    ``format`` is ``"FBX"`` or ``"GLTF"``; the keywords are already filtered
    against the operator RNA, so they can be splatted into the call. An unknown
    preset raises ``ValueError``.
    """
    preset = str(preset).upper()
    if preset not in EXPORT_PRESETS:
        raise ValueError(
            "unknown export preset '{0}' (expected one of {1})".format(
                preset, ", ".join(EXPORT_PRESETS)
            )
        )

    if preset in ("UNITY", "UNREAL"):
        kwargs = {
            "filepath": filepath,
            "use_selection": bool(use_selection),
            "object_types": {"ARMATURE", "MESH"},
            "use_armature_deform_only": True,
            "add_leaf_bones": bool(add_leaf_bones),
            "bake_anim": True,
            "bake_anim_use_nla_strips": False,
            "bake_anim_use_all_actions": False,
            "bake_anim_simplify_factor": 0.0,
            "apply_scale_options": "FBX_SCALE_UNITS",
            "axis_forward": "-Z",
            "axis_up": "Y",
        }
        if preset == "UNITY":
            kwargs.update(
                {
                    "primary_bone_axis": "Y",
                    "secondary_bone_axis": "X",
                    "bake_space_transform": False,
                }
            )
        elif preset == "UNREAL":
            kwargs.update(
                {
                    "primary_bone_axis": "Y",
                    "secondary_bone_axis": "X",
                    "mesh_smooth_type": "FACE",
                }
            )
        return "FBX", _filter_operator_kwargs(bpy.ops.export_scene.fbx, kwargs)

    kwargs = {
        "filepath": filepath,
        "export_format": "GLB" if filepath.lower().endswith(".glb") else "GLTF_SEPARATE",
        "use_selection": bool(use_selection),
        "export_def_bones": True,
        "export_skins": True,
        "export_all_influences": False,
        "export_influence_nb": int(max_influences),
        "export_animations": True,
        "export_optimize_animation_size": False,
        "export_yup": True,
    }
    return "GLTF", _filter_operator_kwargs(bpy.ops.export_scene.gltf, kwargs)


def export_rig(
    arm_obj,
    filepath,
    preset="UNITY",
    mesh_objs=None,
    add_leaf_bones=False,
    max_influences=DEFAULT_MAX_INFLUENCES,
):
    """Export ``arm_obj`` and its meshes with the flags of ``preset``.

    The influences are capped first (unless ``max_influences`` is ``None``),
    then the selection and the mode of the scene are saved, only the armature
    and its rigged meshes are selected (armature active), the FBX or glTF
    operator runs, and selection and mode are restored. The scene is left in
    the state it was found in, so the caller can keep working headless.

    Returns a report dict with ``armature``, ``meshes``, ``preset``, ``format``,
    ``filepath``, ``add_leaf_bones``, ``max_influences`` and ``capped_vertices``.
    """
    meshes = find_rigged_meshes(arm_obj) if mesh_objs is None else list(mesh_objs)
    cap_report = None
    if max_influences is not None:
        cap_report = limit_vertex_influences(
            arm_obj, mesh_objs=meshes, max_influences=max_influences
        )
    influence_cap = DEFAULT_MAX_INFLUENCES if max_influences is None else max_influences
    fmt, kwargs = build_export_kwargs(
        preset,
        filepath,
        use_selection=True,
        add_leaf_bones=add_leaf_bones,
        max_influences=influence_cap,
    )

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_mode = arm_obj.mode
    previous_selection = [obj for obj in view_layer.objects if obj.select_get()]
    try:
        if arm_obj.mode != "OBJECT":
            view_layer.objects.active = arm_obj
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in view_layer.objects:
            obj.select_set(False)
        for mesh_obj in meshes:
            mesh_obj.select_set(True)
        arm_obj.select_set(True)
        view_layer.objects.active = arm_obj
        if fmt == "FBX":
            bpy.ops.export_scene.fbx(**kwargs)
        else:
            bpy.ops.export_scene.gltf(**kwargs)
    finally:
        for obj in view_layer.objects:
            obj.select_set(obj in previous_selection)
        view_layer.objects.active = previous_active
        if previous_mode != "OBJECT" and previous_active is not None:
            bpy.ops.object.mode_set(mode=previous_mode)

    return {
        "armature": arm_obj.name,
        "meshes": [mesh_obj.name for mesh_obj in meshes],
        "preset": str(preset).upper(),
        "format": fmt,
        "filepath": filepath,
        "add_leaf_bones": bool(add_leaf_bones),
        "max_influences": max_influences,
        "capped_vertices": 0 if cap_report is None else cap_report["capped_vertices"],
    }
