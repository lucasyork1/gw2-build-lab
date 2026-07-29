$ErrorActionPreference = 'Stop'

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnvironmentPython = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
$PythonCommand = if (Test-Path -LiteralPath $VirtualEnvironmentPython) {
    $VirtualEnvironmentPython
} else {
    'python'
}
$DatasetPath = Join-Path $RepositoryRoot 'data\normalized\current'
$OutputPath = Join-Path $RepositoryRoot 'work\verification-release'

Push-Location $RepositoryRoot
try {
    & $PythonCommand -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed with exit code $LASTEXITCODE" }

    if (-not (Test-Path -LiteralPath (Join-Path $DatasetPath 'dataset-manifest.json'))) {
        throw 'No published current dataset exists. Run a live refresh first.'
    }

    & $PythonCommand -m gw2_wvw_data.cli validate --dataset $DatasetPath
    if ($LASTEXITCODE -ne 0) { throw "Dataset validation failed with exit code $LASTEXITCODE" }

    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Recurse -Force
    }
    & $PythonCommand -m gw2_wvw_data.cli release --dataset $DatasetPath --output $OutputPath
    if ($LASTEXITCODE -ne 0) { throw "Release verification failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
