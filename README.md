# BBone to Bones

[![Blender](https://img.shields.io/badge/Blender-4.2%20LTS%20%7C%205.x-orange)](https://www.blender.org)
[![License](https://img.shields.io/badge/License-GPL--3.0--or--later-blue)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-22%2F22%20Passing-brightgreen)](tests/run.py)
[![Godot](https://img.shields.io/badge/Godot-4.7.2%20%7C%204.3-478cbf)](tests/run.py)
[![Unity](https://img.shields.io/badge/Unity-6000.6.6f1-black)](tests/run.py)
[![Unreal](https://img.shields.io/badge/Unreal-FBX%20%26%20glTF-0e1128)](tests/run.py)

![BBone to Bones Demo](docs/demo.gif)

Converts Blender Bendy Bones (B-Bones) into standard deforming bone chains with automatic weight transfer, animation baking, and game-engine export presets for **Unity**, **Unreal Engine**, and **Godot**.

## Key Features

1. **Non-destructive `Revert to BBones`** (`btob.revert_to_bbones`): deletes generated segment bones and transfers skin weights back onto the original bendy bones at any time (verified in [`tests/run.py`](tests/run.py)).
2. **Curved joint boundary blending**: blends the last segment endpoint onto the connected child bone's first segment ([`core/weights.py`](core/weights.py)), keeping posed and baked vertex positions within `< 0.001 m` of the source B-Bone deformation (`9.90e-07 m` max delta in [`tests/run.py`](tests/run.py)).
3. **One-click deform-only influence cap** (`btob.limit_influences`): caps per-vertex weights on deform bones only and preserves non-deform vertex groups (`ClothPin`, masks, physics pins) in one click, without having to switch Blender's native `Limit Total` subset to `Pose Bone Deform` manually ([`tests/run.py`](tests/run.py)).
4. **Multi-Action / NLA Bake & Linear Skin (LBS)**:
   - **All Actions** (`bake_all_actions`): bakes and exports every armature Action and NLA strip, with full support for Blender 4.2 Actions and Blender 5.x Slotted Actions ([`core/bake.py`](core/bake.py)).
   - **Linear Skin (LBS)** (`disable_preserve_volume`): turns off Dual Quaternion `Preserve Volume` on Armature modifiers at export so Blender matches the Linear Blend Skinning used by game engines ([`core/export.py`](core/export.py)).
5. **5 Engine Export Presets & `Rigging Suite` Auto-Tab**:
   - Presets: `UNITY` (FBX), `UNITY_GLTF` (`.glb`), `UNREAL` (FBX), `UNREAL_GLTF` (`.glb`), and `GODOT` (`.glb`), exporting deform bones only (`add_leaf_bones=False` by default, `use_connect=False` segment chains).
   - Automatically unifies under the **Rigging Suite** Sidebar tab when installed alongside `CTRL_DEF` or `ACTD` ([`ui/panel.py`](ui/panel.py)).

## Usage (3D Viewport > Sidebar > BBone to Bones / Rigging Suite)

1. **Convert Segments** (`btob.convert_segments`) - replaces each bendy bone with a chain of `<name>_seg_00..XX` deform bones (or only the current selection when **Selected Bones Only** is enabled).
2. **Transfer Weights** (`btob.transfer_weights`) - splits and normalizes skin weights from the bendy bones onto the segment chains with curved joint boundary blending.
3. **Add Follow / Bake Animation** (`btob.add_constraints`, `btob.bake_animation`) - binds segment bones to the B-Bone curve and bakes keyframes across the active Action or **All Actions**.
4. **Export Rig** (`btob.export_rig`) - caps influences, applies **Linear Skin (LBS)**, and exports `.fbx` or `.glb` using the chosen engine preset.

 Or click **Convert All** (`btob.convert_all`) to run steps 1-3 in a single operation, and **Revert to BBones** (`btob.revert_to_bbones`) whenever you want to return to the original B-Bone rig.

## Tested Versions & Engine Verification

- **Blender**: `4.2.23 LTS` and `5.2.3 LTS` on Ubuntu and Windows ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)), plus `5.2.0 LTS` locally.
- **Godot Engine**: `4.7.2-stable` (latest stable) and `4.3-stable` (headless `.glb` import, skeleton, skin, and animation verification).
- **Unity**: `6000.6.6f1` (`-batchmode` `.fbx` prefab, `SkinnedMeshRenderer`, 96 segment bones, and `AnimationClip` verification).
- **Unreal Engine**: `UNREAL` (`.fbx`) and `UNREAL_GLTF` (`.glb`) presets verified via round-trip reimport in [`tests/run.py`](tests/run.py) and FBX/glTF inspection.

## Tests

Run the deterministic headless test suite (builds its own multi-chain B-Bone fixture in memory):

```sh
blender -b -noaudio --python tests/run.py
```

## Packaging & CI

```sh
powershell -NoProfile -ExecutionPolicy Bypass -File .opencode\scripts\package_release.ps1 -OutputDir dist
```

Builds `dist/bbone_to_bones-0.1.0.zip` alongside its `.sha256` checksum and file manifest, and validates clean installation in an isolated Blender profile.
