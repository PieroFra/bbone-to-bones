# Changelog

All notable changes to BBone to Bones are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-11-05

### Fixed

- Fix NameError nel revert dei segmenti ai bone bendy originali
- Hardening della conversione e di `Revert to BBones` (messaggi d'errore e controlli d'ingresso)

### Changed

- Suite dedicate estese a 7 (revert, segmenti core, pesi/bake, export, operatori UI, meta addon)

## [0.2.0] - 2026-11-04

### Added

- Conversione predefinita delle sole ossa deformanti con `deform_bones_only`
- Opzione `add_live_follow` per i follow constraint immediati
- Refactor modulare: `core/revert.py`, `ui/operator_*`

### Changed

- Umanizzazione della documentazione

## [0.1.1] - 2026-11-04

### Removed

- Rigging suite tab sync and the `Animation` tag, requested by the Blender
  Extensions review, together with the related panel code and tests.

### Changed

- Dropped the remaining internal tooling references and local scratch paths
  from the repository and the packaging script.

### Docs

- Added the GitHub downloads badge and cleaned up the install and packaging sections.

## [0.1.0] - 2026-11-02

### Added

- B-Bone to bone-chain conversion (`btob.convert_segments`, `btob.convert_all`).
- Skin weight transfer with curved joint boundary blending (`btob.transfer_weights`).
- Follow constraints and animation baking, including All Actions and NLA
  (`btob.add_constraints`, `btob.bake_animation`).
- Deform-only influence cap that keeps non-deform vertex groups
  (`btob.limit_influences`).
- Non-destructive revert to B-Bones (`btob.revert_to_bbones`).
- Linear Skin (LBS) switch and five engine export presets: `UNITY`,
  `UNITY_GLTF`, `UNREAL`, `UNREAL_GLTF`, `GODOT` (`btob.export_rig`).
- Headless test suite in `tests/run.py`.
