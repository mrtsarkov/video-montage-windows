# Setup video stack (agent prompt)

Промпт для автоматической установки окружения HyperFrames на **любой ОС**.  
На Windows предпочтительнее: `.\setup-windows.ps1`

<details>
<summary>Исходный текст промпта (macOS / Linux / Windows)</summary>

См. также upstream: HyperFrames docs — `npx hyperframes docs`

### Windows (кратко)

1. `winget install OpenJS.NodeJS.LTS Gyan.FFmpeg Python.Python.3.12`
2. `npm install -g hyperframes`
3. whisper-cli — из `tools/whisper-cpp/Release/` (в репо) или `setup-windows.ps1`
4. `npx hyperframes skills` + `npx hyperframes doctor`
5. `.\tools\download-whisper-model.ps1`
6. Smoke: `.\tools\probe-trial.ps1 -RunLabel cursor`

</details>

Полный оригинальный промпт установки хранится в репозитории Rudstock: `MD projects/setup-video-stack-prompt.md`
