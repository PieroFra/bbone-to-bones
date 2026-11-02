# SPDX-License-Identifier: GPL-3.0-or-later
"""BBone to Bones: converts bendy bones into real bone chains, with weights and
an export-ready rig for Unity / Unreal / Godot.

GLP v3+ (see LICENSE). Target: Blender 4.2 LTS and 5.x.

Package layout:
- core/  pure logic, no UI, headless-safe (covered by tests/run.py).
- ui/    panels and operators; thin wrappers over core.
"""

bl_info = {
    "name": "BBone to Bones",
    "author": "Piero Fra",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > BBone to Bones",
    "description": "Converts bendy bones into real bone chains, with weights, "
    "bake and export presets for Unity / Unreal / Godot",
    "doc_url": "",
    "support": "COMMUNITY",
    "category": "Rigging",
}


def _ui_module():
    """Import the UI module lazily so core stays importable headless."""
    from . import ui

    return ui


CLASSES = ()

SETTINGS_NAME = "bbone_to_bones_settings"


def _collect_classes():
    """Collect registrable classes from ui/. core/ holds logic only."""
    global CLASSES
    ui = _ui_module()
    CLASSES = tuple(ui.CLASSES)


def register():
    if not CLASSES:
        _collect_classes()
    for cls in CLASSES:
        try:
            bpy_classes_register(cls)
        except Exception:
            if not getattr(cls, "is_registered", False):
                raise
    # Idempotent register(): safe under double registration.
    _register_settings()
    # Companion add-ons may already be up: align the tabs of the suite.
    _ui_module().sync_rigging_suite_tabs(unregistering=False)


def unregister():
    # The Scene pointer must go before the PropertyGroup class it points at.
    _ui_module().sync_rigging_suite_tabs(unregistering=True)
    _unregister_settings()
    for cls in reversed(CLASSES):
        try:
            bpy_classes_unregister(cls)
        except Exception:
            if getattr(cls, "is_registered", False):
                raise


def _register_settings():
    """Attach the PropertyGroup to Scene once, even under double register()."""
    import bpy

    if getattr(bpy.types.Scene, SETTINGS_NAME, None) is not None:
        return
    ui = _ui_module()
    setattr(
        bpy.types.Scene,
        SETTINGS_NAME,
        bpy.props.PointerProperty(type=ui.BBoneToBonesSettings),
    )


def _unregister_settings():
    """Detach the PropertyGroup from Scene; safe when it is already gone."""
    import bpy

    if getattr(bpy.types.Scene, SETTINGS_NAME, None) is None:
        return
    delattr(bpy.types.Scene, SETTINGS_NAME)


def bpy_classes_register(cls):
    import bpy

    bpy.utils.register_class(cls)


def bpy_classes_unregister(cls):
    import bpy

    bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
