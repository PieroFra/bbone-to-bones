# -*- coding: utf-8 -*-
"""Headless metadata suite for the BBone to Bones add-on.

Verifies that the three version sources stay in sync: ``core.VERSION``
(``core/__init__.py``), ``bl_info["version"]`` (``__init__.py``) and the
``version`` field of ``blender_manifest.toml``. It never imports
``tests/run.py`` (that module executes its own runner on import) and never
touches the add-on code.

Usage:
    blender -b --python tests/test_addon_meta_suite.py

The verdict is the LAST line of stdout:
    RISULTATO passati=X falliti=Y totale=N
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, "blender_manifest.toml")

RESULTS = []


def check(name, fn):
    """Record a check result without aborting the rest."""
    try:
        detail = fn()
        RESULTS.append((name, True, detail or ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, "{0}: {1}".format(type(exc).__name__, exc)))


def _addon_module():
    """Load the add-on package from ROOT (never a stale copy in AppData)."""
    import importlib

    package_dir = os.path.dirname(ROOT)
    pkg_name = os.path.basename(ROOT)
    if sys.path[:1] != [package_dir]:
        if package_dir in sys.path:
            sys.path.remove(package_dir)
        sys.path.insert(0, package_dir)
    existing = sys.modules.get(pkg_name)
    if existing is not None:
        mod_file = os.path.abspath(getattr(existing, "__file__", "") or "")
        if not mod_file.startswith(os.path.abspath(ROOT)):
            for key in [k for k in list(sys.modules) if k == pkg_name or k.startswith(pkg_name + ".")]:
                del sys.modules[key]
    return importlib.import_module(pkg_name)


def _core():
    """Import the headless core package from ROOT."""
    _addon_module()
    import importlib

    return importlib.import_module("{0}.core".format(os.path.basename(ROOT)))


def _version_string(version_tuple):
    """Render a version tuple as the ``X.Y.Z`` string used in the manifest."""
    return ".".join(str(part) for part in version_tuple)


def test_meta_version_bl_info():
    """core.VERSION must equal bl_info["version"] of the add-on package."""
    mod = _addon_module()
    core = _core()
    bl_info_version = mod.bl_info.get("version")
    if bl_info_version is None:
        raise AssertionError("bl_info['version'] missing")
    if tuple(bl_info_version) != tuple(core.VERSION):
        raise AssertionError(
            "bl_info version {0} != core.VERSION {1}".format(
                tuple(bl_info_version), tuple(core.VERSION)
            )
        )
    return "bl_info version {0} == core.VERSION".format(tuple(core.VERSION))


def test_meta_version_manifest():
    """The manifest version string must equal core.VERSION as X.Y.Z."""
    core = _core()
    if not os.path.isfile(MANIFEST):
        raise AssertionError("manifest {0} missing".format(MANIFEST))
    with open(MANIFEST, "r", encoding="utf-8") as handle:
        content = handle.read()
    match = re.search(r'^\s*version\s*=\s*"(\d+\.\d+\.\d+)"', content, re.MULTILINE)
    if match is None:
        raise AssertionError("no version field found in the manifest")
    manifest_version = match.group(1)
    expected = _version_string(core.VERSION)
    if manifest_version != expected:
        raise AssertionError(
            "manifest version {0} != core.VERSION {1}".format(manifest_version, expected)
        )
    return "manifest version {0} == core.VERSION".format(manifest_version)


def main():
    tests = [
        test_meta_version_bl_info,
        test_meta_version_manifest,
    ]
    for test in tests:
        check(test.__name__, test)

    print(
        "BTOB meta suite addon={0} blender={1}".format(
            os.path.basename(ROOT), __import__("bpy").app.version_string
        )
    )
    for name, passed, detail in RESULTS:
        print("CHECK {0} {1} {2}".format(name, "PASS" if passed else "FAIL", detail))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("RISULTATO passati={0} falliti={1} totale={2}".format(passed, failed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
