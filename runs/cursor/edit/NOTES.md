# Run: cursor

## Паспорт (ответы по умолчанию)

- Формат: 16:9, 1920×1080, 30 fps (как исходник)
- Картинка: с контрастом (eq на подложке)
- Шрифты: Segoe UI Bold + Segoe UI (Windows, кириллица OK)
- Цвета: accent1 `#f97316`, accent2 `#38bdf8`, dark `#18181b`

## Пересборка

```powershell
$env:HYPERFRAMES_NO_TELEMETRY = "1"
$env:DO_NOT_TRACK = "1"

# EDL + голос
py -3 scripts\build_edl.py runs\cursor\edit\transcripts\2026-05-28` 13-20-36-words.json runs\cursor\edit\edl.json
py -3 scripts\build_voice.py takes\2026-05-28` 13-20-36.mp4 runs\cursor\edit\edl.json runs\cursor\edit\voice.wav

# Подложка (~100 с)
py -3 scripts\build_plate.py takes\2026-05-28` 13-20-36.mp4 runs\cursor\edit\edl.json runs\cursor\edit\plate.mp4

# Comp (субтитры отключены — build_subtitles.py не запускать)
py -3 scripts\generate_comp.py

# Графика (346 с, draft ~15–40 мин)
cd runs\cursor\edit\comp
npx hyperframes render --format mov --quality draft -w 2 -o ..\layer-front.mov

# Финал
..\..\..\tools\mux-final.ps1 -RunLabel cursor
```

## Окружение

- whisper-cli: `tools\whisper-cpp\Release\whisper-cli.exe` (скачан v1.7.6)
- Расшифровка: faster-whisper large-v3 (py -3 scripts\transcribe_take.py)
- Маска «слово за головой»: не считалась (нет remove-background в прогоне)
