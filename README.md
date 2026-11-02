# BBone to Bones

Convert B-Bone (bendy bone) deformation into standard bone weights, so game-ready rigs
export cleanly while staying fully editable and non-destructive in Blender.

## Key Features

### Non-destructive `Revert to BBones`
`btob.revert_to_bbones` restores the original B-Bone setup at any time — verified in
`do_fase5_ui_operators` of [`tests/run.py`](tests/run.py).

### Curved joint boundary blending
`_next_chain_segment_group` in [`core/weights.py`](core/weights.py) blends weights across
curved joint boundaries: pose/bake error `< 0.001 m` (max delta `9.90e-07 m`), verified in
`do_fase2_pose_equivalence` and `do_fase3_bake_30_frames` of [`tests/run.py`](tests/run.py)
and visible in [`docs/demo.gif`](docs/demo.gif).

### One-click deform-only influence cap
`btob.limit_influences` caps influences on deform bones only and preserves non-deform
groups such as `ClothPin` and masks in a single click — no manual selection of the
`Pose Bone Deform` subset required by the native operator. Verified in
`do_fase4_influence_limit` of [`tests/run.py`](tests/run.py).

### 5 Engine Presets (`UNITY`, `UNITY_GLTF`, `UNREAL`, `UNREAL_GLTF`, `GODOT`) & `Rigging Suite` Auto-Tab
Exports `.fbx` and `.glb`, and automatically unifies into the **Rigging Suite** tab
whenever `CTRL_DEF` or `ACTD` are active.

## Tested Versions & Engine Verification

- **Blender**: `4.2.23 LTS` and `5.2.3 LTS` (Ubuntu and Windows in
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml)), plus `5.2.0 LTS` locally.
- **Godot Engine**: `4.7.2-stable` (latest stable) and `4.3-stable` (headless `.glb`
  import via `godot_import_check.py`).
- **Unity**: `6000.6.6f1` (batchmode `.fbx` import via `unity_import_check.py`).
- **Unreal Engine**: `UNREAL` (`.fbx`) and `UNREAL_GLTF` (`.glb`) presets verified through
  a real round-trip reimport in [`tests/run.py`](tests/run.py)
  (`do_fase4_export_reimport`) and FBX/glTF inspection.
