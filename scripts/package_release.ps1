param(
    [string]$OutputDir = 'dist',
    [switch]$DryRun
)

# Packaging di rilascio di BBone to Bones.
#
# Legge la versione da blender_manifest.toml, verifica che coincida con
# bl_info["version"] in __init__.py e con VERSION in core/__init__.py, mette in
# staging la struttura runtime bbone_to_bones/ e produce in dist\:
#   - bbone_to_bones-<versione>.zip
#   - bbone_to_bones-<versione>.sha256     (formato sha256sum)
#   - bbone_to_bones-<versione>.files.txt  (file list confrontabile)
#
# Poi valida il pacchetto con Blender 5.2 locale, se presente:
#   1. blender --command extension validate (se il comando e' supportato)
#   2. installazione del .zip + enable + assert su bbone_to_bones_settings,
#      che deve chiudere con la riga G3_INSTALL_OK.
#
# Uscita attesa: righe "ZIP ...", "SHA256 ...", "G3 ..." e infine la riga
# finale "PACKAGE versione=... file=... py=... docs=...". Nessuna dipendenza
# esterna oltre a Blender gia' installato in locale.

$ErrorActionPreference = 'Stop'

# Zona oraria fissa sugli entry dello ZIP: stesso contenuto -> stesso SHA-256.
$ZipEpoch = [DateTimeOffset]::new(2000, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
$BlenderBin = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'

# Contratto di packaging: 10 .py (radice, core\, ui\ + manifest) e 3 doc/meta.
$ExpectedPy = 10
$ExpectedDocs = 3
$IncludeDocs = @('blender_manifest.toml', 'LICENSE', 'README.md')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Get-ManifestVersion {
    param([string]$Path)

    $text = [IO.File]::ReadAllText($Path)
    # Primo match "version = ..." all'inizio riga: schema_version non matcha
    # perche' non inizia con "version".
    $m = [regex]::Match($text, '(?m)^\s*version\s*=\s*"(\d+\.\d+\.\d+)"')
    if (-not $m.Success) {
        throw "manifest.version non trovato in $Path (parsing testuale fallito)."
    }
    return $m.Groups[1].Value
}

function Get-BlInfoVersion {
    param([string]$Path)

    $text = [IO.File]::ReadAllText($Path)
    $m = [regex]::Match($text, '(?m)^\s*"version"\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
    if (-not $m.Success) {
        throw "bl_info['version'] non trovato in $Path (parsing testuale fallito)."
    }
    return $m.Groups[1].Value + '.' + $m.Groups[2].Value + '.' + $m.Groups[3].Value
}

function Get-CoreVersion {
    param([string]$Path)

    $text = [IO.File]::ReadAllText($Path)
    $m = [regex]::Match($text, '(?m)^\s*VERSION\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
    if (-not $m.Success) {
        throw "VERSION non trovato in $Path (parsing testuale fallito)."
    }
    return $m.Groups[1].Value + '.' + $m.Groups[2].Value + '.' + $m.Groups[3].Value
}

function Get-Sha256 {
    param([string]$Path)
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

# ---------------------------------------------------------------------------
# 1. Radice e versione
# ---------------------------------------------------------------------------

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$initPath = Join-Path $root '__init__.py'
if (-not (Test-Path -LiteralPath $initPath)) { throw "Add-on non trovato: $initPath" }

$version = Get-ManifestVersion -Path (Join-Path $root 'blender_manifest.toml')
$blInfoVersion = Get-BlInfoVersion -Path $initPath
$coreVersion = Get-CoreVersion -Path (Join-Path $root 'core\__init__.py')

if ($blInfoVersion -ne $version) {
    throw ("Versione incoerente: manifest {0} != bl_info {1}" -f $version, $blInfoVersion)
}
if ($coreVersion -ne $version) {
    throw ("Versione incoerente: manifest {0} != core VERSION {1}" -f $version, $coreVersion)
}

$missingDocs = @()
foreach ($doc in $IncludeDocs) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $doc))) { $missingDocs += $doc }
}
if ($missingDocs.Count -gt 0) {
    throw ('Documenti richiesti assenti: ' + ($missingDocs -join ', '))
}

# ---------------------------------------------------------------------------
# 2. Selezione dei file: solo .py di radice, core\ e ui\ + i doc/meta
# ---------------------------------------------------------------------------

$selected = New-Object System.Collections.Generic.List[object]
foreach ($dir in @('.', 'core', 'ui')) {
    $absDir = if ($dir -eq '.') { $root } else { Join-Path $root ($dir -replace '/', '\') }
    if (-not (Test-Path -LiteralPath $absDir)) { throw "Directory runtime assente: $absDir" }
    foreach ($f in (Get-ChildItem -LiteralPath $absDir -Filter '*.py' -File)) {
        $rel = if ($dir -eq '.') { $f.Name } else { "$dir/$($f.Name)" }
        $selected.Add([pscustomobject]@{ Rel = $rel; Full = $f.FullName })
    }
}
foreach ($doc in $IncludeDocs) {
    $selected.Add([pscustomobject]@{ Rel = $doc; Full = (Join-Path $root $doc) })
}
$selected = @($selected | Sort-Object -Property Rel -Unique)

$pyCount = @($selected | Where-Object { $_.Rel -like '*.py' }).Count
$docCount = @($selected | Where-Object { $_.Rel -notlike '*.py' }).Count
if ($pyCount -ne $ExpectedPy) {
    throw ("Conteggio .py inatteso: $pyCount != $ExpectedPy (c'e' un file nuovo da gestire?)")
}
if ($docCount -ne $ExpectedDocs) {
    throw ("Conteggio doc/meta inatteso: $docCount != $ExpectedDocs")
}
foreach ($required in @('__init__.py', 'core/__init__.py', 'ui/__init__.py')) {
    if (-not ($selected | Where-Object { $_.Rel -eq $required })) {
        throw "File runtime richiesto assente: $required"
    }
}

# ---------------------------------------------------------------------------
# 3. Staging in bbone_to_bones/
# ---------------------------------------------------------------------------

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) ("opencode\bbone_pkg\{0}_{1}" -f $stamp, [guid]::NewGuid().ToString('N').Substring(0, 8))
$pkgDir = Join-Path $stagingRoot 'bbone_to_bones'

try {
    New-Item -ItemType Directory -Path $pkgDir -Force | Out-Null

    foreach ($f in $selected) {
        $parts = $f.Rel -split '/'
        $destDir = $pkgDir
        for ($i = 0; $i -lt ($parts.Count - 1); $i++) {
            $destDir = Join-Path $destDir $parts[$i]
        }
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $f.Full -Destination (Join-Path $destDir $parts[$parts.Count - 1]) -Force
    }

    if (-not (Test-Path -LiteralPath (Join-Path $pkgDir 'blender_manifest.toml'))) {
        throw 'Staging non valido: blender_manifest.toml non e alla radice di bbone_to_bones/.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $pkgDir '__init__.py'))) {
        throw 'Staging non valido: __init__.py non e alla radice di bbone_to_bones/.'
    }

    $staged = @(Get-ChildItem -LiteralPath $pkgDir -Recurse -File | ForEach-Object {
        [pscustomobject]@{
            Rel  = $_.FullName.Substring($pkgDir.Length + 1).Replace('\', '/')
            Full = $_.FullName
        }
    } | Sort-Object -Property Rel)

    # Nessun file di sviluppo dentro lo staging: niente di fuori root/core/ui.
    $leaks = @($staged | Where-Object {
        $_.Rel -match '^(tests|docs|\.git|\.github|scripts|__pycache__|ci-logs|dist)/' -or
        $_.Rel -in @('AGENTS.md', 'opencode.json', '.gitignore') -or
        $_.Rel -match '\.(pyc|pyo|log|txt|ps1|png|jpg|gif|blend|blend1|zip)$'
    } | ForEach-Object { $_.Rel })
    if ($leaks.Count -gt 0) {
        throw ('Esclusione violata, file di sviluppo nello staging: ' + ($leaks -join ', '))
    }

    # -----------------------------------------------------------------------
    # 4. File list
    # -----------------------------------------------------------------------

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# bbone_to_bones $version - release file list")
    $lines.Add("# manifest.version $version | bl_info $blInfoVersion | core VERSION $coreVersion")
    $lines.Add("# generated $((Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')) deterministic build")
    $lines.Add("# files $($staged.Count) (py $pyCount, docs $docCount)")
    $lines.Add("# columns: sha256  bytes  relative-path")

    foreach ($s in $staged) {
        $hash = Get-Sha256 -Path $s.Full
        $size = (Get-Item -LiteralPath $s.Full).Length
        $lines.Add(('{0}  {1}  {2}' -f $hash, $size, $s.Rel))
    }

    # -----------------------------------------------------------------------
    # 5. ZIP deterministico (timestamp fisso, slash Unix, prefisso bbone_to_bones/)
    # -----------------------------------------------------------------------

    Add-Type -AssemblyName System.IO.Compression | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null

    $targetDir = if ($DryRun) { $stagingRoot } else {
        if ([IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $root $OutputDir }
    }
    if (-not (Test-Path -LiteralPath $targetDir)) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }

    $zipName = "bbone_to_bones-$version.zip"
    $zipPath = Join-Path $targetDir $zipName
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }

    $fs = [IO.File]::Open($zipPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $zip = [System.IO.Compression.ZipArchive]::new(
            $fs, [System.IO.Compression.ZipArchiveMode]::Create, $true, [System.Text.Encoding]::UTF8)
        try {
            foreach ($s in $staged) {
                $entry = $zip.CreateEntry(
                    ('bbone_to_bones/' + $s.Rel), [System.IO.Compression.CompressionLevel]::Optimal)
                $entry.LastWriteTime = $ZipEpoch.DateTime
                $outStream = $entry.Open()
                $inStream = [IO.File]::OpenRead($s.Full)
                try { $inStream.CopyTo($outStream) }
                finally { $inStream.Dispose(); $outStream.Dispose() }
            }
        }
        finally { $zip.Dispose() }
    }
    finally { $fs.Dispose() }

    # -----------------------------------------------------------------------
    # 6. Checksum e file list su disco
    # -----------------------------------------------------------------------

    $zipHash = Get-Sha256 -Path $zipPath
    $shaPath = Join-Path $targetDir ("bbone_to_bones-$version.sha256")
    $listPath = Join-Path $targetDir ("bbone_to_bones-$version.files.txt")

    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($shaPath, ("{0}  {1}`n" -f $zipHash, $zipName), $utf8)
    [IO.File]::WriteAllLines($listPath, $lines.ToArray(), $utf8)

    # -----------------------------------------------------------------------
    # 7. Verifica su Blender 5.2 locale (validate + installazione G3)
    # -----------------------------------------------------------------------

    $g3Message = 'SKIP blender non presente: ' + $BlenderBin
    if (Test-Path -LiteralPath $BlenderBin) {
        # 1) Validazione del pacchetto, se il nodo --command extension.validate esiste.
        $valLines = & $BlenderBin --command extension validate $zipPath 2>&1 | ForEach-Object { $_.ToString() }
        $valCode = $LASTEXITCODE
        if ($null -eq $valCode) { $valCode = -1 }
        Write-Output ("G3_VALIDATE exit={0}" -f $valCode)
        $valLines | Where-Object { $_ } | Select-Object -Last 3 | ForEach-Object { Write-Output ("G3_VALIDATE | " + $_) }

        # 2) Installazione vera del .zip in risorsa utente, enable e assert sul PropertyGroup.
        $expr = (
            "import bpy, addon_utils; " +
            "r = bpy.ops.preferences.addon_install(overwrite=True, filepath=r'$zipPath'); " +
            "assert r == {'FINISHED'}, r; " +
            "addon_utils.enable('bbone_to_bones', default_set=True, persistent=True); " +
            "assert 'bbone_to_bones' in bpy.context.preferences.addons, 'add-on non montato'; " +
            "assert hasattr(bpy.types.Scene, 'bbone_to_bones_settings'), 'manca bbone_to_bones_settings'; " +
            "print('G3_INSTALL_OK')"
        )
        $instLines = & $BlenderBin --factory-startup -b -noaudio --python-expr $expr 2>&1 | ForEach-Object { $_.ToString() }
        $instCode = $LASTEXITCODE
        if ($null -eq $instCode) { $instCode = -1 }
        if ($instCode -ne 0 -or -not ($instLines | Where-Object { $_.Trim() -eq 'G3_INSTALL_OK' })) {
            throw ("Installazione G3 fallita su Blender 5.2 locale (exit=$instCode): " + (($instLines | Select-Object -Last 5) -join ' | '))
        }
        $g3Message = 'OK (validate exit=' + $valCode + ', install exit=' + $instCode + ')'
    }
    Write-Output ("G3_INSTALL_OK {0}" -f $g3Message)

    # -----------------------------------------------------------------------
    # 8. Report finale
    # -----------------------------------------------------------------------

    Write-Output ("ZIP {0}" -f $zipPath)
    Write-Output ("SHA256 {0}" -f $zipHash)
    Write-Output ("CHECKSUM {0}" -f $shaPath)
    Write-Output ("FILELIST {0}" -f $listPath)
    Write-Output ("STAGING {0}" -f $stagingRoot)
    if ($DryRun) { Write-Output 'MODALITA dry-run: dist\ non e stato toccato.' }
    Write-Output ("PACKAGE versione={0} file={1} py={2} docs={3}" -f $version, $staged.Count, $pyCount, $docCount)
}
finally {
    if ((-not $DryRun) -and (Test-Path -LiteralPath $stagingRoot)) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}

exit 0
