#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "MONTAGE-PROMPT-v4.md"
OUT = ROOT / "MONTAGE-PROMPT-v4-no-subs.md"

SECTION_5 = """## 5. Субтитры — отключены

**Не делай.** В `edit/data.json` стоит `"subtitles": false`.

- Не создавай `subtitles.json`, не рендерь субтитры в HyperFrames, не добавляй блоки `.sub` / caption в композицию.
- **Расшифровка Whisper всё равно нужна** (раздел 3.3–3.4, 4) — для выбора дублей, EDL, таймингов графики и финальной проверки речи (§12.11). Таймкоды слов — только внутри пайплайна, не на экране.

"""


def patch(c: str) -> str:
    c = c.replace(
        "инфографика, субтитры, саунд-дизайн.",
        "инфографика, саунд-дизайн. **Субтитры на экране не делаем.**",
    )
    c = c.replace("**текстовый** (субтитры, подписи", "**текстовый** (подписи")
    c = c.replace(
        "- **Опережение субтитра:** 0,1 с.\n",
        '- **Субтитры:** `false` в `edit/data.json` — **не генерировать, не рендерить, не класть в композицию**.\n',
    )
    c = re.sub(
        r"## 5\. Субтитры\n\n.*?(?=\n---\n\n## 6\. Звук)",
        SECTION_5,
        c,
        flags=re.S,
    )
    c = c.replace("split, кружок. Субтитры событиями не считаются.", "split, кружок.")
    c = c.replace("Классы текста — пять, и только пять:", "Классы текста — четыре, и только четыре:")
    c = c.replace("- **Субтитр** — раздел 5.\n", "")
    c = c.replace(
        "Появляется на атаке своего слова с опережением из паспорта.",
        "Появляется на атаке своего слова в речи.",
    )
    c = c.replace("- Субтитры, EDL, план графики", "- EDL, план графики")
    c = c.replace(
        "5. **Тайминги.** Каждый субтитр, метка, пункт",
        "5. **Тайминги.** Каждая метка, пункт",
    )
    c = c.replace(
        "`edl.json`, `graphics_plan.md`, субтитры, `sfx_catalog.json`",
        "`edl.json`, `graphics_plan.md`, `sfx_catalog.json`",
    )
    return c


if __name__ == "__main__":
    text = patch(SRC.read_text(encoding="utf-8"))
    OUT.write_text(text, encoding="utf-8")
    SRC.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} and {SRC}")
