# SPDX-License-Identifier: GPL-3.0-or-later
"""UI of BBone to Bones: panels and operators for the View3D Sidebar.

Operators stay thin: they validate input, relay messages, and call the core
package. No bpy math here beyond argument plumbing.
"""

import bpy


class VIEW3D_PT_BBoneToBones(bpy.types.Panel):
    """Sidebar panel under the 'BBone to Bones' tab."""

    bl_label = "BBone to Bones"
    bl_idname = "VIEW3D_PT_BBoneToBones"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BBone to Bones"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Conversion not implemented yet (Fase 1).")
        layout.label(text="v0.1.0 - Phase 0: setup and tests only.")
