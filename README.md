# BBone to Bones

![License](https://img.shields.io/badge/license-MIT-green) ![Blender](https://img.shields.io/badge/Blender-4.2%20%7C%205.x-orange) ![Tests](https://img.shields.io/badge/tests-22%2F22-brightgreen) ![Godot](https://img.shields.io/badge/Godot-4.7.2-blue) ![Unity](https://img.shields.io/badge/Unity-6000.6.6f1-black) ![Unreal](https://img.shields.io/badge/Unreal-round--trip-9cf)

![BBone to Bones Demo](docs/demo.gif)

Convert BBone (Bendy Bone) deform rig segments into real bones with fully automatic weight transfer, follow animation baking and game engine exports. Non-destructive: the original BBone rig stays untouched and you can always revert.

## Key Features

1. **Non-destructive `Revert to BBones`** (`btob.revert_to_bbones`): restore the original BBone rig at any time after conversion, verified in `do_fase5_ui_operators` of [`tests/run.py`](tests/run.py).
2. **Curved joint boundary blending** (`_next_chain_segment_group` in [`core/weights.py`](core/weights.py)): curved joints blend vertex weights across segment boundaries exactly like the original BBone deforms, pose/bake error `< 0.001 m` (max delta `9.90e-07 m`), verified in `do_fase2_pose_equivalence` and `do_fase3_bake_30_frames` of [`tests/run.py`](tests/run.py).
3. **One-click deform-only influence cap** (`btob.limit_influences`): limits influences on deform bones only and preserves non-deform groups like `ClothPin` and masks in one click, without having to switch the native operator subset to `Pose Bone Deform` manually, verified in `do_fase4_influence_limit` of [`tests/run.py`](tests/run.py).
4. **Multi-Action / NLA Bake & Slotted Actions (Blender 4.2 / 5.x)**: `bake_all_actions` / the `All Actions` checkbox bakes every NLA track and strip into slotted Actions compatible with both Blender 4.2 and 5.x. Plus **Linear Skin (LBS)** (`disable_preserve_volume`): disables Dual Quaternion `Preserve Volume` on Armature modifiers at export to match game engines.
5. **5 Engine Presets (`UNITY`, `UNITY_GLTF`, `UNREAL`, `UNREAL_GLTF`, `GODOT`) & `Rigging Suite` Auto-Tab**: exports `.fbx` and `.glb` (deform bones only, `add_leaf_bones=False` by default, `use_connect=False` segment chains) and automatically unifies under the **Rigging Suite** Sidebar tab when `CTRL_DEF` or `ACTD` are active.

## Usage (3D Viewport > Sidebar > BBone to Bones / Rigging Suite)

1. **Convert Segments**: turn each BBone segment chain into real bones (optionally limited to the current selection with `Selected Bones Only`).
2. **Transfer Weights**: copy vertex weights from the BBone rig to the new bones with curved joint boundary blending.
3. **Add Follow / Bake Animation**: recreate BBone follow behavior or bake animation, either the current Action only or every NLA Action with `All Actions`.
4. **Export Rig**: pick one of the 5 engine presets and export.

Additional controls:

- `Convert All`: convert every eligible BBone chain in the armature at once.
- `Selected Bones Only`: restrict conversion to the selected bones.
- `All Actions`: bake all Actions/NLA strips instead of the current one (Multi-Action / Slotted Actions).
- `Linear Skin (LBS)`: force Linear Blend Skinning on export by disabling Dual Quaternion `Preserve Volume`.
- `Revert to BBones`: non-destructive rollback to the original BBone rig.

## Tested Versions & Engine Verification

- **Blender**: `4.2.23 LTS` and `5.2.3 LTS` on Ubuntu & Windows ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)), plus `5.2.0 LTS` locally.
- **Godot Engine**: `4.7.2-stable` (latest stable) and `4.3-stable` (headless `.glb` import, skeleton/skin/animation verification).
- **Unity**: `6000.6.6f1` (`-batchmode` `.fbx` prefab, `SkinnedMeshRenderer`, 96 segment bones and `AnimationClip` verification).
- **Unreal Engine**: `UNREAL` (`.fbx`) and `UNREAL_GLTF` (`.glb`) presets verified via round-trip reimport in [`tests/run.py`](tests/run.py) (`do_fase4_export_reimport`) and FBX/glTF inspection.

## Tests

```bash
blender -b -noaudio --python tests/run.py
```

Output: `RISULTATO passati=22 falliti=0 totale=22`

## Packaging & CI

`package_release.ps1` builds the distributable zip:

```text
PACKAGE versione=0.1.0 file=13 py=10 docs=3
```
