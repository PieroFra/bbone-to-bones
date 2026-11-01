# SPDX-License-Identifier: GPL-3.0-or-later
"""UI of BBone to Bones: settings, operators and panel of the View3D Sidebar.

Operators stay thin: they validate input, relay messages, and call the core
package. No bpy math here beyond argument plumbing.
"""

from .properties import BBoneToBonesSettings
from .operators import (
    BTOB_OT_add_constraints,
    BTOB_OT_bake_animation,
    BTOB_OT_convert_all,
    BTOB_OT_convert_segments,
    BTOB_OT_export_rig,
    BTOB_OT_limit_influences,
    BTOB_OT_remove_constraints,
    BTOB_OT_transfer_weights,
)
from .panel import VIEW3D_PT_BBoneToBones

# Registration order matters: the PropertyGroup comes first, because the panel
# and the operators read it. The panel is last, it only draws.
CLASSES = (
    BBoneToBonesSettings,
    BTOB_OT_convert_segments,
    BTOB_OT_transfer_weights,
    BTOB_OT_add_constraints,
    BTOB_OT_remove_constraints,
    BTOB_OT_bake_animation,
    BTOB_OT_limit_influences,
    BTOB_OT_export_rig,
    BTOB_OT_convert_all,
    VIEW3D_PT_BBoneToBones,
)

__all__ = [
    "BBoneToBonesSettings",
    "BTOB_OT_convert_segments",
    "BTOB_OT_transfer_weights",
    "BTOB_OT_add_constraints",
    "BTOB_OT_remove_constraints",
    "BTOB_OT_bake_animation",
    "BTOB_OT_limit_influences",
    "BTOB_OT_export_rig",
    "BTOB_OT_convert_all",
    "VIEW3D_PT_BBoneToBones",
    "CLASSES",
]
