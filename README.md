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

## Одна команда: из дубля в готовый ролик

```powershell
cd D:\LLM\video-montage-template

# графика рисуется из сценария съёмки (по блокам и B-roll каждого блока)
py -3 scripts\montage.py --label 2026-10-15-крипта `
    --take "takes\2026-10-15 13-54-01.mp4" --script "script\2026-10-15-крипта.md"

# без сценария — эвристика по триггерным словам расшифровки
py -3 scripts\montage.py --label v4 --take "takes\НОВЫЙ-ДУБЛЬ.mp4" --transcribe
```

Стадии с `--script`: `env → edl → script_plan → voice → comp → check → render → sfx →
final → verify → verify_extra → report`. Каждая стадия пропускается, если её выходы
новее входов. `--force all`, `--only <стадия>`, `--from <стадия>`, `--allow-fail`.

Результат: `runs/<метка>/out/final.mp4` и отчёт `runs/<метка>/edit/report.md` (§13).

Подробности, цифры последнего прогона и что дальше: [RESUME.md](RESUME.md).
История ранних фаз — [RESUME-v2.md](RESUME-v2.md).

## Съёмка: чтобы глаза смотрели в объектив

```powershell
py -3 scripts\build_teleprompter.py "script\2026-10-15-крипта.md" runs\teleprompter.html --eyeline
py -3 scripts\check_eyeline.py "takes\2026-10-15 13-54-01.mp4"
```

`--eyeline` паркует строку чтения на высоте объектива (вебка сверху ≈ 9 % высоты) и
сужает колонку; `check_eyeline.py` измеряет, куда реально ушёл взгляд, и возвращает
вердикт `OK` / `GAZE DOWN`. Подробно: [docs/EYELINE.md](docs/EYELINE.md).

## Тексты в кадре

Вставки собираются из сценария, служебная разметка (`#N`, `Хук:`, `CTA`,
`🎞 B-roll:`) в кадр не попадает, а строки измеряются настоящим Inter и
переписываются, если не влезают — многоточия в кадре не бывает. Для конкретного
ролика тексты можно доводить руками: `script/<метка>-inserts.json`.
Подробно: [docs/INSERT-COPY.md](docs/INSERT-COPY.md).

## Приёмка

Прогон сам себя проверяет и останавливается на первом провале:

| Протокол | Что проверяет |
|---|---|
| `edit/report.md` | отчёт §13: что проверено вживую, что сверено по коду, что не проверялось |
| `edit/verify.json` | 8 групп: формат, цветовые теги, битрейт, звук, субтитры, поля кадра, чёрные кадры, источник |
| `edit/verify_extra.json` | 9 проверок: лист кадров, синхрон звука, клиппинг от грейда, дрожь на удержании, звук на событиях, детерминизм, **0 многоточий в кадре**, **0 дублей**, **графика не на лице** |

Провал любой группы останавливает прогон; `--allow-fail` — только для отладки.
Линия взгляда проверяется отдельно перед съёмкой: `check_eyeline.py`.

## Структура

```
takes/          — сырые дубли (не трогать агентом)
script/         — сценарии съёмки (#NЗаголовок~50 сек + 🎞 B-roll) и тексты вставок
fonts/          — локальные шрифты (опционально)
sfx/            — звуки (опционально)
logos/          — логотипы (опционально)
refs/           — брендбук и референсы стиля
runs/<метка>/
  edit/         — пульт data.json, EDL, планы, композиция, слои (субтитры выключены)
  out/          — final.mp4
tools/          — PowerShell-раннеры
scripts/        — Python (расшифровка, EDL, графика, sfx, приёмка, замеры)
docs/           — тексты вставок, линия взгляда
```

## Полезные команды

| Задача | Команда |
|--------|---------|
| Опись дублей | `.\tools\scan-takes.ps1` |
| Расшифровка с DTW-таймингами слов | `py -3 scripts\build_words_dtw.py take.mp4 out-words.json` |
| Проверка линии взгляда | `py -3 scripts\check_eyeline.py takes\take.mp4` |
| Суфлёр на линии объектива | `py -3 scripts\build_teleprompter.py script.md out.html --eyeline` |
| Каталог sfx | `py -3 scripts\sfx_catalog.py sfx\` |

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
