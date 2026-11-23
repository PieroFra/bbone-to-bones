# run_gates.ps1 - 4 Gate comuni su BBone to Bones
param([string]$BlenderBin = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $PSScriptRoot 'find_blender.ps1')
$install = Get-BlenderInstall $BlenderBin
if (-not $install -or [string]::IsNullOrWhiteSpace($install.BlenderExe)) { throw 'BLENDER_NOT_FOUND' }
$blender = $install.BlenderExe
$py = $install.BlenderPython
Write-Host "Gate run: blender=$blender"
# Gate 1 py_compile
Write-Host '=== GATE 1: py_compile ==='
$pyFiles = @(
  (Join-Path $root '__init__.py'),
  (Join-Path $root 'core\__init__.py'),
  (Join-Path $root 'core\segments.py'),
  (Join-Path $root 'core\revert.py'),
  (Join-Path $root 'core\weights.py'),
  (Join-Path $root 'core\bake.py'),
  (Join-Path $root 'core\export.py')
) + @(Get-ChildItem (Join-Path $root 'ui\*.py') | ForEach-Object { $_.FullName })
& $py -m py_compile $pyFiles
if ($LASTEXITCODE -ne 0) { throw "GATE1_FAIL" }
Write-Host "GATE1_OK | py_compile files=$($pyFiles.Count)"
# Gate 1b versioni
Write-Host '=== GATE 1b: check_versions ==='
& $py (Join-Path $PSScriptRoot 'check_versions.py')
if ($LASTEXITCODE -ne 0) { throw 'VERSION_FAIL' }
# Gate 1c hardcoded
Write-Host '=== GATE 1c: hardcoded_paths ==='
& $py (Join-Path $PSScriptRoot 'hardcoded_paths.py') --root $root
if ($LASTEXITCODE -ne 0) { throw 'HARDCODED_FAIL' }
# Gate 2 suite
Write-Host '=== GATE 2: suite ==='
$suites = @('tests\run.py','tests\test_revert_suite.py','tests\test_core_segments_revert_suite.py','tests\test_core_weights_bake_suite.py','tests\test_core_export_suite.py','tests\test_ui_operators_suite.py','tests\test_addon_meta_suite.py','tests\test_zip_install_suite.py')
$totalPassed = 0; $totalFailed = 0
foreach ($s in $suites) {
  $out = & $blender -b -noaudio --python (Join-Path $root $s) 2>&1
  $verdict = $out | Select-String 'RISULTATO passati=' | Select-Object -Last 1
  Write-Host "$s => $($verdict.Line)"
  if ($verdict.Line -match 'passati=(\d+) falliti=(\d+)') { $totalPassed += [int]$Matches[1]; $totalFailed += [int]$Matches[2] }
  else { throw "GATE2_FAIL | $s no verdict" }
}
Write-Host "GATE2 totals passed=$totalPassed failed=$totalFailed"
if ($totalFailed -ne 0 -or $totalPassed -ne 80) { throw "GATE2_FAIL | expected 80/0 got $totalPassed/$totalFailed" }
Write-Host 'GATE2_OK'
# Gate 3/4 packaging + install + audit
Write-Host '=== GATE 3/4: packaging + install + audit ==='
$pkg = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\package_release.ps1') -OutputDir dist -BlenderBin $blender 2>&1
$pkg | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) { throw 'GATE34_BUILD_FAIL' }
$zip = Get-ChildItem (Join-Path $root 'dist\bbone_to_bones-*.zip') | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { throw 'GATE34_FAIL | zip missing' }
& $py (Join-Path $PSScriptRoot 'install_isolated.py') --zip $zip.FullName --blender $blender
if ($LASTEXITCODE -ne 0) { throw 'GATE3_FAIL' }
& $py (Join-Path $PSScriptRoot 'audit_zip.py') $zip.FullName
if ($LASTEXITCODE -ne 0) { throw 'GATE4_FAIL' }
Write-Host "ALL_GATES_OK | zip=$($zip.Name)"
exit 0
