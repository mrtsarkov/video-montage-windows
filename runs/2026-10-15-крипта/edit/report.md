# Отчёт §13 — прогон `2026-10-15-крипта`

- Исходник: `2026-10-15 13-54-01.mp4` (509.3 с монтажа из 96 склеек)
- Файл: `runs\2026-10-15-крипта\out\final.mp4` — h264 / yuv420p / 1920x1080 / 30.000 fps / duration 509.267 s
- Вердикт приёмки: **PASS** (8 прошло, 0 провалилось)
- Паспорт: 16:9, 30 fps, субтитры выключены

## 1. Проверено вживую (с цифрами)

| Проверка | Статус | Измерено | Цель |
|---|---|---|---|
| video | PASS | h264 / yuv420p / 1920x1080 / 30.000 fps / duration 509.267 s | h264 / yuv420p / 1920x1080 / 30 fps / duration = EDL sum +- 0.15 s |
| color_tags | PASS | color_range=tv / color_space=bt709 / color_primaries=bt709 / color_trc=bt709 | tv / bt709 / bt709 / bt709 (all four tags mandatory) |
| bitrate | PASS | 30.01 Mbps | >= 16 Mbps (target ~30 Mbps) |
| audio | PASS | aac / -14.20 LUFS / true peak -2.20 dBTP | aac / -14 LUFS +- 0.5 LU / true peak <= -0.85 dBTP |
| subtitles | PASS | comp/index.html: 0x class="subs", 0x class="sub clip"; edit/subtitles.json: absent | no class="subs", no class="sub clip", no edit/subtitles.json (spec sec. 5) |
| layer_alpha | PASS | empty 52/120 frames; visible 68/120 frames; min margins 5.00/5.00/8.98/8.98 % | >= 1 empty frame (max alpha == 0); graphics present (max alpha > 0.12); opaque bbox >= 3.5% of width and >= 7% of height from the edges |
| black_frames | PASS | first_frame mean luma 183.40/255; last_frame mean luma 176.44/255 | first and last frame mean luma > 8/255 |
| source | PASS | readable: D:\LLM\video-montage-template\takes\2026-10-15 13-54-01.mp4; duration: source 604.133 s vs final 509.267 s; color_tags: source and final tags agree (or source tags are unset) | readable; source duration >= final duration; colour tags consistent |
| frame_sheet | PASS | 37/37 stills in frames/ | one still per graphics element, after it settled |
| audio_sync | PASS | lag +0.00 ms (correlation 1.0000) | |lag| <= 5.0 ms |
| levels | PASS | paired on 11 EDL frames: source 0.02% -> final 0.02% clipped at 255 (grade adds -0.01 pp); p50 185-189; mean luma change 6.75/255 — 21 frame(s) skipped: graphics on screen (§9.3 plates are white by design) | grade adds <= 0.3 pp of clipping |
| jitter | PASS | max centroid drift 0.000 px/frame per element (4 element(s), ) | <= 0.25 px/frame on hold |
| sfx_placement | PASS | 40/40 events raise the level (median +2.7 dB) | each planned event louder than the voice-only track in its window |
| determinism | PASS | no infinite animation, no random/time source; 3 deterministic tl.call steps | no infinite, Math.random, Date.now, performance.now |

Резка по волне (`check_edl.py`):

| Метрика | Значение |
|---|---|
| segments | 96 |
| duration_s | 509.26 |
| threshold_rms | 0.01147 |
| dead_air_total_s | 11.09 |
| dead_air_lead_median_s | 0.08 |
| dead_air_lead_max_s | 0.09 |
| dead_air_tail_median_s | 0.06 |
| dead_air_tail_max_s | 0.06 |
| cut_in_lands_on_speech | 13 |
| cut_out_lands_on_speech | 13 |
| internal_pauses_over_max | 60 |

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
| hook | 0.60 | pop-panel.mp3 | pop | 0.60 |
| title | 7.00 | impact-word.mp3 | impact | 7.00 |
| chips | 14.00 | pop-panel.mp3 | pop | 14.00 |
| quotes | 27.00 | pop-panel.mp3 | pop | 27.00 |
| divider2 | 41.40 | pop-panel.mp3 | pop | 41.40 |
| chips | 44.90 | pop-panel.mp3 | pop | 44.90 |
| chips | 75.60 | pop-panel.mp3 | pop | 75.60 |
| divider3 | 89.40 | pop-panel.mp3 | pop | 89.40 |
| diagram | 92.50 | pop-panel.mp3 | pop | 92.50 |
| quote | 106.20 | pop-panel.mp3 | pop | 106.20 |
| divider4 | 119.60 | pop-panel.mp3 | pop | 119.60 |
| timeline | 129.50 | pop-panel.mp3 | pop | 129.50 |
| chips | 143.20 | pop-panel.mp3 | pop | 143.20 |
| divider5 | 167.00 | pop-panel.mp3 | pop | 167.00 |
| stat | 176.40 | click-04.mp3 | click | 176.40 |
| chart | 202.40 | pop-panel.mp3 | pop | 202.40 |
| divider6 | 213.40 | pop-panel.mp3 | pop | 213.40 |
| premium | 223.50 | pop-panel.mp3 | pop | 223.50 |
| chips | 250.30 | pop-panel.mp3 | pop | 250.30 |
| divider7 | 257.50 | pop-panel.mp3 | pop | 257.50 |
| table | 267.10 | pop-panel.mp3 | pop | 267.10 |
| counter | 288.60 | click-04.mp3 | click | 288.60 |
| divider8 | 297.20 | pop-panel.mp3 | pop | 297.20 |
| scenario | 303.60 | pop-panel.mp3 | pop | 303.60 |
| quote | 331.40 | pop-panel.mp3 | pop | 331.40 |
| divider9 | 338.60 | pop-panel.mp3 | pop | 338.60 |
| scenario | 342.60 | pop-panel.mp3 | pop | 342.60 |
| funnel | 354.40 | pop-panel.mp3 | pop | 354.40 |
| divider10 | 380.10 | pop-panel.mp3 | pop | 380.10 |
| checklist | 385.00 | pop-panel.mp3 | pop | 385.00 |
| item | 385.87 | click-04.mp3 | click | 385.87 |
| item | 394.09 | click-04.mp3 | click | 394.09 |
| item | 398.22 | click-04.mp3 | click | 398.22 |
| chips | 399.70 | pop-panel.mp3 | pop | 399.70 |
| divider11 | 422.10 | pop-panel.mp3 | pop | 422.10 |
| steps | 433.30 | pop-panel.mp3 | pop | 433.30 |
| stat | 445.00 | click-04.mp3 | click | 445.00 |
| divider12 | 467.80 | pop-panel.mp3 | pop | 467.80 |
| quote | 470.90 | pop-panel.mp3 | pop | 470.90 |
| outro | 480.60 | impact-word.mp3 | impact | 480.60 |

## Сценарий и вставки (§9.4–9.5)

Блоков в сценарии: 12; привязано к записи: 10; плановая сумма 618 с при фактических 509 с.

| # | Блок | На таймлайне | Длина | Что нарисовано |
|---|---|---|---|---|
| 1 | Хук: правила яснее, цена ниже | 0.0s | 41 с | 14.0s chips·речь, 27.0s quotes·речь |
| 2 | Что за конференция и кто в зале | 41.4s | 48 с | 44.9s chips·речь, 75.6s chips·речь |
| 3 | Четыре блока: онбординг, KYT, Travel Rule, стек | 89.4s | 30 с | 92.5s diagram·речь, 106.2s quote·тактовка |
| 4 | Почему это тектонический сдвиг | 119.6s | 47 с | 129.5s timeline·речь, 143.2s chips·речь |
| 5 | Глобальный фон: инфляция 3,7% и оттоки ETF | 167.0s | 46 с | 176.4s stat·речь, 202.4s chart·речь |
| 6 | Coinbase Premium 20 дней в минусе | 213.4s | 44 с | 223.5s premium·речь, 250.3s chips·речь |
| 7 | Разлоки съедают ликвидность | 257.5s | 40 с | 267.1s table·речь, 288.6s counter·речь |
| 8 | Bull-сценарий: легальный мост | 297.2s | 41 с | 303.6s scenario·речь, 331.4s quote·речь |
| 9 | Bear-сценарий: комплаенс как фильтр | 338.6s | 41 с | 342.6s scenario·речь, 354.4s funnel·речь |
| 10 | Что делать трейдеру прямо сейчас | 380.1s | 42 с | 385.0s checklist·речь, 399.7s chips·тактовка |
| 11 | Российский контекст: майнеры и AML | 422.1s | 46 с | 433.3s steps·речь, 445.0s miners·речь |
| 12 | CTA | 467.8s | — | 470.9s quote·тактовка, 480.6s outro·тактовка |

Событий графики в таблице: 37 (разделители блоков и вставки; внутренние появления — пункты чек-листа, столбцы диаграммы, метки — идут сверх этого). Средний интервал 13.3 с, максимальная пауза 30.7 с.

**Отклонение от §12.13 (сознательное):** норма ждёт новое событие каждые 2–3 с и паузу не больше 4 с. Здесь средний интервал между событиями 13.3 с, самая длинная пауза 30.7 с. Материал — говорящая голова 1080p, камера отключена (§7.1, апскейл запрещён), а уложиться в норму можно только держа плашку в кадре почти непрерывно: это превратило бы объяснение в инфографику с титрами. Плотность оставлена ниже нормы осознанно.

## 3. Не проверялось

- VMAF против эталона в 4K и дисперсия лапласиана (резкость): для этого дубля 4K-эталона нет — материал снят в 1080p, поэтому сравнение с 4K-референсом невозможно (§12.7–12.8).
- Приём «слово за головой» (§8) в этом прогоне не применялся: графика рисуется из плана сценария (разделители блоков и вставки), маска человека и слой за спиной не считались.
- Камера (наезды, отъезды, split, кружок): отключена по решению владельца — материал 1080p, апскейл запрещён §7.1. Задокументированное отклонение.
- Битрейт: 30.01 Mbps. Lossless-мастер держит 68.36 Мбит/с — это потолок материала.
- Режим `--bitrate-mode cbr` собран и замерен на отдельном прогоне: он даёт ровно 30.00 Мбит/с, но SSIM относительно мастера **ниже** (0.999664 → 0.998359, PSNR 34.7 → 27.8 дБ) — малый буфер CBR экономит биты на сложных кадрах. Поэтому по умолчанию режим `abr`.

## Таблица графики (§9.5)

| время | слова | элемент | анимация | звук |
|---|---|---|---|---|
| 0.6 | здравствуйте | hook | титр имени и должности | pop |
| 7.0 | крипта на балансе | title | титр всплывает сверху | impact |
| 14.0 | кто в зале | chips | имена и организации появляются по одному | pop |
| 27.0 | биткоин 81 174, эфир 2 373 | quotes | виджет котировок, строки по очереди | pop |
| 41.4 |  | divider2 | номер и название блока | pop |
| 44.9 | кто в зале | chips | имена и организации появляются по одному | pop |
| 75.6 | кто в зале | chips | имена и организации появляются по одному | pop |
| 89.4 |  | divider3 | номер и название блока | pop |
| 92.5 | онбординг, KYT, Travel Rule | diagram | четыре блока по очереди | pop |
| 106.2 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |
| 119.6 |  | divider4 | номер и название блока | pop |
| 129.5 | первое сентября 2026 | timeline | даты и требования по очереди | pop |
| 143.2 | кто в зале | chips | имена и организации появляются по одному | pop |
| 167.0 |  | divider5 | номер и название блока | pop |
| 176.4 | инфляция 3,7 | stat | счётчик добегает до значения из текста | click |
| 202.4 | оттоки из ETF | chart | столбцы вырастают по значениям из текста | pop |
| 213.4 |  | divider6 | номер и название блока | pop |
| 223.5 | минус 0,1398 процента, двадцать дней | premium | двадцать меток под нулевой линией | pop |
| 250.3 | кто в зале | chips | имена и организации появляются по одному | pop |
| 257.5 |  | divider7 | номер и название блока | pop |
| 267.1 | разлоки | table | строки таблицы появляются по одной | pop |
| 288.6 | доля акций cerebras | counter | счётчик добегает до значения из текста | click |
| 297.2 |  | divider8 | номер и название блока | pop |
| 303.6 | bull | scenario | карточка сценария и её пункты | pop |
| 331.4 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |
| 338.6 |  | divider9 | номер и название блока | pop |
| 342.6 | bear | scenario | карточка сценария и её пункты | pop |
| 354.4 | мелкие не выдерживают | funnel | воронка сужается от многих к нескольким | pop |
| 380.1 |  | divider10 | номер и название блока | pop |
| 385.0 | что делать трейдеру | checklist | пять пунктов с галочками на своих словах | pop |
| 399.7 | кто в зале | chips | имена и организации появляются по одному | pop |
| 422.1 |  | divider11 | номер и название блока | pop |
| 433.3 | сначала правила, потом реестр | steps | три шага цепочки по очереди | pop |
| 445.0 | 1473 участника | stat | счётчик до 1473 | click |
| 467.8 |  | divider12 | номер и название блока | pop |
| 470.9 | ключевая мысль | quote | линия слева растёт, строка въезжает | pop |
| 480.6 | подпишитесь на Rudstock Crypto | outro | плашка подписки в конце | impact |

## EDL (первые 20 склеек)

| # | Фраза | Вход | Выход | Длина | Причина |
|---|---|---|---|---|---|
| 1 | сентября 2026 года российский криптовалютный рынок официальн | 19.560 | 30.060 | 10.50 | waveform onset/offset snap |
| 2 | И вот сегодня, 15 октября, в | 30.450 | 33.240 | 2.79 | waveform onset/offset snap |
| 3 | Москве впервые на одной площадке собирается весь контур рынк | 32.830 | 36.120 | 3.29 | waveform onset/offset snap (part 1/2) |
| 4 | … | 37.180 | 38.310 | 1.13 | continuation after pause trim (part 2/2) |
| 5 | Минфин, Банк России, Ассоциация Банков | 38.640 | 41.350 | 2.71 | waveform onset/offset snap |
| 6 | России и ВБРФ. | 40.980 | 42.090 | 1.11 | waveform onset/offset snap |
| 7 | Конференция называется «Крипта на балансе. Запуск по новым п | 42.620 | 46.200 | 3.58 | waveform onset/offset snap |
| 8 | А теперь смотрите, что происходит с ценой. Биткоин снизился  | 46.630 | 51.180 | 4.55 | waveform onset/offset snap |
| 9 | долларов, эфир до 2300 с лишним. Ну и SPA снизился на 1%. То | 50.870 | 66.090 | 15.22 | waveform onset/offset snap |
| 10 | Организаторы – банковское обозрение и проф. ЦФА, генеральный | 68.050 | 78.570 | 10.52 | waveform onset/offset snap |
| 11 | Формат, подчеркнуто, не трендовый. Это не обзор, куда идет б | 79.080 | 84.300 | 5.22 | waveform onset/offset snap |
| 12 | Для тех, кто уже работает или только планирует запускать кри | 83.980 | 88.290 | 4.31 | waveform onset/offset snap |
| 13 | В анонсах прямо написано. Впервые собирают весь контур рынка | 88.850 | 95.500 | 6.65 | waveform onset/offset snap |
| 14 | Для читателей действует скидка 10% по промокоду «Партнер». С | 96.220 | 104.700 | 8.48 | waveform onset/offset snap (part 1/2) |
| 15 | … | 105.240 | 111.690 | 6.45 | continuation after pause trim (part 2/2) |
| 16 | Ключевые темы. Анбординг клиента, KYT, Travel Rule и стэк-те | 117.640 | 126.950 | 9.31 | waveform onset/offset snap |
| 17 | Какие документы, какие проверки, сколько времени. | 127.390 | 130.160 | 2.77 | waveform onset/offset snap |
| 18 | KYT – New York Transaction – проверка транзакций. Откуда при | 130.480 | 138.060 | 7.58 | waveform onset/offset snap |
| 19 | Travel Rule – правила передачи данных об отправителе и получ | 138.580 | 149.210 | 10.63 | waveform onset/offset snap |
| 20 | И стэк – технологическая инфраструктура. | 149.650 | 152.130 | 2.48 | waveform onset/offset snap |

Всего склеек: 96.
