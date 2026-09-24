#Requires -Version 5.1
<#
.SYNOPSIS
  Transcribe a take with whisper-cli (Russian, large-v3).
  Splits on pauses >= 0.7s via ffmpeg silencedetect, then transcribes each segment.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Take,
    [string]$OutDir,
    [string]$Model = "$env:USERPROFILE\.cache\whisper\ggml-large-v3.bin",
    [string]$Language = "ru"
)

$Take = Resolve-Path $Take
$root = Split-Path $PSScriptRoot -Parent
if (-not $OutDir) {
    $OutDir = Join-Path $root "runs\cursor\edit\transcripts"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (-not (Test-Path $Model)) {
    Write-Error "Whisper model not found: $Model`nRun: .\tools\download-whisper-model.ps1"
    exit 1
}

$base = [IO.Path]::GetFileNameWithoutExtension($Take)
$wav = Join-Path $env:TEMP "$base-transcribe.wav"
ffmpeg -y -i $Take -ar 16000 -ac 1 -c:a pcm_s16le $wav 2>&1 | Out-Null

# Detect silence segments (pause >= 0.7s)
$silenceLog = Join-Path $env:TEMP "$base-silence.log"
ffmpeg -i $wav -af "silencedetect=noise=-30dB:d=0.7" -f null - 2> $silenceLog
$lines = Get-Content $silenceLog
$segments = @()
$start = 0.0
foreach ($line in $lines) {
    if ($line -match "silence_start:\s*([\d.]+)") {
        $end = [double]$Matches[1]
        if ($end - $start -ge 0.3) {
            $segments += @{ start = $start; end = $end }
        }
    }
    elseif ($line -match "silence_end:\s*([\d.]+)") {
        $start = [double]$Matches[1]
    }
}
# tail segment
$dur = (ffprobe -v error -show_entries format=duration -of csv=p=0 $wav).Trim()
if ([double]$dur - $start -ge 0.3) {
    $segments += @{ start = $start; end = [double]$dur }
}
if ($segments.Count -eq 0) {
    $segments = @(@{ start = 0; end = [double]$dur })
}

Write-Host "Transcribing $($segments.Count) segment(s) from $base..." -ForegroundColor Cyan
$all = @()
$i = 0
foreach ($seg in $segments) {
    $i++
    $segWav = Join-Path $env:TEMP ("{0}-seg-{1:D3}.wav" -f $base, $i)
    $len = $seg.end - $seg.start
    ffmpeg -y -ss $seg.start -t $len -i $wav -c copy $segWav 2>&1 | Out-Null
    $outBase = Join-Path $OutDir ("{0}-seg-{1:D3}" -f $base, $i)
    whisper-cli -m $Model -l $Language -oj -of $outBase --no-timestamps 0 $segWav 2>&1 | Out-Null
    $jsonPath = "$outBase.json"
    if (Test-Path $jsonPath) {
        $j = Get-Content $jsonPath -Raw | ConvertFrom-Json
        foreach ($w in $j.transcription) {
            $all += @{
                word = $w.text
                start = [double]$w.offsets.from / 1000.0 + $seg.start
                end = [double]$w.offsets.to / 1000.0 + $seg.start
            }
        }
    }
}

$merged = Join-Path $OutDir "$base-words.json"
$all | ConvertTo-Json -Depth 5 | Set-Content $merged -Encoding UTF8
Write-Host "Saved: $merged ($($all.Count) words)"
