# SPDX-License-Identifier: GPL-3.0-or-later
"""Core logic of BBone to Bones: bendy-bone analysis and chain conversion.

This package must stay UI-free. Everything here runs headless (Blender
--background) and is covered by tests/run.py. UI operators in ui/ call into
this code; they must never implement math themselves.
"""

# Single source of truth for the package version (mirrors blender_manifest.toml
# and bl_info in ../__init__.py; keep all three in sync on every release).
VERSION = (0, 1, 0)

# Tolerances used by the numeric contract between the conversion and its tests.
HEAD_MATCH_TOLERANCE = 1e-5  # Fase 1: segment heads on the bbone curve.
POSE_MATCH_MAX_ERROR = 0.001  # Fase 2/3: max 1 mm between posed meshes.

# Public Fase 1 API: bendy bones -> chains of regular bones.
from .segments import (  # noqa: E402  (after the shared constants on purpose)
    collect_segment_specs,
    convert_bbones_to_segments,
    is_convertible_bone,
    revert_segments_to_bbones,
    segment_bone_name,
)

# Public Fase 2 API: skin weights of the bbones -> converted segment bones.
from .weights import (  # noqa: E402  (same reason: keep constants first)
    find_rigged_meshes,
    pose_segments_from_bbones,
    split_bbone_weight,
    transfer_bbone_weights,
    vertex_coords_in_armature_space,
)

# Public Fase 3 API: bbone animation -> keyframes on the segment bones.
from .bake import (  # noqa: E402  (same reason: keep constants first)
    CONSTRAINT_NAME,
    add_bbone_follow_constraints,
    assign_armature_action,
    bake_segments_animation,
    collect_armature_actions,
    remove_bbone_follow_constraints,
    select_only_segment_bones,
)

# Public Fase 4 API: influence cap + FBX/glTF export of the converted rig.
from .export import (  # noqa: E402  (same reason: keep constants first)
    DEFAULT_MAX_INFLUENCES,
    EXPORT_PRESETS,
    build_export_kwargs,
    disable_preserve_volume,
    export_rig,
    limit_vertex_influences,
)
