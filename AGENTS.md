# AGENTS.md - BBone to Bones

Regole operative per gli agenti. È l'unica fonte di verità sul progetto: se un
altro documento dice il contrario, vale questo.

---

## 0. Dove siamo

- Workspace: `C:\Users\checc\Desktop\BLENDER ADDONS\` (**una cartella per addon**).
- Progetto: `C:\Users\checc\Desktop\BLENDER ADDONS\bbone_to_bones\`
- Fino a prova contraria non esiste backup Drive per questo progetto.

---

## 1. Il piano in 7 fasi (una fase per sessione, test prima del codice)

| Fase | Contenuto | Rete di sicurezza (test in `tests/run.py`) |
|---|---|---|
| 0 | Setup: manifest Extensions, `core/` senza UI, `ui/`, fixture deterministica | fixture valida (catene, mesh, trap naming, 30 frame) |
| 1 | Catena di segmenti da bbone: UN solo cambio di modalità, posizioni/roll da `bbone_segment_matrix(rest=True)`, segmenti parentati in catena con `use_connect=False` (non connessi: in Edit Mode vanno spostati singolarmente, in Pose Mode si comportano normalmente e accettano keyframe di traslazione per il bake), primo segmento parentato al parent originale, figli dell'originale riparentati all'ultimo segmento, naming `_seg_00`, `use_deform` flip | teste dei segmenti sulla curva bbone (toll. `core.HEAD_MATCH_TOLERANCE`) |
| 2 | Pesi: `matrix_world` per ogni mesh collegata, spazio giusto per `bbone_segment_index`, dict accumulato e scritto una volta, normalizzazione sui soli deform group | confronto vertici in posa pre/post conversione, errore < `core.POSE_MATCH_MAX_ERROR` |
| 3 | Constraint opzionali + bake (`bpy.ops.nla.bake`, visual keying, solo segmenti) poi rimozione constraint | stesso confronto su tutti i 30 frame della fixture |
| 4 | Export: preset FBX (Unity/UE) e glTF (Godot), solo deform bone, leaf bone, limite influenze/vertice | reimport dell'export e confronto in Blender |
| 5 | UI: pannello, un operatore per volta, undo, messaggi chiari, progresso su rig grossi | smoke UI + probe |
| 6 | Pubblicazione: Blender Extensions (gratuita) ed eventualmente Superhive | packaging + gate G3 vergine |

**Fatti dell'API da usare (Fasi 1-2)**: `PoseBone.bbone_segment_matrix(rest=True)`,
`bbone_segment_index` (piano vertice→segmento, verificare lo spazio atteso con
un test dedicato). Link API:
- https://docs.blender.org/api/current/bpy.types.PoseBone.html
- https://docs.blender.org/api/current/bpy.types.Bone.html

**Vincolo GPL**: il set di conversioni esistente (GPL) NON viene mai letto,
incollato o adattato. I suoi difetti diventano requisiti da non ripetere
(vedi §4). Il codice, commenti e docstring sono in **inglese**; documentazione
 `.md` in italiano.

---

## 2. Com'è fatto il codice

| Area | File | Stato |
|---|---|---|
| ingresso | `__init__.py` | bl_info, CLASSES (lazy da ui/), register idempotente |
| dati | `core/__init__.py` | VERSION + tolleranze condivise |
| conversione | `core/segments.py` | Fasi 1: catena di segmenti da bbone + revert ai BBone (`revert_segments_to_bbones`) |
| revert | `core/revert.py` | logica di revert dei segmenti ai bone bendy originali (usata da `btob.revert_to_bbones`) |
| pesi | `core/weights.py` | Fase 2: trasferimento pesi ai segmenti |
| bake | `core/bake.py` | Fase 3: constraint/bake su 30 frame |
| export | `core/export.py` | Fase 4: export FBX Unity/UE e glTF Godot, limite influenze e reimport |
| UI | `ui/properties.py`, `ui/operators.py`, `ui/panel.py`, `ui/__init__.py` | impostazioni scena, operatori `btob.*`, pannello Sidebar "BBone to Bones", CLASSES UI |
| UI operatori | `ui/operator_convert.py`, `ui/operator_weights.py`, `ui/operator_follow.py`, `ui/operator_export.py`, `ui/operator_common.py` | implementazione degli operatori `btob.*` per area (conversione, pesi, bake/follow, export, utilità) |
| test | `tests/make_fixture.py`, `tests/run.py` | fixture deterministica + runner headless |

Package flat per il formato Extensions: `blender_manifest.toml` è il contratto
di packaging (`id=bbone_to_bones`, GPL-3.0-or-later, min Blender 4.2).

Gli operatori `btob.*` includono anche **Revert to BBones**
(`btob.revert_to_bbones`, operatore UI `ui/operators.py`, logica in
`core/segments.py:revert_segments_to_bbones`): elimina i segmenti convertiti
e restituisce i pesi di skin ai bone bendy originali. Il preset engine
(`Unity/Unreal/Godot`) cambia automaticamente l'estensione del percorso di
export tra `.fbx` e `.glb` (`ui/properties.py:PRESET_EXTENSIONS`); i percorsi
scritti a mano con altre estensioni restano intatti. La checkbox
**Selected Bones Only** (`selected_bones_only`, `ui/properties.py`) limita
ogni passaggio (segmenti, pesi, bake, export) ai soli bone bendy selezionati
in Pose o Object mode.

---

## 3. Verifica

Eseguire i comandi **dalla radice del progetto**.

| Cosa | Comando |
|---|---|
| test | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/run.py` |
| suite revert | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/test_revert_suite.py` |
| suite segmenti/revert core | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/test_core_segments_revert_suite.py` |
| suite pesi/bake core | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/test_core_weights_bake_suite.py` |
| suite export core | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/test_core_export_suite.py` |
| suite operatori UI | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/test_ui_operators_suite.py` |
| suite meta addon | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/test_addon_meta_suite.py` |
| fixture su file | `& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -noaudio --python tests/make_fixture.py -- save` |
| packaging | `.\.opencode\scripts\package_release.ps1 -OutputDir dist` |
| engine (Godot 4.3) | & 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' "$env:USERPROFILE\.config\opencode\scripts\godot_import_check.py" "$env:TEMP\opencode\btob_gui\demo_export.glb" --min-bones 96 --min-meshes 1 --require-anim |

Blender non è nel PATH; `python` nel PATH è la stub del Microsoft Store.
Per Blender 4.2 (non installato in locale): solo via CI quando il repo è su
GitHub: non dichiarare compatibilità 4.2 senza prova reale.

Atteso: l'ultima riga di stdout è
`RISULTATO passati=X falliti=Y totale=N` con **falliti=0**; exit code sempre 0,
il verdetto si legge dal log (convenzione come intelligent_uv).

Il packaging (`package_release.ps1 -OutputDir dist`) chiude con
`PACKAGE versione=0.2.1 file=19 py=16 docs=3`: 16 moduli `.py` + 3 file
doc/meta, mai file di sviluppo, test o `__pycache__` dentro lo zip; insieme
allo zip produce il `.sha256` e la lista `files.txt` confrontabile. Il
workflow CI `.github/workflows/ci.yml` ripete la suite headless su
Ubuntu/Windows × Blender `4.2.23`/`5.2.3` e un job `package` ricostruisce e
verifica zip, contenuti e SHA-256 con gli stessi criteri. Il gate G3
(installazione pulita su configurazione vergine) resta da confermare
manualmente.

---

## 4. Requisiti (difetti noti del set GPL esistente, da NON ripetere)

1. Un solo cambio di modalità per conversione, non uno per segmento: la storia
   di undo deve restare pulita e il rig grosso non deve impazzire.
2. Naming affidabile: indice a due cifre (`_seg_00`), stabile tra
   disinstallazioni, mai collisione con i bone originali.
3. Spazio sempre esplicito: ogni chiamata a `bbone_segment_*` è corredata dal
   test che ne fissa lo spazio atteso; niente matrici "a occhio".
4. I pesi si accumulano in memoria e si scrivono UNA sola volta; la
   normalizzazione tocca solo i deform group.
5. Niente loop Python per vertice che richiama API ripetute: calcoli batch,
   scrittura sequenziale (`foreach_set` dove possibile).
6. Roll, ease e scale dei bbone sono coperti: l'equivalenza numerica della
   Fase 2 li scopre subito se manca il termine.
7. Errori: messaggi chiari (cosa manca, su quale bone/mesh), mai traceback nudo
   all'utente.
8. Undo/redo supportati dagli operatori (`bl_options` corretti REGISTER/UNDO).

---

## 5. Rischi noti (dal piano)

- Scala/ease/roll dei bbone: la Fase 2 li espone; fixture già variata (C).
- Cambi API su Blender 5.x: test su 4.2 (CI) e su 5.2 (locale) sempre.
- Mesh grosse: niente loop Python per vertice con chiamate ripetute (req. 5).
