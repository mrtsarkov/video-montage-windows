Ты — инженер по настройке окружения. Задача: подготовить эту машину для создания видео  
из кода через HyperFrames. Работай сам, в терминале, до конца.

ПРАВИЛА  
1\. Сначала проверь, что уже установлено (версия/путь), и только потом ставь. Ничего не  
   переустанавливай и не обновляй сверх списка ниже.  
2\. Каждый шаг закрывай ФАКТОМ — выводом команды с версией. «Установка прошла успешно»  
   доказательством не считается.  
3\. Если шаг требует пароль (sudo) — остановись и попроси человека выполнить команду  
   самому, дай точную строку.  
4\. Если что-то не встало — не молчи и не выдумывай обход: запиши как «не установлено» с  
   причиной и иди дальше.  
5\. В конце — таблица: компонент | версия | путь | статус.

ШАГ 0\. Определи ОС и менеджер пакетов  
\- macOS → Homebrew (\`brew \-v\`; если нет:  
  /bin/bash \-c "\$(curl \-fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)")  
\- Windows → winget  
\- Linux → apt/dnf

ШАГ 1\. Node.js 22 или новее (обязательное требование HyperFrames)  
\- Проверка: node \-v  
\- macOS: brew install node · Windows: winget install OpenJS.NodeJS.LTS · Linux: через nvm  
\- Факт: node \-v (должно быть v22+), npm \-v

ШАГ 2\. FFmpeg (вместе с ffprobe)  
\- macOS: brew install ffmpeg · Windows: winget install Gyan.FFmpeg · Linux: sudo apt install ffmpeg  
\- Факт: ffmpeg \-version и ffprobe \-version

ШАГ 3\. Whisper — именно whisper.cpp  
HyperFrames для расшифровки и субтитров запускает бинарь whisper-cli из whisper.cpp.  
Пакет openai-whisper на питоне для этого НЕ подходит.  
\- macOS: brew install whisper-cpp  
\- Windows / Linux: поставь готовый билд или собери из исходников  
  github.com/ggml-org/whisper.cpp так, чтобы бинарь whisper-cli был в PATH  
\- Факт: whisper-cli \--help отрабатывает без ошибки  
\- Опционально, только Apple Silicon: uv pip install parakeet-mlx — точнее и быстрее  
  whisper, HyperFrames подхватывает сам

ШАГ 4\. HyperFrames  
\- npm install \-g hyperframes  
\- Факт: hyperframes \--version  
\- Поставь скиллы HyperFrames для ИИ-агентов (Claude Code, Cursor и т.д.): npx hyperframes skills  
\- ГЕЙТ: npx hyperframes doctor  
  Зелёными должны быть: Version, Node.js, FFmpeg, FFprobe, whisper-cpp, Chrome.  
  Строки Docker, TTS (Kokoro), BGM (MusicGen) — опциональные, красный статус там нормален,  
  ничего по ним не доставляй.  
  Первый запуск докачает headless Chrome — это ожидаемо, дай ему закончить.

ШАГ 5\. Проверка боем  
\- Создай тестовый проект: npx hyperframes init hf-demo  
  (в неинтерактивном режиме: npx hyperframes init hf-demo \--non-interactive \--example=\<имя  
  из списка, который покажет CLI\>)  
\- В папке проекта: npx hyperframes check, затем npx hyperframes render \--quality draft \--output out.mp4  
\- Факт: test \-s out.mp4 и ffprobe \-v error \-show\_format out.mp4 показывает ненулевую длительность  
\- Спроси человека, оставить папку hf-demo или удалить.

ШАГ 6\. Отчёт  
Выведи таблицу по всем компонентам: что стоит, версия, путь, статус. Отдельно перечисли,  
что НЕ встало и почему.

ШАГ 7\. И ТОЛЬКО ПОСЛЕ ОТЧЁТА — спроси про Remotion  
Задай вопрос дословно:  
«Поставить дополнительно Remotion? Это отдельный фреймворк для видео на React — для  
работы HyperFrames он не нужен, берут его только если хочешь собирать композиции на  
React. Лицензия: бесплатно для частных лиц и команд до 3 человек, дальше нужна платная  
Company License. Ставим? (да/нет)»  
Дождись явного «да». Без ответа — не ставь.  
Если да:  
\- npx create-video@latest — создаст проект и поставит зависимости локально  
\- Факт: в папке проекта npx remotion versions выводит версии, npm run dev поднимает Studio  
\- Верни человеку путь к проекту и адрес Studio.  
