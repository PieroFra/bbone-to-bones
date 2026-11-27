# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for v0.3.0 features: max_segments, export_copy, manifest audit."""

import os
import sys
import tempfile

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.dirname(ROOT) not in sys.path:
    sys.path.insert(0, os.path.dirname(ROOT))

from bbone_to_bones import core


def _make_test_rig():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm_data = bpy.data.armatures.new("TestArmData")
    arm_obj = bpy.data.objects.new("TestArm", arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    bone = arm_data.edit_bones.new("Bendy")
    bone.head = (0, 0, 0)
    bone.tail = (0, 0, 2)
    bone.bbone_segments = 8
    bone.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")

    mesh_data = bpy.data.meshes.new("TestMeshData")
    mesh_data.from_pydata([(0, 0, 0), (0, 0, 1), (0, 0, 2)], [], [])
    mesh_obj = bpy.data.objects.new("TestMesh", mesh_data)
    bpy.context.scene.collection.objects.link(mesh_obj)
    mod = mesh_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj
    vg = mesh_obj.vertex_groups.new(name="Bendy")
    vg.add([0, 1, 2], 1.0, "REPLACE")
    return arm_obj, mesh_obj


def test_max_segments_and_revert():
    arm_obj, mesh_obj = _make_test_rig()
    report = core.convert_bbones_to_segments(arm_obj, max_segments=4)
    assert len(report["created"]) == 4, f"Expected 4 segments, got {len(report['created'])}"
    w_report = core.transfer_bbone_weights(arm_obj, mesh_objs=[mesh_obj])
    assert len(w_report["segments"]) >= 2, "Expected weights transferred to segments"
    rev = core.revert_segments_to_bbones(arm_obj)
    assert len(rev["removed_segments"]) == 4, "Expected 4 segments removed on revert"
    assert arm_obj.data.bones["Bendy"].use_deform is True
    print("CHECK v030_max_segments PASS")


def test_export_copy_non_destructive():
    arm_obj, mesh_obj = _make_test_rig()
    orig_objs = len(bpy.data.objects)
    orig_bones = len(arm_obj.data.bones)
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "copy_test.glb")
        report = core.export_copy(arm_obj, out_path, preset="GODOT", max_segments=4)
        assert report["non_destructive"] is True
        assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
    assert len(bpy.data.objects) == orig_objs, "Temporary objects leaked!"
    assert len(arm_obj.data.bones) == orig_bones, "Original armature was modified!"
    assert not any("_seg_" in b.name for b in arm_obj.data.bones)
    print("CHECK v030_export_copy PASS")


def test_manifest_audit():
    manifest_path = os.path.join(ROOT, "blender_manifest.toml")
    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'version = "0.3.0"' in content
    for pat in ("/tools/", "/.opencode/", "/_esperimenti/", "/scripts/", "/.goosehints", "/PUBLISHING_PLAN.md"):
        assert pat in content, f"Missing exclude pattern: {pat}"
    print("CHECK v030_manifest_audit PASS")


if __name__ == "__main__":
    test_max_segments_and_revert()
    test_export_copy_non_destructive()
    test_manifest_audit()
    print("ALL v0.3.0 TESTS PASSED")
