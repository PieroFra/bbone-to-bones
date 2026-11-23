# Lancia il probe UI di BBone to Bones in Blender 5.2 GUI, poi verifica l'output.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'find_blender.ps1')
$install = Get-BlenderInstall
$blender = $install.BlenderExe
$blenderPy = $install.BlenderPython
if (-not $blender) { throw "BLENDER_NOT_FOUND | BlenderExe vuoto" }
if (-not $blenderPy) { throw "BLENDER_NOT_FOUND | BlenderPython vuoto" }
$probe = Join-Path $PSScriptRoot 'btob_ui_probe.py'
$check = Join-Path $PSScriptRoot 'ui_math_check.py'
$outDir = Join-Path $env:TEMP 'btob_gui'

& $blender --factory-startup --no-window-focus --python $probe
& $blenderPy $check $outDir
exit $LASTEXITCODE
