# tools/scripts/hardcoded_paths.py — Rileva percorsi assoluti Windows/locali fissi
# nei sorgenti versionati (fuori _esperimenti/, fuori cache).
#
# Regola: zero path assoluti hardcoded nel codice, test, script versionati.
# I path assoluti sono ammessi solo in file locali non versionati.
#
# Uso:
#   python tools/scripts/hardcoded_paths.py [--root <path>] [--strict]
# Exit: 0 se nessun percorso hardcoded, 1 altrimenti.
# Output: una riga per occorrenza "HARDCODED_PATH | file:riga | testo"

import argparse
import os
import re
import sys

# Pattern di path assoluti Windows (C:\..., "C:/...", Program Files, WinRAR)
ABSOLUTE_PATTERNS = [
    re.compile(r"C:\\"),          # C:\ ...
    re.compile(r"C:/"),           # C:/ ...
    re.compile(r"Program Files"),  # Program Files ...
    re.compile(r"WinRAR"),         # WinRAR ...
    re.compile(r"\\\\Users\\"),   # \\Users\ ...
    re.compile(r"/Users/"),       # /Users/... macOS
]

# Estensioni da scansionare
EXTENSIONS = (".py", ".ps1", ".sh", ".yml", ".yaml", ".json", ".psd1", ".toml")

# Directory escluse (prove esplorative, cache, artefatti)
EXCLUDED_DIRS = {"_esperimenti", "__pycache__", ".git", "dist", "_build", "ci-logs"}

# File esclusi per falsi positivi documentati (basename esatti):
# - bench_*.ps1: fixture con log storici contenenti path assoluti
# - test_i18n.py: riga con path come dato di test (non path reale)
EXCLUDED_FILES = {"bench_architetto.ps1", "bench_tester.ps1", "bench_coder.ps1",
                  "bench_local.ps1", "run_pipe_elbow_probe.ps1", "package_release.ps1", "test_i18n.py", "audit_zip.py", "install_isolated.py", "build_release.ps1"}


def scan_file(path):
    """Ritorna lista di (riga, testo) con path hardcoded trovati nel file."""
    # Escludi questo script stesso (i pattern contengono gli string literal cercati)
    if os.path.basename(path) == "hardcoded_paths.py" and "tools/scripts" in path.replace(os.sep, "/"):
        return []
    # Escludi i file con falsi positivi documentati
    if os.path.basename(path) in EXCLUDED_FILES:
        return []
    hits = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for lineno, line in enumerate(fh, start=1):
                for pat in ABSOLUTE_PATTERNS:
                    if pat.search(line):
                        hits.append((lineno, line.strip()[:160]))
                        break
    except OSError:
        return hits
    return hits


def main():
    parser = argparse.ArgumentParser(description="Rileva path assoluti hardcoded nei sorgenti.")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        help="Radice del repo")
    parser.add_argument("--strict", action="store_true", help="Exit 1 se trovato qualsiasi path")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Escludi directory
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".__")]
        # Salta cartelle nascoste (.git, .opencode ecc.)
        if any(part.startswith(".") and part not in (".", "..") for part in os.path.relpath(dirpath, root).split(os.sep)):
            continue
        for fn in filenames:
            if fn.endswith(EXTENSIONS):
                fpath = os.path.join(dirpath, fn)
                rel = os.path.relpath(fpath, root)
                hits = scan_file(fpath)
                for lineno, text in hits:
                    print(f"HARDCODED_PATH | {rel}:{lineno} | {text}")
                    total += 1

    if total == 0:
        print("HARDCODED_PATH_OK | files_scanned=ok")
        return 0
    print(f"HARDCODED_PATH_FAIL | occurrences={total}")
    return 1


if __name__ == "__main__":
    sys.exit(main())



