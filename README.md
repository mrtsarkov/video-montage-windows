# Video Montage Template (Windows + HyperFrames)

Воспроизводимый процесс монтажа «говорящих роликов» по правилам `MONTAGE-PROMPT-v4.md`.

**GitHub:** https://github.com/mrtsarkov/video-montage-windows

## Новый компьютер

```powershell
git clone https://github.com/mrtsarkov/video-montage-windows.git
cd video-montage-windows
.\setup-windows.ps1
.\tools\download-whisper-model.ps1
.\tools\check-env.ps1
```

Подробнее: [DEPLOY.md](DEPLOY.md)

## Быстрый старт

1. **Скопируйте** эту папку в место проекта (или работайте прямо здесь).
2. Положите сырые дубли в `takes/` (опционально: `fonts/`, `sfx/`, `logos/`, `script.txt`, `refs/`).
3. Проверьте окружение:

   ```powershell
   .\tools\check-env.ps1
   ```

4. Инициализируйте прогон (создаст `runs/<метка>/edit/` и `runs/<метка>/out/`):

   ```powershell
   .\tools\init-run.ps1 -Label cursor
   ```

5. Откройте папку проекта в Cursor и вставьте **весь** `MONTAGE-PROMPT-v4.md` (+ при желании `PROJECT-CONFIG.md`) как задачу агенту.

6. Пробная сборка окружения (2 сек, §3.7):

   ```powershell
   .\tools\probe-trial.ps1 -RunLabel cursor
   ```

## Структура

```
takes/          — сырые дубли (не трогать агентом)
fonts/          — локальные шрифты (опционально)
sfx/            — звуки (опционально)
logos/          — логотипы (опционально)
script.txt      — текст ролика (опционально)
refs/           — референсы стиля (опционально)
runs/<метка>/
  edit/         — пульт data.json, EDL, планы (субтитры выключены)
  out/          — final.mp4
tools/          — PowerShell-раннеры
scripts/        — Python (EDL, графика, sfx, замеры текста)
```

## Переменные окружения (монтаж)

```powershell
$env:HYPERFRAMES_NO_TELEMETRY = "1"
$env:DO_NOT_TRACK = "1"
```

## Whisper-модель (русская расшифровка)

HyperFrames / `whisper-cli` нужна модель **large-v3** (не `.en`):

```powershell
# Только после явного согласия — скачивает ~3 GB
.\tools\download-whisper-model.ps1
```

Путь по умолчанию: `%USERPROFILE%\.cache\whisper\ggml-large-v3.bin`

## Полезные команды

| Задача | Команда |
|--------|---------|
| Опись дублей | `.\tools\scan-takes.ps1` |
| Расшифровка одного дубля | `.\tools\transcribe.ps1 -Take takes\clip01.mp4` |
| Список шрифтов Windows | `.\tools\list-fonts.ps1` |
| Каталог sfx | `py -3.12 scripts\sfx_catalog.py sfx\` |

## HyperFrames

- Движок графики: `hyperframes` / `npx hyperframes`
- Документация: `npx hyperframes docs`
- Проверка: `npx hyperframes check` в папке композиции
- Рендер слоёв графики: `--format mov` (ProRes 4444 с альфой)

## Итог

Готовый файл: `runs/<метка>/out/final.mp4`

Промпт монтажа: `MONTAGE-PROMPT-v4.md` (полная спецификация процесса).
