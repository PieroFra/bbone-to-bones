# tools/scripts/find_blender.ps1 — Autodiscovery cross-platform di Blender e del suo Python
# Zero path assoluti hardcoded. Ordine di ricerca:
#   1. $env:BLENDER_EXE / $env:BLENDER_BIN (CI e configurazione manuale)
#   2. Get-Command blender (PATH)
#   3. Directory standard per OS (Blender Foundation, /opt, /usr/local, ~/Applications)
# Restituisce un hashtable con @{ BlenderExe = '...'; BlenderPython = '...' }.
# Se Blender non e' trovato, lancia un errore esplicito BLENDER_NOT_FOUND.

function Get-BlenderInstall {
    param(
        [string]$HintExe
    )

    $exe = $null

    if ($HintExe -and (Test-Path -LiteralPath $HintExe -PathType Leaf)) {
        $exe = (Get-Item -LiteralPath $HintExe).FullName
    }

    if (-not $exe) {
        foreach ($envName in @("BLENDER_EXE", "BLENDER_BIN")) {
            $val = [Environment]::GetEnvironmentVariable($envName)
            if ($val -and (Test-Path -LiteralPath $val -PathType Leaf)) {
                $exe = (Get-Item -LiteralPath $val).FullName
                break
            }
        }
    }

    if (-not $exe) {
        $cmd = Get-Command blender -ErrorAction SilentlyContinue
        if ($cmd) { $exe = $cmd.Source }
    }

    if (-not $exe) {
        $candidates = @()

        $isWindows = if ($null -ne $IsWindows) { $IsWindows } else { ($PSVersionTable.PSEdition -eq "Desktop") -or $true }
        $isLinux = if ($null -ne $IsLinux) { $IsLinux } else { $false }
        $isMacOS = if ($null -ne $IsMacOS) { $IsMacOS } else { $false }

        if ($isWindows) {
            $pf = $env:ProgramFiles
            $pf86 = ${env:ProgramFiles(x86)}
            if ($pf) {
                $candidates += Get-ChildItem -Path (Join-Path $pf "Blender Foundation") -Directory -ErrorAction SilentlyContinue |
                    Sort-Object Name |
                    ForEach-Object { Join-Path $_.FullName "blender.exe" }
            }
            if ($pf86) {
                $candidates += Get-ChildItem -Path (Join-Path $pf86 "Blender Foundation") -Directory -ErrorAction SilentlyContinue |
                    Sort-Object Name |
                    ForEach-Object { Join-Path $_.FullName "blender.exe" }
            }
            if ($pf) { $candidates += (Join-Path $pf "Blender Foundation\blender.exe") }
            if ($pf86) { $candidates += (Join-Path $pf86 "Blender Foundation\blender.exe") }
        } elseif ($isLinux) {
            $candidates += @("/opt/blender/blender", "/usr/local/blender/blender", "/usr/bin/blender")
            if ($env:HOME) {
                $candidates += Get-ChildItem -Path (Join-Path $env:HOME "blender*") -Directory -ErrorAction SilentlyContinue |
                    Sort-Object Name |
                    ForEach-Object { Join-Path $_.FullName "blender" }
            }
        } elseif ($isMacOS) {
            $candidates += @("/Applications/Blender.app/Contents/MacOS/Blender")
            if ($env:HOME) {
                $candidates += Get-ChildItem -Path (Join-Path $env:HOME "Applications") -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -like "Blender*" } |
                    Sort-Object Name |
                    ForEach-Object { Join-Path $_.FullName "Contents/MacOS/Blender" }
            }
        }

        $candidates = $candidates | Sort-Object

        foreach ($c in $candidates) {
            if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) {
                $exe = (Get-Item -LiteralPath $c).FullName
                break
            }
        }
    }

    if (-not $exe) {
        throw "BLENDER_NOT_FOUND | hint=$HintExe | env BLENDER_EXE/BLENDER_BIN assenti | blender non nel PATH | nessuna installazione standard trovata"
    }

    $blenderDir = Split-Path -Parent $exe
    $py = $null
    $pyCandidates = @(
        (Join-Path $blenderDir "5.2\python\bin\python.exe"),
        (Join-Path $blenderDir "5.2/python/bin/python3"),
        (Join-Path $blenderDir "5.3\python\bin\python.exe"),
        (Join-Path $blenderDir "5.3/python/bin/python3"),
        (Join-Path $blenderDir "python/bin/python.exe"),
        (Join-Path $blenderDir "python/bin/python3"),
        (Join-Path $blenderDir "python\bin\python.exe"),
        (Join-Path $blenderDir "python\bin\python3.exe")
    )
    foreach ($c in $pyCandidates) {
        if (Test-Path -LiteralPath $c -PathType Leaf) { $py = $c; break }
    }

    if (-not $py) {
        $pyCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pyCmd) { $py = $pyCmd.Source }
    }

    return @{
        BlenderExe = $exe
        BlenderPython = $py
    }
}

function Find-BlenderInstall { Get-BlenderInstall @args }
