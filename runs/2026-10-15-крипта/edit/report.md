# Отчёт §13 — прогон `2026-10-15-крипта`

- Исходник: `2026-10-15 13-54-01.mp4` (505.9 с монтажа из 97 склеек)
- Файл: `runs\2026-10-15-крипта\out\final.mp4` — h264 / yuv420p / 1920x1080 / 30.000 fps / duration 511.000 s
- Вердикт приёмки: **PASS** (8 прошло, 0 провалилось)
- Паспорт: 16:9, 30 fps, субтитры выключены

## 1. Проверено вживую (с цифрами)

| Проверка | Статус | Измерено | Цель |
|---|---|---|---|
| video | PASS | h264 / yuv420p / 1920x1080 / 30.000 fps / duration 511.000 s | h264 / yuv420p / 1920x1080 / 30 fps / duration = EDL sum +- 0.15 s |
| color_tags | PASS | color_range=tv / color_space=bt709 / color_primaries=bt709 / color_trc=bt709 | tv / bt709 / bt709 / bt709 (all four tags mandatory) |
| bitrate | PASS | 29.99 Mbps | >= 16 Mbps (target ~30 Mbps) |
| audio | PASS | aac / -14.30 LUFS / true peak -2.30 dBTP | aac / -14 LUFS +- 0.5 LU / true peak <= -0.85 dBTP |
| subtitles | PASS | comp/index.html: 0x class="subs", 0x class="sub clip"; edit/subtitles.json: absent | no class="subs", no class="sub clip", no edit/subtitles.json (spec sec. 5) |
| layer_alpha | PASS | empty 42/120 frames; visible 78/120 frames; min margins 5.00/5.00/7.50/12.87 % | >= 1 empty frame (max alpha == 0); graphics present (max alpha > 0.12); opaque bbox >= 3.5% of width and >= 7% of height from the edges |
| black_frames | PASS | first_frame mean luma 182.10/255; last_frame mean luma 29.58/255 | first and last frame mean luma > 8/255 |
| source | PASS | readable: D:\LLM\video-montage-template\takes\2026-10-15 13-54-01.mp4; duration: source 604.133 s vs final 511.000 s; color_tags: source and final tags agree (or source tags are unset) | readable; source duration >= final duration; colour tags consistent |
| frame_sheet | PASS | 41/41 stills in frames/ | one still per graphics element, after it settled |
| audio_sync | PASS | lag +0.00 ms (correlation 1.0000) | |lag| <= 5.0 ms |
| levels | PASS | paired on 9 EDL frames: source 0.02% -> final 0.01% clipped at 255 (grade adds -0.01 pp); p50 183-193; mean luma change 5.54/255 — 22 frame(s) skipped: graphics on screen (§9.3 plates are white by design) | grade adds <= 0.3 pp of clipping |
| jitter | PASS | max centroid drift 0.000 px/frame per element (4 element(s), ) | <= 0.25 px/frame on hold |
| sfx_placement | PASS | 44/44 events raise the level (median +2.4 dB) | each planned event louder than the voice-only track in its window |
| determinism | PASS | no infinite animation, no random/time source; 3 deterministic tl.call steps | no infinite, Math.random, Date.now, performance.now |
| copy_quality | PASS | 218 text node(s), 0 with an ellipsis; 5 line(s) rewritten to fit; copy: 2026-10-15-крипта-inserts.json | 0 ellipses on screen; long lines are rewritten, not cut short |
| retakes | PASS | 97 clips checked; 0 duplicate pair(s) left | 0 repeated or aborted phrases (build_edl.py + build_words_dtw.py remove them) |
| face_safe | PASS | face box x45% y28% 16×38%; 23 frame(s) measured, 1 exempt (liquid-glass stage); no graphics on the face | 0 frames with a graphic over the face outside the declared glass stage |

Резка по волне (`check_edl.py`):

| Метрика | Значение |
|---|---|
| segments | 97 |
| duration_s | 505.93 |
| threshold_rms | 0.01147 |
| dead_air_total_s | 14.51 |
| dead_air_lead_median_s | 0.08 |
| dead_air_lead_max_s | 0.09 |
| dead_air_tail_median_s | 0.06 |
| dead_air_tail_max_s | 1.65 |
| cut_in_lands_on_speech | 9 |
| cut_out_lands_on_speech | 13 |
| internal_pauses_over_max | 56 |

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
| chips | 13.90 | pop-panel.mp3 | pop | 13.90 |
| quotes | 27.10 | pop-panel.mp3 | pop | 27.10 |
| divider02 | 43.80 | pop-panel.mp3 | pop | 43.80 |
| chips | 47.00 | pop-panel.mp3 | pop | 47.00 |
| chips | 74.00 | pop-panel.mp3 | pop | 74.00 |
| divider03 | 85.20 | pop-panel.mp3 | pop | 85.20 |
| diagram | 88.30 | pop-panel.mp3 | pop | 88.30 |
| quote | 120.60 | pop-panel.mp3 | pop | 120.60 |
| divider04 | 126.60 | pop-panel.mp3 | pop | 126.60 |
| timeline | 129.90 | pop-panel.mp3 | pop | 129.90 |
| chips | 139.60 | pop-panel.mp3 | pop | 139.60 |
| divider05 | 170.00 | pop-panel.mp3 | pop | 170.00 |
| stat | 175.60 | click-04.mp3 | click | 175.60 |
| chart | 200.70 | pop-panel.mp3 | pop | 200.70 |
| divider06 | 218.50 | pop-panel.mp3 | pop | 218.50 |
| premium | 222.30 | pop-panel.mp3 | pop | 222.30 |
| quote | 229.90 | pop-panel.mp3 | pop | 229.90 |
| chips | 240.10 | pop-panel.mp3 | pop | 240.10 |
| divider07 | 261.80 | pop-panel.mp3 | pop | 261.80 |
| table | 265.10 | pop-panel.mp3 | pop | 265.10 |
| counter | 287.30 | click-04.mp3 | click | 287.30 |
| quote | 294.80 | pop-panel.mp3 | pop | 294.80 |
| divider08 | 300.80 | pop-panel.mp3 | pop | 300.80 |
| scenario | 304.00 | pop-panel.mp3 | pop | 304.00 |
| quote | 330.90 | pop-panel.mp3 | pop | 330.90 |
| divider09 | 340.50 | pop-panel.mp3 | pop | 340.50 |
| scenario | 343.70 | pop-panel.mp3 | pop | 343.70 |
| funnel | 353.90 | pop-panel.mp3 | pop | 353.90 |
| divider10 | 380.10 | pop-panel.mp3 | pop | 380.10 |
| checklist | 383.50 | pop-panel.mp3 | pop | 383.50 |
| item | 384.61 | click-04.mp3 | click | 384.61 |
| item | 386.31 | click-04.mp3 | click | 386.31 |
| item | 388.01 | click-04.mp3 | click | 388.01 |
| item | 389.71 | click-04.mp3 | click | 389.71 |
| item | 391.41 | click-04.mp3 | click | 391.41 |
| chips | 397.00 | pop-panel.mp3 | pop | 397.00 |
| divider11 | 422.10 | pop-panel.mp3 | pop | 422.10 |
| miners | 431.50 | click-04.mp3 | click | 431.50 |
| steps | 452.80 | pop-panel.mp3 | pop | 452.80 |
| divider12 | 467.80 | pop-panel.mp3 | pop | 467.80 |
| quote | 471.00 | pop-panel.mp3 | pop | 471.00 |
| outro | 496.30 | impact-word.mp3 | impact | 496.30 |

## Сценарий и вставки (§9.4–9.5)

Блоков в сценарии: 12; привязано к записи: 12; плановая сумма 618 с при фактических 506 с.

| # | Блок | На таймлайне | Длина | Что нарисовано |
|---|---|---|---|---|
| 1 | Хук: правила яснее, цена ниже | 0.3s | 44 с | 7.0s title·речь, 13.9s chips·речь, 27.1s quotes·речь |
| 2 | Что за конференция и кто в зале | 43.9s | 41 с | 43.8s divider·речь, 47.0s chips·речь, 74.0s chips·речь |
| 3 | Четыре блока: онбординг, KYT, Travel Rule, стек | 85.2s | 42 с | 85.2s divider·речь, 88.3s diagram·речь, 120.6s quote·речь |
| 4 | Почему это тектонический сдвиг | 126.8s | 43 с | 126.6s divider·речь, 129.9s timeline·речь, 139.6s chips·речь, 146.9s compare·речь |
| 5 | Глобальный фон: инфляция 3,7% и оттоки ETF | 170.2s | 48 с | 170.0s divider·речь, 175.6s stat·речь, 200.7s chart·речь |
| 6 | Coinbase Premium 20 дней в минусе | 218.6s | 43 с | 218.5s divider·речь, 222.3s premium·речь, 229.9s quote·речь, 240.1s chips·речь |
| 7 | Разлоки съедают ликвидность | 261.9s | 39 с | 261.8s divider·речь, 265.1s table·речь, 287.3s counter·речь, 294.8s quote·речь |
| 8 | Bull-сценарий: легальный мост | 300.9s | 40 с | 300.8s divider·речь, 304.0s scenario·речь, 330.9s quote·речь |
| 9 | Bear-сценарий: комплаенс как фильтр | 340.6s | 40 с | 340.5s divider·речь, 343.7s scenario·речь, 353.9s funnel·речь |
| 10 | Что делать трейдеру прямо сейчас | 380.4s | 42 с | 380.1s divider·речь, 383.5s checklist·речь, 397.0s chips·речь |
| 11 | Российский контекст: майнеры и AML | 422.5s | 45 с | 422.1s divider·речь, 431.5s miners·речь, 452.8s steps·речь |
| 12 | CTA | 467.8s | 38 с | 467.8s divider·речь, 471.0s quote·речь, 496.3s outro·речь |

Событий графики в таблице: 41 (разделители блоков и вставки; внутренние появления — пункты чек-листа, столбцы диаграммы, метки — идут сверх этого). Средний интервал 12.6 с, максимальная пауза 32.3 с.

**Отклонение от §12.13 (сознательное):** норма ждёт новое событие каждые 2–3 с и паузу не больше 4 с. Материал — говорящая голова 1080p, камера отключена (§7.1, апскейл запрещён), а уложиться в норму можно только держа плашку в кадре почти непрерывно: это превратило бы объяснение в инфографику с титрами. Плотность оставлена ниже нормы осознанно; выравнивать её следует сценарием, а не более частой графикой поверх речи.

## 3. Не проверялось

- VMAF против эталона в 4K и дисперсия лапласиана (резкость): для этого дубля 4K-эталона нет — материал снят в 1080p, поэтому сравнение с 4K-референсом невозможно (§12.7–12.8).
- Приём «слово за головой» (§8) в этом прогоне не применялся: графика рисуется из плана сценария (разделители блоков и вставки), маска человека и слой за спиной не считались.
- Камера (наезды, отъезды, split, кружок): отключена по решению владельца — материал 1080p, апскейл запрещён §7.1. Задокументированное отклонение.
- Битрейт: 29.99 Mbps. Lossless-мастер держит 65.12 Мбит/с — это потолок материала.
- Режим `--bitrate-mode cbr` собран и замерен на отдельном прогоне: он даёт ровно 30.00 Мбит/с, но SSIM относительно мастера **ниже** (0.999664 → 0.998359, PSNR 34.7 → 27.8 дБ) — малый буфер CBR экономит биты на сложных кадрах. Поэтому по умолчанию режим `abr`.

## Таблица графики (§9.5)

| время | слова | элемент | анимация | звук | примечание |
|---|---|---|---|---|---|
| 0.6 | здравствуйте | hook | титр имени и должности | pop |  |
| 7.0 | крипта на балансе | title | титр всплывает сверху | impact |  |
| 13.9 | банки, брокеры, биржи, обменники и депозитарии | chips | подписи появляются по одной | pop |  |
| 27.1 | биткоин 81 174, эфир 2 373 | quotes | строки котировок по очереди | pop |  |
| 43.8 |  | divider02 | жидкое стекло: размытие и плашка по центру | pop |  |
| 47.0 | организаторы и генеральный партнёр | chips | подписи появляются по одной | pop |  |
| 74.0 | Минфин, ЦБ, АБР и ВЭБ.РФ | chips | подписи появляются по одной | pop |  |
| 85.2 |  | divider03 | жидкое стекло: размытие и плашка по центру | pop |  |
| 88.3 | онбординг, KYT, Travel Rule и стек | diagram | шаги появляются по очереди | pop |  |
| 120.6 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 126.6 |  | divider04 | жидкое стекло: размытие и плашка по центру | pop |  |
| 129.9 | первое сентября и пятнадцатое октября | timeline | даты и требования по очереди | pop |  |
| 139.6 |  | chips | подписи появляются по одной | pop |  |
| 146.9 | раньше и теперь | compare | было и стало, вторая ячейка подсвечена | pop |  |
| 170.0 |  | divider05 | жидкое стекло: размытие и плашка по центру | pop |  |
| 175.6 | инфляция 3,7 против 3,6 | stat | счётчик добегает до значения из текста | click |  |
| 200.7 | оттоки из ETF | chart | столбцы вырастают по значениям | pop |  |
| 218.5 |  | divider06 | жидкое стекло: размытие и плашка по центру | pop |  |
| 222.3 | минус 0,1398 процента, двадцать дней | premium | двадцать меток под нулевой линией | pop |  |
| 229.9 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 240.1 |  | chips | подписи появляются по одной | pop |  |
| 261.8 |  | divider07 | жидкое стекло: размытие и плашка по центру | pop |  |
| 265.1 | разлоки | table | строки таблицы появляются по одной | pop |  |
| 287.3 | доля акций cerebras | counter | счётчик добегает до значения из текста | click |  |
| 294.8 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 300.8 |  | divider08 | жидкое стекло: размытие и плашка по центру | pop |  |
| 304.0 | bull | scenario | карточка сценария и её пункты | pop |  |
| 330.9 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 340.5 |  | divider09 | жидкое стекло: размытие и плашка по центру | pop |  |
| 343.7 | bear | scenario | карточка сценария и её пункты | pop |  |
| 353.9 | мелкие не выдерживают | funnel | воронка сужается от многих к нескольким | pop |  |
| 380.1 |  | divider10 | жидкое стекло: размытие и плашка по центру | pop |  |
| 383.5 | что делать трейдеру | checklist | пункты с галочками на своих словах | pop |  |
| 397.0 |  | chips | подписи появляются по одной | pop |  |
| 422.1 |  | divider11 | жидкое стекло: размытие и плашка по центру | pop |  |
| 431.5 | 1473 участника | miners | счётчик добегает до значения из текста | click |  |
| 452.8 | сначала правила, потом реестр | steps | шаги появляются по очереди | pop |  |
| 467.8 |  | divider12 | жидкое стекло: размытие и плашка по центру | pop |  |
| 471.0 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |  |
| 496.3 | подпишитесь на Rudstock Crypto | outro | кадр сдвигается, панель подписки справа | impact |  |
| 505.6 |  | endcard | фирменная заставка после речи | impact |  |

## EDL (первые 20 склеек)

| # | Фраза | Вход | Выход | Длина | Причина |
|---|---|---|---|---|---|
| 1 | С 1 сентября 2026 года российский криптовалютный рынок офици | 19.560 | 30.080 | 10.52 | waveform onset/offset snap (part 1/3) |
| 2 | … | 30.450 | 36.140 | 5.69 | continuation after pause trim (part 2/3) |
| 3 | … | 37.160 | 42.090 | 4.93 | continuation after pause trim (part 3/3) |
| 4 | Конференция называется «Крипта на балансе. Запуск по новым п | 42.620 | 46.220 | 3.60 | waveform onset/offset snap (part 1/2) |
| 5 | … | 46.630 | 56.000 | 9.37 | continuation after pause trim (part 2/2) |
| 6 | То есть правила становятся понятнее, а рынок дешевле. И это  | 56.390 | 66.090 | 9.70 | waveform onset/offset snap |
| 7 | Организаторы– банковское обозрение и проф. ЦФА, генеральный  | 68.050 | 78.590 | 10.54 | waveform onset/offset snap (part 1/2) |
| 8 | … | 79.080 | 88.290 | 9.21 | continuation after pause trim (part 2/2) |
| 9 | В анонсах прямо написано. Впервые собирают весь контур рынка | 88.850 | 95.520 | 6.67 | waveform onset/offset snap (part 1/2) |
| 10 | Для читателей действует скидка 10% по промокоду «Партнер». С | 96.220 | 104.720 | 8.50 | waveform onset/offset snap (part 1/2) |
| 11 | … | 105.220 | 111.690 | 6.47 | continuation after pause trim (part 2/2) |
| 12 | Ключевые темы. Анбординг клиента, KYT, Travel Rule и стэк-те | 117.640 | 122.210 | 4.57 | waveform onset/offset snap (part 1/3) |
| 13 | … | 122.580 | 126.970 | 4.39 | continuation after pause trim (part 2/3) |
| 14 | … | 127.390 | 130.700 | 3.31 | continuation after pause trim (part 3/3) |
| 15 | KYT– New York Transaction– проверка транзакций. Откуда пришл | 130.480 | 138.080 | 7.60 | waveform onset/offset snap (part 1/2) |
| 16 | Travel Rule– правила передачи данных об отправителе и получа | 138.580 | 144.120 | 5.54 | waveform onset/offset snap (part 1/2) |
| 17 | … | 144.500 | 149.210 | 4.71 | continuation after pause trim (part 2/2) |
| 18 | И стэк– технологическая инфраструктура. Провайдеры, аналитик | 149.650 | 152.150 | 2.50 | waveform onset/offset snap (part 1/2) |
| 19 | … | 152.610 | 161.430 | 8.82 | continuation after pause trim (part 2/2) |
| 20 | Почему это важно? | 165.910 | 167.260 | 1.35 | waveform onset/offset snap |

Всего склеек: 97.
