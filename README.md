# BBone to Bones

[![Blender](https://img.shields.io/badge/Blender-4.2%20LTS%2B-blueviolet)](https://www.blender.org)
[![License](https://img.shields.io/badge/License-GPL--3.0--or--later-blue)](LICENSE)
[![XERJ Corpus Hub contributor](https://hub.xerj.org/contributors/PieroFra/badge.svg)](https://hub.xerj.org/contributors/PieroFra)

Converts Blender bendy bones (BBone) into real bone chains, with correct
weights, baked animation and export presets ready for
**Unity**, **Unreal Engine** and **Godot**.

- Target: Blender **4.2 LTS+** (tested on 5.x)
- License: **GPL-3.0-or-later** (Blender Extensions compatible)
- Engine presets: FBX for Unity/UE, glTF for Godot (deform bones only, leaf
  bones handled, per-vertex influence cap)

> Status: **v0.1.0, Phase 0 (setup + deterministic test fixture).**
> The conversion itself lands in Phase 1; see the roadmap in `AGENTS.md`.

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
