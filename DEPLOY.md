# Развёртывание на новом компьютере (Windows)

## 1. Клонировать репозиторий

```powershell
git clone https://github.com/mrtsarkov/video-montage-windows.git
cd video-montage-windows
```

## 2. Установить окружение (один раз)

```powershell
.\setup-windows.ps1
```

Скрипт ставит через winget: Node.js LTS, FFmpeg, Python 3.12; через npm: HyperFrames; скачивает whisper.cpp (если нет в `tools/whisper-cpp/`); добавляет `whisper-cli` в PATH пользователя; ставит Python-пакеты numpy/Pillow; запускает `npx hyperframes skills` и `npx hyperframes doctor`.

## 3. Скачать модель Whisper (~3 GB)

```powershell
.\tools\download-whisper-model.ps1
```

Путь: `%USERPROFILE%\.cache\whisper\ggml-large-v3.bin`

## 4. Проверка

```powershell
.\tools\check-env.ps1
.\tools\init-run.ps1 -Label cursor
.\tools\probe-trial.ps1 -RunLabel cursor
```

## 5. Монтаж ролика

1. Положите дубли в `takes/`
2. Откройте папку в Cursor
3. В Agent-чат вставьте **весь** `MONTAGE-PROMPT-v4.md`
4. Добавьте: «Метка прогона: cursor, итог runs/cursor/out/final.mp4»
5. Ответьте на вопросы агента → ждите `final.mp4`

## Что не в git

| Что | Как восстановить |
|-----|------------------|
| Сырые дубли `takes/*.mp4` | Скопировать вручную / свой бэкап |
| `runs/**/out/final.mp4` | Перерендерить |
| Whisper model 3 GB | `download-whisper-model.ps1` |
| HyperFrames Chrome | `npx hyperframes doctor` (авто) |

## macOS / Linux

Промпт монтажа (`MONTAGE-PROMPT-v4.md`) изначально под macOS. На Windows используйте `tools/*.ps1`. Для Mac см. `SETUP-VIDEO-STACK.md`.
