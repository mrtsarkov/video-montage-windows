#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$Label
)

$root = Split-Path $PSScriptRoot -Parent
$runDir = Join-Path $root "runs\$Label"
$editDir = Join-Path $runDir "edit"
$outDir = Join-Path $runDir "out"
$compDir = Join-Path $editDir "comp"
$fontsDir = Join-Path $compDir "fonts"

foreach ($d in @($editDir, $outDir, $compDir, $fontsDir)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

$template = Join-Path $root "edit\data.json.template"
$dataJson = Join-Path $editDir "data.json"
if (-not (Test-Path $dataJson)) {
    if (Test-Path $template) {
        Copy-Item $template $dataJson
    } else {
        @{} | ConvertTo-Json -Depth 5 | Set-Content $dataJson -Encoding UTF8
    }
}

$notes = Join-Path $editDir "NOTES.md"
if (-not (Test-Path $notes)) {
    @"
# Run: $Label

## Пересборка

- Подложка: ``tools/build-plate.ps1 -RunLabel $Label``
- Графика (HyperFrames): ``npx hyperframes render --format mov -o runs/$Label/edit/layer-front.mov``
- Свод: ``tools/mux-final.ps1 -RunLabel $Label``

## Телеметрия off

``````powershell
`$env:HYPERFRAMES_NO_TELEMETRY = "1"
`$env:DO_NOT_TRACK = "1"
``````
"@ | Set-Content $notes -Encoding UTF8
}

Write-Host "Initialized run: $runDir"
Write-Host "  edit/  -> $editDir"
Write-Host "  out/   -> $outDir"
