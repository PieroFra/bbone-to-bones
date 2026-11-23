# tools/scripts/audit_zip.py — Gate 4: audit del pacchetto ZIP
# Verifica che lo ZIP contenga solo file runtime (niente test, cache, .git,
# script locali o file temporanei) e stampa SHA256 + file list.
#
# Uso:
#   python tools/scripts/audit_zip.py <path.zip>
# Exit: 0 se audit ok, 1 altrimenti.
# Output: "ZIP_AUDIT_OK | sha256=<hash> | files=<n>" o "ZIP_AUDIT_FAIL | ..."

import hashlib
import os
import sys
import zipfile

# File consentiti nel pacchetto runtime dell'estensione
ALLOWED_EXTENSIONS = (".py", ".toml", ".txt", ".md", "")  # "" = file senza estensione (es. LICENSE)

# Directory e pattern vietati
FORBIDDEN_PARTS = {"__pycache__", ".git", "dist", "_esperimenti", "tests", "test", ".github"}
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".zip", ".rar", ".blend", ".log")
FORBIDDEN_NAMES = {"test_out.txt", "verdict.txt", "metrics.jsonl", "gate.lock"}


def audit(zip_path):
    """Audit di un pacchetto ZIP: ritorna (ok, sha256, lista_file, problemi)."""
    if not os.path.isfile(zip_path):
        return False, "", [], [f"file non trovato: {zip_path}"]
    problems = []
    files = []
    with open(zip_path, "rb") as fh:
        sha256 = hashlib.sha256(fh.read()).hexdigest()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            # Salta directory entries
            if name.endswith("/"):
                continue
            files.append(name)
            parts = set(name.replace("\\", "/").split("/"))
            lower = name.lower()
            if any(part in FORBIDDEN_PARTS for part in parts):
                problems.append(f"directory vietata: {name}")
            if lower.endswith(FORBIDDEN_SUFFIXES):
                problems.append(f"estensione vietata: {name}")
            if os.path.basename(name) in FORBIDDEN_NAMES:
                problems.append(f"file locale vietato: {name}")
            if not lower.endswith(ALLOWED_EXTENSIONS) and not lower.endswith((".json",)):
                problems.append(f"estensione non runtime: {name}")
            if "__pycache__" in name:
                problems.append(f"cache: {name}")
    return len(problems) == 0, sha256, files, problems


def main():
    if len(sys.argv) < 2:
        print("ZIP_AUDIT_FAIL | reason=usage: python tools/scripts/audit_zip.py <path.zip>")
        return 1
    ok, sha256, files, problems = audit(sys.argv[1])
    if not ok:
        for p in problems:
            print(f"ZIP_AUDIT_FAIL | {p}")
        print("ZIP_AUDIT_FAIL | reason=violazioni runtime")
        return 1
    print(f"ZIP_AUDIT_OK | sha256={sha256} | files={len(files)}")
    for f in sorted(files):
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
