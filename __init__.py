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


def _collect_classes():
    """Collect registrable classes from ui/. core/ holds logic only."""
    global CLASSES
    ui = _ui_module()
    classes = []
    for name in dir(ui):
        obj = getattr(ui, name)
        if isinstance(obj, type) and issubclass(obj, bpy_types_super()):
            classes.append(obj)
    if not classes:
        raise RuntimeError("BBone to Bones: no registrable classes found in ui/")
    CLASSES = tuple(classes)


def bpy_types_super():
    import bpy

    return bpy.types.Panel


def register():
    if not CLASSES:
        _collect_classes()
    for cls in CLASSES:
        try:
            bpy_classes_register(cls)
        except Exception:
            if not cls.is_registered():
                raise
    # Idempotent register(): safe under double registration.


def unregister():
    for cls in reversed(CLASSES):
        try:
            bpy_classes_unregister(cls)
        except Exception:
            if cls.is_registered():
                raise


def bpy_classes_register(cls):
    import bpy

    bpy.utils.register_class(cls)


def bpy_classes_unregister(cls):
    import bpy

    bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
