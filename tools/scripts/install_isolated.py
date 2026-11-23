# tools/scripts/install_isolated.py — Gate 3: installazione ZIP in profilo isolato
# Installa il pacchetto in un profilo Blender isolato (BLENDER_USER_CONFIG),
# verifica caricamento/enable/disable pulito senza errori.
#
# Uso:
#   python tools/scripts/install_isolated.py --zip <path.zip> --blender <path>
# Exit: 0 se installazione pulita, 1 altrimenti.
# Output: "INSTALL_OK | ..." o "INSTALL_FAIL | ..."

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

# Script Blender eseguito dopo install-file --enable: si verifica che
# l'estensione sia installata e abilitabile, poi si disabilita pulito.
ENVSCRIPT = """
import bpy, sys, traceback
MOD = 'bl_ext.user_default.bbone_to_bones'
try:
    # In Blender 5.2 le estensioni sono namespaced per repository
    if MOD not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module=MOD)
    operatore = hasattr(bpy.types, 'BTOB_OT_convert_segments')
    if not operatore:
        raise RuntimeError('operatore BTOB_OT_convert_segments non registrato')
    bpy.ops.preferences.addon_disable(module=MOD)
    bpy.ops.wm.save_userpref()
    print('INSTALL_OK | enable/disable pulito')
except Exception:
    traceback.print_exc()
    print('INSTALL_FAIL | eccezione durante enable/disable')
    sys.exit(1)
"""


def main():
    parser = argparse.ArgumentParser(description="Installazione isolata ZIP in profilo Blender.")
    parser.add_argument("--zip", required=True, help="Percorso del pacchetto ZIP")
    parser.add_argument("--blender", required=True, help="Percorso dell'eseguibile Blender")
    args = parser.parse_args()

    if not os.path.isfile(args.zip):
        print(f"INSTALL_FAIL | zip non trovato: {args.zip}")
        return 1
    if not os.path.isfile(args.blender):
        print(f"INSTALL_FAIL | blender non trovato: {args.blender}")
        return 1

    tmpdir = tempfile.mkdtemp(prefix="actd_isolated_")
    env = dict(os.environ)
    env["BLENDER_USER_CONFIG"] = tmpdir
    env["BLENDER_USER_SCRIPTS"] = os.path.join(tmpdir, "scripts")
    env["BLENDER_USER_RESOURCES"] = os.path.join(tmpdir, "resources")
    try:
        # Installa il pacchetto come estensione via CLI di Blender 4.2+
        # install-file (non install): 'install' cerca un ID nei repository.
        result = subprocess.run(
            [args.blender, "--background", "--factory-startup",
             "--command", "extension", "install-file", "-r", "user_default",
             args.zip, "--enable"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if result.returncode != 0:
            print(f"INSTALL_FAIL | extension install exit={result.returncode}")
            print(result.stdout[-2000:])
            print(result.stderr[-2000:])
            return 1
        # Verifica caricamento/enable/disable pulito
        envscript = os.path.join(tmpdir, "check_enable.py")
        with open(envscript, "w", encoding="utf-8") as fh:
            fh.write(ENVSCRIPT)
        # Senza --factory-startup: il profilo isolato deve caricare
        # l'estensione appena installata con install-file --enable.
        result2 = subprocess.run(
            [args.blender, "--background",
             "--python", envscript],
            capture_output=True, text=True, timeout=120, env=env,
        )
        combined = result2.stdout + result2.stderr
        if "INSTALL_OK" not in combined:
            print("INSTALL_FAIL | enable/disable non pulito")
            print(combined[-2000:])
            return 1
        print(f"INSTALL_OK | zip={os.path.basename(args.zip)} profile={tmpdir}")
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
