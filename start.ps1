param([switch]$Demo)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (!(Test-Path .venv)) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno Python" }
}
& .\.venv\Scripts\python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias" }
$env:BLUETTI_DEMO = if ($Demo) { "1" } else { "0" }
& .\.venv\Scripts\python.exe -m uvicorn explorer.app:app --host 127.0.0.1 --port 8765
