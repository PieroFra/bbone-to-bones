# tools/scripts/check_versions.py — Allineamento versioni bloccante (bbone_to_bones)
# Confronta la versione dichiarata in:
#   __init__.py (bl_info "version": (x, y, z))
#   core/__init__.py (costante VERSION = (x, y, z))
#   blender_manifest.toml (version = "x.y.z")
#   README.md (badge shields.io version-X.Y.Z)
#   CHANGELOG.md (primo titolo di sezione "## [x.y.z]", ignora [Unreleased])
#
# Se una versione differisce dalle altre, il controllo fallisce con errore
# esplicito. Nessuna versione e' scritta in chiaro nello script: la versione
# attesa e' ricavata confrontando le sorgenti tra loro.
# Uso:
#   python tools/scripts/check_versions.py [--root <path>]
# Exit: 0 se tutte le versioni trovate sono allineate, 1 altrimenti.
# Output: "VERSION_CHECK_OK | version=x.y.z" o "VERSION_MISMATCH | ..."

from __future__ import annotations

import argparse
import os
import re
import sys


def _leggi(path):
    """Legge il file in utf-8, restituisce None se assente/illeggibile."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return None


def _estrai(path, pattern, flags=re.MULTILINE):
    """Estrae il primo gruppo della regex dal file, oppure None."""
    text = _leggi(path)
    if text is None:
        return None
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def _tupla_alla_versione(path, pattern):
    """Converte una tupla (x, y, z) trovata con regex in 'x.y.z', oppure None."""
    text = _leggi(path)
    if text is None:
        return None
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return None
    return ".".join(m.group(i) for i in (1, 2, 3))


def _versione_primo_changelog(path):
    """Primo '## [x.y.z]' del CHANGELOG, ignorando '## [Unreleased]'."""
    text = _leggi(path)
    if text is None:
        return None
    for line in text.splitlines():
        if line.startswith("## ["):
            m = re.search(r"## \[(\d+\.\d+\.\d+)\]", line)
            if m:
                return m.group(1)
    return None


def raccogli_versioni(root):
    """Raccoglie le versioni dichiarate nelle sorgenti del progetto."""
    versioni = {}

    # bl_info in __init__.py: "version": (x, y, z)
    v = _tupla_alla_versione(
        os.path.join(root, "__init__.py"),
        r'"version":\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)',
    )
    if v:
        versioni["__init__.py"] = v

    # Costante VERSION in core/__init__.py: VERSION = (x, y, z)
    v = _tupla_alla_versione(
        os.path.join(root, "core", "__init__.py"),
        r"^\s*VERSION\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
    )
    if v:
        versioni["core/__init__.py"] = v

    # blender_manifest.toml: version = "x.y.z"
    v = _estrai(
        os.path.join(root, "blender_manifest.toml"),
        r'^version\s*=\s*"(\d+\.\d+\.\d+)"',
    )
    if v:
        versioni["blender_manifest.toml"] = v

    # README.md: badge shields.io badge/version-x.y.z-
    v = _estrai(
        os.path.join(root, "README.md"),
        r"badge/version-(\d+\.\d+\.\d+)-",
        flags=0,
    )
    if v:
        versioni["README.md (badge)"] = v

    # CHANGELOG.md: primo ## [x.y.z] (salta [Unreleased])
    v = _versione_primo_changelog(os.path.join(root, "CHANGELOG.md"))
    if v:
        versioni["CHANGELOG.md"] = v

    return versioni


def main():
    parser = argparse.ArgumentParser(description="Verifica allineamento versioni.")
    parser.add_argument(
        "--root",
        default=os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
        help="Radice del repo",
    )
    args = parser.parse_args()
    root = os.path.abspath(args.root)

    versioni = raccogli_versioni(root)

    if not versioni:
        print("VERSION_MISMATCH | reason=no version found in any file")
        return 1

    uniche = set(versioni.values())
    if len(uniche) > 1:
        print(
            "VERSION_MISMATCH | "
            + " | ".join(f"{k}={v}" for k, v in versioni.items())
        )
        return 1

    versione = next(iter(uniche))
    print(f"VERSION_CHECK_OK | version={versione}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
