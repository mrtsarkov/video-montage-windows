# Отчёт §13 — прогон `v3`

- Исходник: `2026-05-28 13-20-36.mp4` (336.9 с монтажа из 81 склеек)
- Файл: `runs\v3\out\final.mp4` — h264 / yuv420p / 1920x1080 / 30.000 fps / duration 336.933 s
- Вердикт приёмки: **PASS** (8 прошло, 0 провалилось)
- Паспорт: 16:9, 30 fps, субтитры выключены

## 1. Проверено вживую (с цифрами)

| Проверка | Статус | Измерено | Цель |
|---|---|---|---|
| video | PASS | h264 / yuv420p / 1920x1080 / 30.000 fps / duration 336.933 s | h264 / yuv420p / 1920x1080 / 30 fps / duration = EDL sum +- 0.15 s |
| color_tags | PASS | color_range=tv / color_space=bt709 / color_primaries=bt709 / color_trc=bt709 | tv / bt709 / bt709 / bt709 (all four tags mandatory) |
| bitrate | PASS | 20.03 Mbps | >= 16 Mbps (target ~30 Mbps) |
| audio | PASS | aac / -14.20 LUFS / true peak -2.20 dBTP | aac / -14 LUFS +- 0.5 LU / true peak <= -0.85 dBTP |
| subtitles | PASS | comp/index.html: 0x class="subs", 0x class="sub clip"; edit/subtitles.json: absent | no class="subs", no class="sub clip", no edit/subtitles.json (spec sec. 5) |
| layer_alpha | PASS | empty 70/84 frames; visible 14/84 frames; min margins 5.00/5.00/13.98/60.83 % | >= 1 empty frame (max alpha == 0); graphics present (max alpha > 0.12); opaque bbox >= 3.5% of width and >= 7% of height from the edges |
| black_frames | PASS | first_frame mean luma 178.37/255; last_frame mean luma 181.01/255 | first and last frame mean luma > 8/255 |
| source | PASS | readable: D:\LLM\video-montage-template\takes\2026-05-28 13-20-36.mp4; duration: source 384.900 s vs final 336.933 s; color_tags: source and final tags agree (or source tags are unset) | readable; source duration >= final duration; colour tags consistent |
| frame_sheet | PASS | 8/8 stills in frames/ | one still per graphics element, after it settled |
| audio_sync | PASS | lag +0.00 ms (correlation 1.0000) | |lag| <= 5.0 ms |
| levels | PASS | paired on 27 EDL frames: source 0.98% -> final 0.98% clipped at 255 (grade adds +0.01 pp); p50 98-252; mean luma change 2.91/255 | grade adds <= 0.3 pp of clipping |
| jitter | PASS | max centroid drift 0.000 px/frame per element (4 element(s), ) | <= 0.25 px/frame on hold |
| sfx_placement | PASS | 15/15 events raise the level (median +3.3 dB) | each planned event louder than the voice-only track in its window |
| determinism | PASS | no infinite animation, no random/time source; 8 deterministic tl.call steps | no infinite, Math.random, Date.now, performance.now |

Резка по волне (`check_edl.py`):

| Метрика | Значение |
|---|---|
| segments | 81 |
| duration_s | 336.91 |
| threshold_rms | 0.00934 |
| dead_air_total_s | 9.48 |
| dead_air_lead_median_s | 0.06 |
| dead_air_lead_max_s | 0.09 |
| dead_air_tail_median_s | 0.06 |
| dead_air_tail_max_s | 0.06 |
| cut_in_lands_on_speech | 4 |
| cut_out_lands_on_speech | 6 |
| internal_pauses_over_max | 0 |

## 2. Сверено по коду и документации

- Субтитры: `subtitles: false` в пульте, 0 блоков `.sub` в композиции, `subtitles.json` нет (§5).
- Апскейла нет: мастер собран `trim` + `concat` + наложение слоя, без `scale` и `crop` (§7.1).
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
| hook | 0.10 | pop-panel.mp3 | pop | 0.10 |
| word | 11.00 | impact-word.mp3 | impact | 11.00 |
| calendar | 11.00 | pop-panel.mp3 | pop | 11.00 |
| checklist | 28.90 | pop-panel.mp3 | pop | 28.90 |
| item | 29.27 | click-04.mp3 | click | 29.27 |
| item | 29.77 | click-04.mp3 | click | 29.77 |
| item | 30.27 | click-04.mp3 | click | 30.27 |
| chat | 81.60 | pop-panel.mp3 | pop | 81.60 |
| counter | 183.10 | click-04.mp3 | click | 183.10 |
| item | 183.37 | click-04.mp3 | click | 183.37 |
| scale | 290.10 | pop-panel.mp3 | pop | 290.10 |
| stepper | 320.40 | pop-panel.mp3 | pop | 320.40 |
| item | 320.95 | click-04.mp3 | click | 320.95 |
| item | 321.55 | click-04.mp3 | click | 321.55 |
| item | 322.15 | click-04.mp3 | click | 322.15 |

## 3. Не проверялось

- VMAF против эталона в 4K и дисперсия лапласиана (резкость): для этого дубля 4K-эталона нет — материал снят в 1080p, поэтому сравнение с 4K-референсом невозможно (§12.7–12.8).
- Маска человека `remove-background` и приём «слово за головой» (§8) — не выполнялись (фаза 3).
- Камера (наезды, отъезды, split, кружок): отключена по решению владельца — материал 1080p, апскейл запрещён §7.1. Задокументированное отклонение.
- Битрейт: доставлено ~20 Мбит/с вместо ~30. Lossless-мастер весит 19.31 Мбит/с — это потолок материала, а не экономия. Режим `--bitrate-mode cbr` собран и замерен на этом же мастере: 30.00 Мбит/с, файл в 1.5 раза больше, но SSIM относительно мастера **ниже** (0.999664 → 0.998359, PSNR 34.7 → 27.8 дБ): малый буфер CBR экономит биты на сложных кадрах. Поэтому по умолчанию режим `abr`.

## Таблица графики (§9.5)

| время | слова | элемент | анимация | звук |
|---|---|---|---|---|
| 0.1 | Господа, приветствую. | hook | Контент-завод для советника | — |
| 11.0 | сразу покажу а есть собственный сервис я для своей п | word | КОНТЕНТ-ЗАВОД | — |
| 11.0 | сразу покажу а есть собственный сервис я для своей п | calendar | Календарь событий | — |
| 28.9 | а в нем в каждую дату заполнены уже заранее какие -т | checklist | Типы событий | — |
| 81.6 | Дальше, соответственно, если финансовый советник инт | chat | Генерация поста | — |
| 183.1 | дальше ввожу какие -то метрики, все это можно также  | counter | Метрики дня | — |
| 290.1 | Искусственный интеллект посмотрит базу, посмотрит, в | scale | AI-анализ продукта | — |
| 320.4 | локальными моделями, если у нас есть ограничения по  | stepper | Локальные / внешние модели | — |

## EDL (первые 20 склеек)

| # | Фраза | Вход | Выход | Длина | Причина |
|---|---|---|---|---|---|
| 1 | Господа, приветствую. | 1.130 | 2.570 | 1.44 | waveform onset/offset snap |
| 2 | Продолжение нашего разговора. | 2.410 | 2.790 | 0.38 | waveform onset/offset snap (part 1/2) |
| 3 | … | 3.230 | 5.040 | 1.81 | continuation after pause trim (part 2/2) |
| 4 | Я как в простоклашенной здесь и там вещаю, покажу вам, как э | 5.750 | 11.620 | 5.87 | waveform onset/offset snap (part 1/2) |
| 5 | … | 11.820 | 12.880 | 1.06 | continuation after pause trim (part 2/2) |
| 6 | сразу покажу а есть собственный сервис я для своей практики  | 14.590 | 15.640 | 1.05 | waveform onset/offset snap (part 1/4) |
| 7 | … | 15.930 | 21.890 | 5.96 | continuation after pause trim (part 2/4) |
| 8 | … | 22.330 | 25.480 | 3.15 | continuation after pause trim (part 3/4) |
| 9 | … | 25.900 | 33.650 | 7.75 | continuation after pause trim (part 4/4) |
| 10 | а в нем в каждую дату заполнены уже заранее какие -то событи | 34.190 | 35.090 | 0.90 | waveform onset/offset snap (part 1/7) |
| 11 | … | 35.410 | 38.410 | 3.00 | continuation after pause trim (part 2/7) |
| 12 | … | 38.760 | 46.540 | 7.78 | continuation after pause trim (part 3/7) |
| 13 | … | 46.910 | 50.040 | 3.13 | continuation after pause trim (part 4/7) |
| 14 | … | 50.330 | 55.130 | 4.80 | continuation after pause trim (part 5/7) |
| 15 | … | 55.390 | 58.310 | 2.92 | continuation after pause trim (part 6/7) |
| 16 | … | 58.650 | 61.640 | 2.99 | continuation after pause trim (part 7/7) |
| 17 | тыкайте день у вас здесь отображается список этих мероприяти | 62.050 | 66.800 | 4.75 | waveform onset/offset snap (part 1/3) |
| 18 | … | 67.200 | 72.820 | 5.62 | continuation after pause trim (part 2/3) |
| 19 | … | 73.290 | 76.990 | 3.70 | continuation after pause trim (part 3/3) |
| 20 | Из его базы наверняка там тоже введу за полностью карточки. | 77.720 | 81.680 | 3.96 | waveform onset/offset snap |

Всего склеек: 81.
