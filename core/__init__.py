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
