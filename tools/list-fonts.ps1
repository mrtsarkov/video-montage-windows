#Requires -Version 5.1
<#
  Windows font inventory for montage §3.5 (replaces fc-list / ~/Library/Fonts).
#>
param(
    [int]$Limit = 80
)

$dirs = @(
    "$env:WINDIR\Fonts",
    "$env:LOCALAPPDATA\Microsoft\Windows\Fonts"
)

Write-Host "=== Windows fonts (sample) ===" -ForegroundColor Cyan
$seen = @{}
$rows = @()

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem $dir -Include *.ttf, *.otf, *.ttc -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        $family = $_.BaseName -replace '-?(Regular|Bold|Italic|Light|Medium|SemiBold|Black).*', ''
        if (-not $seen.ContainsKey($_.FullName)) {
            $seen[$_.FullName] = $true
            $rows += [PSCustomObject]@{
                Family = $family
                File = $_.Name
                Path = $_.FullName
            }
        }
    }
}

$rows | Sort-Object Family, File | Select-Object -First $Limit | Format-Table -AutoSize
Write-Host "Total font files scanned: $($seen.Count) (showing up to $Limit)"

Write-Host "`nGlyph check (PIL):" -ForegroundColor Cyan
$sample = "АБВабвЁё0123456789—«»…№%`$₽→✓✕"
& py -3 -c @"
from pathlib import Path
from PIL import ImageFont, ImageDraw, Image
sample = '$sample'
notdef = ImageFont.truetype(r'$env:WINDIR\Fonts\arial.ttf', 32).getmask('￿')
paths = [r'$env:WINDIR\Fonts\arial.ttf', r'$env:WINDIR\Fonts\segoeui.ttf', r'$env:WINDIR\Fonts\calibri.ttf']
for p in paths:
    try:
        f = ImageFont.truetype(p, 32)
        missing = [c for c in sample if f.getmask(c).getbbox() == notdef.getbbox()]
        print(Path(p).name, 'missing:', ''.join(missing) or '(none)')
    except Exception as e:
        print(p, e)
"@
