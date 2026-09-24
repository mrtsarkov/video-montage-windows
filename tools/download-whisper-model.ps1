#Requires -Version 5.1
<#
  Downloads ggml-large-v3.bin (~3 GB). Run only with explicit user consent.
#>
param(
    [string]$Dest = "$env:USERPROFILE\.cache\whisper\ggml-large-v3.bin"
)

$url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"
$dir = Split-Path $Dest -Parent
New-Item -ItemType Directory -Force -Path $dir | Out-Null

if (Test-Path $Dest) {
    Write-Host "Model already exists: $Dest"
    exit 0
}

Write-Host "Downloading ggml-large-v3.bin (~3 GB) to $Dest ..." -ForegroundColor Yellow
Write-Host "URL: $url"
Invoke-WebRequest -Uri $url -OutFile $Dest -UseBasicParsing
Write-Host "Done. Size:" (Get-Item $Dest).Length "bytes"
