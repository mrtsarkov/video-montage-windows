#Requires -Version 5.1
param(
    [string]$RunLabel = "cursor"
)

$env:HYPERFRAMES_NO_TELEMETRY = "1"
$env:DO_NOT_TRACK = "1"

$root = Split-Path $PSScriptRoot -Parent
$edit = Join-Path $root "runs\$RunLabel\edit"
$out = Join-Path $root "runs\$RunLabel\out"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$plate = Join-Path $edit "plate.mp4"
$layer = Join-Path $edit "layer-front.mov"
$voice = Join-Path $edit "voice.wav"
$final = Join-Path $out "final.mp4"
$voiceNorm = Join-Path $edit "voice-norm.wav"

if (-not (Test-Path $plate)) { throw "Missing plate: $plate" }
if (-not (Test-Path $layer)) { throw "Missing graphics layer: $layer" }
if (-not (Test-Path $voice)) { throw "Missing voice: $voice" }

ffmpeg -y -i $voice -af "loudnorm=I=-14:TP=-1:LRA=11:print_format=summary" $voiceNorm 2>&1 | Out-Null

$dur = (ffprobe -v error -show_entries format=duration -of csv=p=0 $plate).Trim()

ffmpeg -y -i $plate -i $layer -i $voiceNorm `
  -filter_complex "[1:v]format=yuva444p,scale=1920:1080[fg];[0:v][fg]overlay=format=auto:shortest=1,setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]" `
  -map "[v]" -map 2:a `
  -c:v libx264 -b:v 30M -maxrate 35M -bufsize 60M -preset slow -tune grain -pix_fmt yuv420p `
  -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 `
  -c:a aac -b:a 192k -shortest -t $dur $final

Write-Host "Final: $final" -ForegroundColor Green
ffprobe -v error -show_format -show_streams $final
