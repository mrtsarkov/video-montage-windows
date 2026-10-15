# Run: v2 (фаза 1 — «честный рендер»)

Статус: **ГОТОВО и принято.** `runs/v2/out/final.mp4` — 336.933 с, H.264 1920×1080 30 fps,
18.43 Мбит/с, BT.709 tv, звук −14.20 LUFS / TP −1.20 dBTP.
`verify_final.py`: **8 проверок из 8 PASS** (`runs/v2/edit/verify.json`).
Следующая фаза — автоматизация: см. `RESUME-v2.md` в корне проекта.

### Итоговые замеры приёмки

| Проверка | Результат |
|---|---|
| video | h264 / yuv420p / 1920×1080 / 30.000 fps / 336.933 с (EDL 336.910, delta +0.023) |
| color_tags | tv / bt709 / bt709 / bt709 |
| bitrate | 18.43 Мбит/с — **потолок материала**: lossless-мастер весит 18.35 Мбит/с |
| audio | aac / −14.20 LUFS (цель −14±0.5) / TP −1.20 dBTP (предел −1) |
| subtitles | 0 блоков `.sub`, `subtitles.json` отсутствует |
| layer_alpha | поля 4.79/4.79/13.98/62.31 % (норма 3.5/7), 70/84 кадров пустых, 14 с графикой |
| black_frames | первый 177.46/255, последний 180.58/255 |
| source | источник читается, 384.900 с ≥ финала, метки согласованы |
| цвет акцента | #f97316 измерен как [247,113,19], ошибка 2.33/255 |

## Паспорт (ответы владельца)

- Формат: 16:9, 1920×1080, 30 fps (как исходник)
- Картинка: с контрастом; коррекция берётся из `data.json.correction` (black 2 / white 242)
- Шрифты: Segoe UI Bold + Segoe UI (локальные копии в `comp/fonts/`)
- Цвета: accent1 `#f97316`, accent2 `#38bdf8`, dark `#18181b`, white `#f4f4f5`
- Субтитры: **выключены** (`"subtitles": false`)
- Камера: **наездов нет** — материал 1080p, апскейл запрещён (§7.1). Задокументированное отклонение.
- Звук: −14 LUFS / ≤ −1 dBTP, деклик-фейды 12 мс на склейках

## Что сделано

| Шаг | Команда | Время | Результат |
|---|---|---|---|
| Рез по огибающей | `py -3 scripts\snap_cuts.py "takes\2026-05-28 13-20-36.mp4" runs\v2\edit\edl.json runs\v2\edit\edl.json --data runs\v2\edit\data.json` | ~20 с | 33 → 81 сегмент, 336.91 с |
| Контроль EDL | `py -3 scripts\check_edl.py "takes\2026-05-28 13-20-36.mp4" runs\v2\edit\edl.json --json runs\v2\edit\check_edl.json` | ~10 с | резы на речи 4/6 (было 5/20), пауз >0.3 с: 0 (было 48) |
| Голос | `py -3 scripts\build_voice.py "takes\2026-05-28 13-20-36.mp4" runs\v2\edit\edl.json runs\v2\edit\voice.wav` | ~40 с | 336.910 с, delta 0.000 |
| Композиция | `py -3 scripts\generate_comp.py v2` | ~2 с | `comp/index.html`, субтитров 0, gsap локальный |
| Проверка композиции | `cd runs\v2\edit\comp; hyperframes check` | ~40 с | 0 ошибок (7 предупреждений GSAP до правки селектора) |
| Рендер графики | `cd runs\v2\edit\comp; hyperframes render --format mov --quality draft -w 4 -o ..\layer-front.mov` | **8 м 49 с** | `layer-front.mov` 412 МБ, ProRes 4444, 336.9 с |

## Что осталось (в порядке выполнения)

```powershell
cd D:\LLM\video-montage-template
$env:HYPERFRAMES_NO_TELEMETRY = "1"; $env:DO_NOT_TRACK = "1"

# 1. Сборка финала: lossless-мастер (81 склейка + слой), 2-проходный звук, 2-проходный H.264 30 Мбит/с
py -3 scripts\build_final.py "takes\2026-05-28 13-20-36.mp4" runs\v2\edit --bitrate 30M
#    ~6–10 мин. Мастер пересобирается сам: слой новее.

# 2. Машинная приёмка (§5/§6.1/§9.3/§11.3/§12)
py -3 scripts\verify_final.py runs\v2\out\final.mp4 --edit runs\v2\edit --source "takes\2026-05-28 13-20-36.mp4" --json runs\v2\edit\verify.json

# 3. Цвет акцента (необязательно, быстрый контроль)
py -3 scripts\check_color.py runs\v2\out\final.mp4 --at 1.0 --hex f97316
```

Ожидание по приёмке: `bitrate`, `audio`, `subtitles`, `layer_alpha` должны перейти из FAIL в PASS.
Если `layer_alpha` снова ругается на поля — смотреть `box-shadow` и отступы панелей в `scripts/generate_comp.py`.

## Узкие места, о которых стоит помнить

- `layer-front.mov` рендерится ~9 мин при 4 воркерах; любая правка композиции требует повторного рендера.
- Мастер lossless весит ~770 МБ и пересобирается при каждом изменении EDL или слоя.
- `build_plate.py` (апскейл 1.35×) и `tools\mux-final.ps1` (однпроходный ABW, `overlay=format=auto`)
  больше не используются этой цепочкой и подлежат ревизии в фазе 2.
- В ffmpeg 9.0.2 нет `-filter_complex_script`: граф передаётся только через `-filter_complex`.
