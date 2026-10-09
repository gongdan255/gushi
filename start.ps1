Set-Location -LiteralPath $PSScriptRoot
$poetryPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $poetryPython) {
    & $poetryPython -X utf8 app.py
} else {
    python -X utf8 app.py
}
