# BBone to Bones

[![Blender](https://img.shields.io/badge/Blender-4.2%20LTS%2B-blueviolet)](https://www.blender.org)
[![License](https://img.shields.io/badge/License-GPL--3.0--or--later-blue)](LICENSE)
[![XERJ Corpus Hub contributor](https://hub.xerj.org/contributors/PieroFra/badge.svg)](https://hub.xerj.org/contributors/PieroFra)

Converts Blender bendy bones (BBone) into real bone chains, with correct
weights, baked animation and export presets ready for
**Unity**, **Unreal Engine** and **Godot**.

![BBone to Bones Demo](docs/demo.gif)

- Target: Blender **4.2 LTS+** (tested on 5.x)
- License: **GPL-3.0-or-later** (Blender Extensions compatible)
- Engine presets: FBX for Unity/UE, glTF for Godot (deform bones only, leaf
  bones handled, per-vertex influence cap)

> Status: **v0.1.0, Phase 5 complete (UI in the 3D Viewport Sidebar: status
> readout, one operator per step with undo support, one-click "Convert All"
> pipeline, clear error messages and progress feedback on heavy rigs)**; see
> the roadmap in `AGENTS.md`.
>
> Note: generated segment bones are parented in chain with use_connect=False
> (in Edit Mode they are moved individually; in Pose Mode they follow parent
> transforms normally and support location keyframes for baking).

## Usage (3D Viewport > Sidebar > BBone to Bones)

Select an armature with bendy bones, then run the four steps of the pipeline:

1. **Convert Segments** (`btob.convert_segments`) - replaces each bendy bone
   with its real bone chain (parenting preserved).
2. **Transfer Weights** (`btob.transfer_weights`) - moves the skin weights
   from the source bones to the matching segments.
3. **Add Follow** / **Bake Animation** (`btob.add_constraints`,
   `btob.bake_animation`) - optional follow constraints, then baking the
   motion over the chosen frame range and removing the constraints.
4. **Export Rig** (`btob.export_rig`) - writes the FBX/glTF file with the
   engine preset chosen in the panel (Unity/UE via FBX, Godot via glTF).

Alternatively press **Convert All** (`btob.convert_all`) to run segments +
weights + bake in one click on the active armature.

## Tests

Headless and deterministic (the fixture is built in memory, no binary needed):

```sh
blender -b -noaudio --python tests/run.py
```

The last stdout line is the verdict:
`RISULTATO passati=X falliti=Y totale=N`.

## Development

No binary test asset is committed: `tests/make_fixture.py` builds the fixture
(3 bbone chains with bend/roll/scale variety, 2 meshes including the
"object name differs from mesh data name" trap and a non-identical
transform, 30-frame animation) from scratch every run.
