# -*- coding: utf-8 -*-
"""Headless zip install suite for the BBone to Bones add-on.

Builds the release zip (or reuses dist/bbone_to_bones-<version>.zip), then starts
a second Blender process with an isolated profile: BLENDER_USER_CONFIG and
BLENDER_USER_SCRIPTS live under %TEMP%. That process installs the zip with
bpy.ops.preferences.addon_install, enables it with bpy.ops.preferences.addon_enable
and imports the package. The version declared by the installed add-on must equal
core.VERSION of the project. The add-on code is never modified.

Usage:
    blender -b --python tests/test_zip_install_suite.py

The verdict is the LAST line of stdout:
    RISULTATO passati=X falliti=Y totale=N
"""

import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")
PKG_NAME = "bbone_to_bones"
RUNTIME_DIRS = (".", "core", "ui")
RUNTIME_DOCS = ("blender_manifest.toml", "LICENSE", "README.md")
SUBPROCESS_TIMEOUT = 600

RESULTS = []
STATE = {}

INSTALL_SCRIPT = """
import os
import sys

import bpy

zip_path = os.environ["BTOB_ZIP"]
result = bpy.ops.preferences.addon_install(overwrite=True, filepath=zip_path)
print("BTOB_INSTALL {0}".format(sorted(result)))
if result != {"FINISHED"}:
    sys.exit(3)

result = bpy.ops.preferences.addon_enable(module="bbone_to_bones")
print("BTOB_ENABLE {0}".format(sorted(result)))
if result != {"FINISHED"}:
    sys.exit(4)

enabled = "bbone_to_bones" in bpy.context.preferences.addons
print("BTOB_ENABLED {0}".format(int(enabled)))
if not enabled:
    sys.exit(5)

import importlib

mod = importlib.import_module("bbone_to_bones")
core = importlib.import_module("bbone_to_bones.core")
print("BTOB_PATH {0}".format(os.path.abspath(mod.__file__)))
print("BTOB_BL_INFO {0}".format(".".join(str(p) for p in mod.bl_info["version"])))
print("BTOB_CORE {0}".format(".".join(str(p) for p in core.VERSION)))
print("BTOB_INSTALL_DONE")
"""


def check(name, fn):
    """Record a check result without aborting the rest."""
    try:
        detail = fn()
        RESULTS.append((name, True, detail or ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, "{0}: {1}".format(type(exc).__name__, exc)))


def _core():
    """Import the headless core package from ROOT (same pattern as the meta suite)."""
    package_dir = os.path.dirname(ROOT)
    if sys.path[:1] != [package_dir]:
        if package_dir in sys.path:
            sys.path.remove(package_dir)
        sys.path.insert(0, package_dir)
    importlib.import_module(PKG_NAME)
    return importlib.import_module("{0}.core".format(PKG_NAME))


def _version_string(version_tuple):
    """Render a version tuple as the X.Y.Z string used in the zip name."""
    return ".".join(str(part) for part in version_tuple)


def _build_zip(target_path):
    """Build the runtime zip with the same selection as package_release.ps1."""
    files = []
    for rel_dir in RUNTIME_DIRS:
        abs_dir = os.path.join(ROOT, rel_dir)
        for name in sorted(os.listdir(abs_dir)):
            if name.endswith(".py") and os.path.isfile(os.path.join(abs_dir, name)):
                rel = name if rel_dir == "." else "{0}/{1}".format(rel_dir, name)
                files.append(rel)
    files.extend(RUNTIME_DOCS)
    with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted(set(files)):
            source = os.path.join(ROOT, *rel.split("/"))
            archive.write(source, arcname="{0}/{1}".format(PKG_NAME, rel))
    return target_path


def do_zip_available():
    """A zip of the current version exists in dist/ or is built in %TEMP%."""
    core = _core()
    version = _version_string(core.VERSION)
    STATE["version"] = version
    dist_zip = os.path.join(DIST, "{0}-{1}.zip".format(PKG_NAME, version))
    if os.path.isfile(dist_zip):
        zip_path = dist_zip
        origin = "dist"
    else:
        STATE["tmp_dir"] = tempfile.mkdtemp(prefix="btob_zip_build_")
        zip_path = _build_zip(
            os.path.join(STATE["tmp_dir"], "{0}-{1}.zip".format(PKG_NAME, version))
        )
        origin = "build temporaneo"
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    if "{0}/__init__.py".format(PKG_NAME) not in names:
        raise AssertionError("{0} non contiene {1}/__init__.py".format(zip_path, PKG_NAME))
    if "{0}/core/__init__.py".format(PKG_NAME) not in names:
        raise AssertionError("{0} non contiene {1}/core/__init__.py".format(zip_path, PKG_NAME))
    STATE["zip_path"] = zip_path
    return "zip {0} ({1}, {2} file)".format(os.path.basename(zip_path), origin, len(names))


def _run_isolated_install():
    """Run the install in a fresh Blender with a profile under %TEMP%, return its output."""
    import bpy

    if "zip_path" not in STATE:
        raise AssertionError("zip non disponibile: il test precedente ha fallito")
    profile_root = tempfile.mkdtemp(prefix="btob_profile_")
    STATE["profile_root"] = profile_root
    config_dir = os.path.join(profile_root, "config")
    scripts_dir = os.path.join(profile_root, "scripts")
    os.makedirs(config_dir)
    os.makedirs(scripts_dir)
    script_path = os.path.join(profile_root, "install_check.py")
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(INSTALL_SCRIPT)

    env = dict(os.environ)
    env["BLENDER_USER_CONFIG"] = config_dir
    env["BLENDER_USER_SCRIPTS"] = scripts_dir
    env["BTOB_ZIP"] = STATE["zip_path"]
    completed = subprocess.run(
        [bpy.app.binary_path, "--factory-startup", "-b", "-noaudio", "--python", script_path],
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )
    output = "{0}\n{1}".format(completed.stdout or "", completed.stderr or "")
    STATE["returncode"] = completed.returncode
    STATE["output"] = output
    STATE["scripts_dir"] = scripts_dir
    return output


def _marker(output, key):
    """Return the text after BTOB_<key> in the subprocess output ("" if no value), or None."""
    match = re.search(r"^BTOB_{0}(?: (.*))?$".format(key), output, re.MULTILINE)
    if match is None:
        return None
    return (match.group(1) or "").strip()


def do_install_isolated():
    """Blender installs the zip, enables the add-on and imports it (isolated profile)."""
    output = _run_isolated_install()
    if STATE["returncode"] != 0:
        raise AssertionError(
            "Blender exit {0} durante l'installazione: {1}".format(
                STATE["returncode"], output.strip()[-400:]
            )
        )
    if _marker(output, "INSTALL_DONE") is None:
        raise AssertionError("riga BTOB_INSTALL_DONE assente nell'output di Blender")
    install = _marker(output, "INSTALL") or ""
    if install != "['FINISHED']":
        raise AssertionError("addon_install ha restituito {0} invece di FINISHED".format(install))
    return "addon_install e addon_enable FINISHED"


def do_enabled_and_importable():
    """The add-on is enabled and the package imports from the isolated scripts folder."""
    output = STATE.get("output", "")
    if _marker(output, "ENABLED") != "1":
        raise AssertionError("add-on non risulta abilitato (BTOB_ENABLED assente o 0)")
    path = _marker(output, "PATH")
    if not path:
        raise AssertionError("il modulo bbone_to_bones non si e' importato")
    scripts_dir = os.path.abspath(STATE["scripts_dir"])
    if not os.path.abspath(path).startswith(scripts_dir):
        raise AssertionError(
            "modulo caricato da {0}, fuori dal profilo isolato {1}".format(path, scripts_dir)
        )
    return "abilitato, importato da profilo isolato"


def do_installed_version_matches_core():
    """The version declared by the installed add-on equals core.VERSION of the project."""
    output = STATE.get("output", "")
    expected = STATE["version"]
    bl_info_version = _marker(output, "BL_INFO")
    core_version = _marker(output, "CORE")
    if bl_info_version is None or core_version is None:
        raise AssertionError("versione del pacchetto installato non letta dall'output")
    if bl_info_version != expected:
        raise AssertionError(
            "bl_info version installata {0} != core.VERSION {1}".format(bl_info_version, expected)
        )
    if core_version != expected:
        raise AssertionError(
            "core.VERSION installata {0} != core.VERSION progetto {1}".format(core_version, expected)
        )
    return "versione installata {0} == core.VERSION".format(expected)


def _cleanup():
    """Remove the temporary profile and build folder created by this suite."""
    for key in ("profile_root", "tmp_dir"):
        path = STATE.get(key)
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def main():
    import bpy

    try:
        check("zip_disponibile", do_zip_available)
        check("install_isolato", do_install_isolated)
        check("abilitato_e_importabile", do_enabled_and_importable)
        check("versione_installata_core", do_installed_version_matches_core)
    finally:
        _cleanup()

    print("BTOB zip install suite addon={0} blender={1}".format(PKG_NAME, bpy.app.version_string))
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
