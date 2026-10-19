# Отчёт §13 — прогон `2026-10-19-обзор-рынка`

- Исходник: `2026-10-19 13-33-11.mp4` (502.2 с монтажа из 134 склеек)
- Файл: `runs\2026-10-19-обзор-рынка\out\final.mp4` — h264 / yuv420p / 1920x1080 / 30.000 fps / duration 507.267 s
- Вердикт приёмки: **PASS** (8 прошло, 0 провалилось)
- Паспорт: 16:9, 30 fps, субтитры выключены

## 1. Проверено вживую (с цифрами)

| Проверка | Статус | Измерено | Цель |
|---|---|---|---|
| video | PASS | h264 / yuv420p / 1920x1080 / 30.000 fps / duration 507.267 s | h264 / yuv420p / 1920x1080 / 30 fps / duration = EDL sum +- 0.15 s |
| color_tags | PASS | color_range=tv / color_space=bt709 / color_primaries=bt709 / color_trc=bt709 | tv / bt709 / bt709 / bt709 (all four tags mandatory) |
| bitrate | PASS | 29.97 Mbps | >= 16 Mbps (target ~30 Mbps) |
| audio | PASS | aac / -14.20 LUFS / true peak -2.20 dBTP | aac / -14 LUFS +- 0.5 LU / true peak <= -0.85 dBTP |
| subtitles | PASS | comp/index.html: 0x class="subs", 0x class="sub clip"; edit/subtitles.json: absent | no class="subs", no class="sub clip", no edit/subtitles.json (spec sec. 5) |
| layer_alpha | PASS | empty 66/120 frames; visible 53/120 frames; min margins 5.00/5.00/7.50/12.87 % | >= 1 empty frame (max alpha == 0); graphics present (max alpha > 0.12); opaque bbox >= 3.5% of width and >= 7% of height from the edges |
| black_frames | PASS | first_frame mean luma 175.97/255; last_frame mean luma 29.56/255 | first and last frame mean luma > 8/255 |
| source | PASS | readable: D:\LLM\video-montage-template\takes\2026-10-19 13-33-11.mp4; duration: source 731.000 s vs final 507.267 s; color_tags: source and final tags agree (or source tags are unset) | readable; source duration >= final duration; colour tags consistent |
| frame_sheet | PASS | 47/47 stills in frames/ | one still per graphics element, after it settled |
| audio_sync | PASS | lag +0.00 ms (correlation 1.0000) | |lag| <= 5.0 ms |
| levels | PASS | paired on 13 EDL frames: source 0.03% -> final 0.02% clipped at 255 (grade adds -0.01 pp); p50 184-192; mean luma change 5.72/255 — 17 frame(s) skipped: graphics on screen (§9.3 plates are white by design) | grade adds <= 0.3 pp of clipping |
| jitter | PASS | max centroid drift 0.000 px/frame per element (4 element(s), ) | <= 0.25 px/frame on hold |
| sfx_placement | PASS | 51/51 events raise the level (median +8.5 dB) | each planned event louder than the voice-only track in its window |
| determinism | PASS | no infinite animation, no random/time source; 3 deterministic tl.call steps | no infinite, Math.random, Date.now, performance.now |
| copy_quality | PASS | 228 text node(s), 0 with an ellipsis; 0 line(s) rewritten to fit; copy: 2026-10-19-обзор-рынка-inserts.json | 0 ellipses on screen; long lines are rewritten, not cut short |
| retakes | PASS | 134 clips checked; 0 duplicate pair(s) left | 0 repeated or aborted phrases (build_edl.py + build_words_dtw.py remove them) |
| face_safe | PASS | face box x42% y30% 20×38%; 19 frame(s) measured, 5 exempt (liquid-glass stage); no graphics on the face | 0 frames with a graphic over the face outside the declared glass stage |

Резка по волне (`check_edl.py`):

| Метрика | Значение |
|---|---|
| segments | 134 |
| duration_s | 502.21 |
| threshold_rms | 0.00428 |
| dead_air_total_s | 19.81 |
| dead_air_lead_median_s | 0.08 |
| dead_air_lead_max_s | 0.09 |
| dead_air_tail_median_s | 0.06 |
| dead_air_tail_max_s | 1.41 |
| cut_in_lands_on_speech | 10 |
| cut_out_lands_on_speech | 13 |
| internal_pauses_over_max | 48 |

## 2. Сверено по коду и документации

- Субтитры: `subtitles: false` в пульте, 0 блоков `.sub` в композиции, `subtitles.json` нет (§5).
- Апскейла материала нет: сдвиг кадра (`push`) берёт кроп 1000×1080 и уменьшает его до 660×712, стеклянные перебивки — только `gblur`, без масштаба (§7.1).
- Сценические режимы кадра перечислены в `stage.json` (`glass` — размытие под плашку, `push` — кадр сдвигается) и применяются при сборке мастера; полнокадровые моменты помечены `data-layout-allow-occlusion`, поэтому поля кадра считаются по остальным кадрам.
- Взгляд в камеру: `check_eyeline.py` измеряет линию взгляда на дубле, `build_teleprompter.py --eyeline` паркует строку чтения на высоте объектива (docs/EYELINE.md).
- Тексты вставок: производственная разметка сценария (`#N`, `Хук:`, `CTA`, `🎞 B-roll:`) в кадр не попадает, строки измеряются настоящим Inter и переписываются, если не влезают (docs/INSERT-COPY.md); многоточий в кадре нет.
- Промежуточный файл — lossless (`-qp 0`), а не перекодирование с потерями (§11.3).
- Слой ProRes читается как BT.601 и складывается в RGB, мастер и финал помечены BT.709 tv (§11.3).
- gsap подключён локально (`comp/vendor/gsap.min.js`), интернет при монтаже не нужен (§1).
- Кривые: экспонента задана функцией; курсор мигает конечное число тактов (§9.2).
- Числа графики берутся из пульта, генератор пульт не перезаписывает (§1, §11.1).
- Звук: деклик-фейды 12 мс на склейках, нормализация проверена по записанному файлу (§6.1).
- Тон-коррекция: S-кривая из пульта с закреплённым белым (`1/1`), поэтому грейд не добавляет клиппинга — проверено парно по кадрам EDL (§11.4 против §12.9).

## Звуковой дизайн (§6.2)

| Событие | Время | Звук | Тип | Пик на кадре события |
|---|---|---|---|---|
| hook | 0.60 | pop-panel.mp3 | pop | 0.60 |
| title | 7.00 | impact-word.mp3 | impact | 7.00 |
| table | 13.90 | pop-panel.mp3 | pop | 13.90 |
| chips | 21.10 | pop-panel.mp3 | pop | 21.10 |
| quote | 30.10 | pop-panel.mp3 | pop | 30.10 |
| divider02 | 42.60 | pop-panel.mp3 | pop | 42.60 |
| quote | 45.80 | pop-panel.mp3 | pop | 45.80 |
| timeline | 52.40 | pop-panel.mp3 | pop | 52.40 |
| stat | 63.70 | click-04.mp3 | click | 63.70 |
| divider03 | 79.80 | pop-panel.mp3 | pop | 79.80 |
| timeline | 83.40 | pop-panel.mp3 | pop | 83.40 |
| stat | 105.00 | click-04.mp3 | click | 105.00 |
| quote | 113.80 | pop-panel.mp3 | pop | 113.80 |
| divider04 | 122.30 | pop-panel.mp3 | pop | 122.30 |
| table | 125.50 | pop-panel.mp3 | pop | 125.50 |
| stat | 134.50 | click-04.mp3 | click | 134.50 |
| quote | 159.20 | pop-panel.mp3 | pop | 159.20 |
| divider05 | 173.50 | pop-panel.mp3 | pop | 173.50 |
| timeline | 177.10 | pop-panel.mp3 | pop | 177.10 |
| chips | 185.00 | pop-panel.mp3 | pop | 185.00 |
| quote | 200.20 | pop-panel.mp3 | pop | 200.20 |
| divider06 | 213.00 | pop-panel.mp3 | pop | 213.00 |
| chips | 216.20 | pop-panel.mp3 | pop | 216.20 |
| quote | 257.50 | pop-panel.mp3 | pop | 257.50 |
| divider07 | 263.50 | pop-panel.mp3 | pop | 263.50 |
| timeline | 266.70 | pop-panel.mp3 | pop | 266.70 |
| quote | 282.00 | pop-panel.mp3 | pop | 282.00 |
| chips | 288.60 | pop-panel.mp3 | pop | 288.60 |
| divider08 | 304.70 | pop-panel.mp3 | pop | 304.70 |
| table | 308.10 | pop-panel.mp3 | pop | 308.10 |
| stat | 317.70 | click-04.mp3 | click | 317.70 |
| quote | 341.60 | pop-panel.mp3 | pop | 341.60 |
| divider09 | 348.70 | pop-panel.mp3 | pop | 348.70 |
| timeline | 352.10 | pop-panel.mp3 | pop | 352.10 |
| stat | 362.10 | click-04.mp3 | click | 362.10 |
| quote | 385.90 | pop-panel.mp3 | pop | 385.90 |
| divider10 | 392.00 | pop-panel.mp3 | pop | 392.00 |
| table | 395.30 | pop-panel.mp3 | pop | 395.30 |
| stat | 408.30 | click-04.mp3 | click | 408.30 |
| quote | 425.30 | pop-panel.mp3 | pop | 425.30 |
| divider11 | 431.40 | pop-panel.mp3 | pop | 431.40 |
| checklist | 435.30 | pop-panel.mp3 | pop | 435.30 |
| item | 436.02 | click-04.mp3 | click | 436.02 |
| item | 438.07 | click-04.mp3 | click | 438.07 |
| item | 439.77 | click-04.mp3 | click | 439.77 |
| item | 441.47 | click-04.mp3 | click | 441.47 |
| item | 442.37 | click-04.mp3 | click | 442.37 |
| quote | 462.60 | pop-panel.mp3 | pop | 462.60 |
| divider12 | 468.60 | pop-panel.mp3 | pop | 468.60 |
| quote | 473.80 | pop-panel.mp3 | pop | 473.80 |
| outro | 480.40 | impact-word.mp3 | impact | 480.40 |

## Сценарий и вставки (§9.4–9.5)

Блоков в сценарии: 12; привязано к записи: 12; плановая сумма 628 с при фактических 502 с.

| # | Блок | На таймлайне | Длина | Что нарисовано |
|---|---|---|---|---|
| 1 | HOOK: цена держится, деньги уходят | 0.0s | 43 с | 7.0s title·речь, 13.9s table·речь, 21.1s chips·речь, 30.1s quote·речь |
| 2 | Вынос стопов 15 октября | 42.7s | 38 с | 42.6s divider·речь, 45.8s quote·речь, 52.4s timeline·речь, 63.7s stat·речь |
| 3 | CPI и Уорш: ставка отложена | 80.3s | 42 с | 79.8s divider·речь, 83.4s timeline·речь, 105.0s stat·речь, 113.8s quote·речь |
| 4 | Разлоки: неделя тяжёлой токеномики | 122.4s | 52 с | 122.3s divider·речь, 125.5s table·речь, 134.5s stat·тактовка, 159.2s quote·речь |
| 5 | MSCI: удар по крипто-казначействам | 174.0s | 39 с | 173.5s divider·речь, 177.1s timeline·речь, 185.0s chips·речь, 200.2s quote·речь |
| 6 | Инфраструктура строится | 213.1s | 50 с | 213.0s divider·речь, 216.2s chips·тактовка, 257.5s quote·речь |
| 7 | Регуляторный пресс | 263.6s | 41 с | 263.5s divider·речь, 266.7s timeline·речь, 282.0s quote·речь, 288.6s chips·речь |
| 8 | Три урока по хранению | 305.0s | 44 с | 304.7s divider·речь, 308.1s table·речь, 317.7s stat·тактовка, 341.6s quote·речь |
| 9 | Календарь текущей недели | 348.9s | 43 с | 348.7s divider·речь, 352.1s timeline·речь, 362.1s stat·речь, 385.9s quote·речь |
| 10 | Сценарии и уровни | 392.2s | 40 с | 392.0s divider·речь, 395.3s table·речь, 408.3s stat·речь, 425.3s quote·речь |
| 11 | Практические выводы | 432.2s | 37 с | 431.4s divider·речь, 435.3s checklist·речь, 462.6s quote·речь |
| 12 | CTA | 469.1s | 33 с | 468.6s divider·речь, 473.8s quote·речь, 480.4s outro·речь |

Событий графики в таблице: 47 (разделители блоков и вставки; внутренние появления — пункты чек-листа, столбцы диаграммы, метки — идут сверх этого). Средний интервал 10.9 с, максимальная пауза 41.3 с.

**Отклонение от §12.13 (сознательное):** норма ждёт новое событие каждые 2–3 с и паузу не больше 4 с. Материал — говорящая голова 1080p, камера отключена (§7.1, апскейл запрещён), а уложиться в норму можно только держа плашку в кадре почти непрерывно: это превратило бы объяснение в инфографику с титрами. Плотность оставлена ниже нормы осознанно; выравнивать её следует сценарием, а не более частой графикой поверх речи.

## 3. Не проверялось

- VMAF против эталона в 4K и дисперсия лапласиана (резкость): для этого дубля 4K-эталона нет — материал снят в 1080p, поэтому сравнение с 4K-референсом невозможно (§12.7–12.8).
- Приём «слово за головой» (§8) в этом прогоне не применялся: графика рисуется из плана сценария (разделители блоков и вставки), маска человека и слой за спиной не считались.
- Камера (наезды, отъезды, split, кружок): отключена по решению владельца — материал 1080p, апскейл запрещён §7.1. Задокументированное отклонение.
- Битрейт: 29.97 Mbps. Lossless-мастер держит 70.45 Мбит/с — это потолок материала.
- Режим `--bitrate-mode cbr` собран и замерен на отдельном прогоне: он даёт ровно 30.00 Мбит/с, но SSIM относительно мастера **ниже** (0.999664 → 0.998359, PSNR 34.7 → 27.8 дБ) — малый буфер CBR экономит биты на сложных кадрах. Поэтому по умолчанию режим `abr`.

## Таблица графики (§9.5)

| время | слова | элемент | анимация | звук | примечание |
|---|---|---|---|---|---|
| 0.6 | здравствуйте | hook | титр имени и должности | pop |  |
| 7.0 | крипта на балансе | title | титр всплывает сверху | impact |  |
| 13.9 | разлоки | table | строки таблицы появляются по одной | pop |  |
| 21.1 |  | chips | подписи появляются по одной | pop |  |
| 30.1 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 42.6 |  | divider02 | жидкое стекло: размытие и плашка по центру | pop |  |
| 45.8 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 52.4 | 1 сентября 2026 → 15 октября 2026 | timeline | даты и требования по очереди | pop |  |
| 63.7 | инфляция 3,7 | stat | счётчик добегает до значения из текста | click |  |
| 79.8 |  | divider03 | жидкое стекло: размытие и плашка по центру | pop |  |
| 83.4 | 1 сентября 2026 → 15 октября 2026 | timeline | даты и требования по очереди | pop |  |
| 105.0 | инфляция 3,7 | stat | счётчик добегает до значения из текста | click |  |
| 113.8 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 122.3 |  | divider04 | жидкое стекло: размытие и плашка по центру | pop |  |
| 125.5 | разлоки | table | строки таблицы появляются по одной | pop |  |
| 134.5 | инфляция 3,7 | stat | счётчик добегает до значения из текста | click |  |
| 159.2 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 173.5 |  | divider05 | жидкое стекло: размытие и плашка по центру | pop |  |
| 177.1 | 1 сентября 2026 → 15 октября 2026 | timeline | даты и требования по очереди | pop |  |
| 185.0 |  | chips | подписи появляются по одной | pop |  |
| 200.2 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 213.0 |  | divider06 | жидкое стекло: размытие и плашка по центру | pop |  |
| 216.2 |  | chips | подписи появляются по одной | pop |  |
| 257.5 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 263.5 |  | divider07 | жидкое стекло: размытие и плашка по центру | pop |  |
| 266.7 | 1 сентября 2026 → 15 октября 2026 | timeline | даты и требования по очереди | pop |  |
| 282.0 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 288.6 |  | chips | подписи появляются по одной | pop |  |
| 304.7 |  | divider08 | жидкое стекло: размытие и плашка по центру | pop |  |
| 308.1 | разлоки | table | строки таблицы появляются по одной | pop |  |
| 317.7 | инфляция 3,7 | stat | счётчик добегает до значения из текста | click |  |
| 341.6 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 348.7 |  | divider09 | жидкое стекло: размытие и плашка по центру | pop |  |
| 352.1 | 1 сентября 2026 → 15 октября 2026 | timeline | даты и требования по очереди | pop |  |
| 362.1 | инфляция 3,7 | stat | счётчик добегает до значения из текста | click |  |
| 385.9 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 392.0 |  | divider10 | жидкое стекло: размытие и плашка по центру | pop |  |
| 395.3 | разлоки | table | строки таблицы появляются по одной | pop |  |
| 408.3 | инфляция 3,7 | stat | счётчик добегает до значения из текста | click |  |
| 425.3 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 431.4 |  | divider11 | жидкое стекло: размытие и плашка по центру | pop |  |
| 435.3 | что делать трейдеру | checklist | пункты с галочками на своих словах | pop |  |
| 462.6 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 468.6 |  | divider12 | жидкое стекло: размытие и плашка по центру | pop |  |
| 473.8 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 480.4 | подпишитесь на Rudstock Crypto | outro | кадр сдвигается, панель подписки справа | impact |  |
| 501.9 |  | endcard | фирменная заставка после речи | impact |  |

## EDL (первые 20 склеек)

| # | Фраза | Вход | Выход | Длина | Причина |
|---|---|---|---|---|---|
| 1 | Биткоин закрывает неделю на 82 671 доллара, плюс 1,3% за сут | 7.680 | 13.570 | 5.89 | waveform onset/offset snap (part 1/3) |
| 2 | … | 13.940 | 20.250 | 6.31 | continuation after pause trim (part 2/3) |
| 3 | … | 20.630 | 25.010 | 4.38 | continuation after pause trim (part 3/3) |
| 4 | Цена стоит, а институциональный поток уходит. Это не противо | 25.730 | 31.120 | 5.39 | waveform onset/offset snap |
| 5 | Первый– краткосрочная торговля, где рынок собрал миллиард до | 30.970 | 36.590 | 5.62 | waveform onset/offset snap |
| 6 | Второй– это распределение капитала, где фонды сокращают пози | 37.030 | 46.740 | 9.71 | waveform onset/offset snap |
| 7 | Разберем, что произошло за неделю, какие разводки прошли и ч | 47.220 | 52.510 | 5.29 | waveform onset/offset snap |
| 8 | Внутри недели биткоин прошел полный цикл. | 55.130 | 57.240 | 2.11 | waveform onset/offset snap |
| 9 | 15 октября в 16.54 по Москве цена опускалась до 80 тысяч дол | 57.690 | 62.770 | 5.08 | waveform onset/offset snap (part 1/3) |
| 10 | … | 63.130 | 64.330 | 1.20 | continuation after pause trim (part 2/3) |
| 11 | Через 49 минут вернулась к 81 568 долларам. | 64.850 | 65.960 | 1.11 | waveform onset/offset snap (part 1/2) |
| 12 | … | 67.590 | 71.990 | 4.40 | continuation after pause trim (part 2/2) |
| 13 | К 16 октября отскочила к 82 500 долларам. | 72.570 | 73.470 | 0.90 | waveform onset/offset snap (part 1/2) |
| 14 | … | 74.850 | 78.140 | 3.29 | continuation after pause trim (part 2/2) |
| 15 | Трейдеры за сутки потеряли около 1 миллиарда долларов на лик | 78.850 | 82.340 | 3.49 | waveform onset/offset snap (part 1/2) |
| 16 | … | 82.920 | 88.250 | 5.33 | continuation after pause trim (part 2/2) |
| 17 | В таких условиях решение принимается не по свече, а по струк | 87.780 | 88.270 | 0.49 | waveform onset/offset snap (part 1/2) |
| 18 | … | 88.760 | 94.350 | 5.59 | continuation after pause trim (part 2/2) |
| 19 | Дальше по неделе были инфляция, разводки и регуляторика. | 94.850 | 98.110 | 3.26 | waveform onset/offset snap |
| 20 | Идем по порядку. | 101.300 | 102.260 | 0.96 | waveform onset/offset snap |

Всего склеек: 134.
