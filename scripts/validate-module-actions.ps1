param(
    [string]$Python = 'python',
    [string]$DependencyDirectory = ''
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskOldQt = $env:QT_QPA_PLATFORM
Push-Location $taskRoot
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $taskBootstrap = 'import sys,runpy; '
    if ($DependencyDirectory) {
        $taskDependencies = (Resolve-Path -LiteralPath $DependencyDirectory).Path
        $taskQuoted = ConvertTo-Json -InputObject $taskDependencies -Compress
        $taskBootstrap += "sys.path.insert(0,$taskQuoted); "
    }
    & $Python -c ($taskBootstrap + "sys.argv=['pytest','tests/test_module_actions.py','tests/test_manager.py','tests/test_recovery_standalone.py','tests/test_profile.py','tests/test_profile_config.py','tests/test_persist_toggles.py','-q']; runpy.run_module('pytest',run_name='__main__')")
    if ($LASTEXITCODE -ne 0) { throw 'Module action regression tests failed.' }
    & $Python -c ($taskBootstrap + "sys.argv=['black','--check','aw_qt/module_actions.py','aw_qt/trayicon.py','tests/test_module_actions.py']; runpy.run_module('black',run_name='__main__')")
    if ($LASTEXITCODE -ne 0) { throw 'Module action formatting check failed.' }
} finally {
    $env:QT_QPA_PLATFORM = $taskOldQt
    Pop-Location
}
