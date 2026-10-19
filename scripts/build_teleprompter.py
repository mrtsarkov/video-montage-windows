#!/usr/bin/env python3
"""Generate a standalone teleprompter page for an OBS Browser Source / second monitor.

OBS has no built-in teleprompter, and the community plugin does not load on OBS 32
(verified: the module never appears in the OBS log). A Browser Source needs no plugin
at all, so this builds a self-contained page with the script text embedded — no file
access, no CORS, works on any OBS version and on any machine (the brand font is embedded
into the page as base64).

Usage:
  build_teleprompter.py <script.md|.txt|.docx> <out.html>
                        [--speed 1.0] [--size 66] [--size-min 36] [--size-max 120]
                        [--eyeline] [--lens-percent 9] [--column-vw 46]
                        [--mirror] [--font path.ttf] [--title "..."]

Reading-page keys:
  пробел            пауза / продолжить
  ↑ / ↓             темп медленнее / быстрее (шаг 6 %, множитель к плановой длительности)
  + / −             кегль крупнее / мельче (шаг 4 px, 36..120)
  PageUp / PageDown предыдущий / следующий блок
  R или Home        вернуться в начало и встать на паузу
  M                 зеркало (для суфлёрского стекла)
  G                 спрятать/показать линию объектива и затемнение
  F                 полный экран
Кегль выбирается ещё и мышью: A− / ползунок / A+ в верхней панели; выбранный
размер запоминается в браузере и переживает перезагрузку страницы.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TEMPLATE = HERE / "teleprompter-template.html"

# приоритет: шрифт из брендбука (полная кириллица), затем рабочие копии
FONT_CANDIDATES = (
    REPO / "refs" / "brandbook" / "fonts" / "inter-v20-cyrillic_latin_latin-ext-800.ttf",
    REPO / "script" / "fonts" / "Inter-800.ttf",
    REPO / "fonts" / "Inter-800.ttf",
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def read_docx(path: Path) -> str:
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "replace")
    out = []
    for block in re.split(r"</w:p>", xml):
        txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", block, re.S))
        txt = html.unescape(re.sub(r"<[^>]+>", "", txt)).strip()
        if txt:
            out.append(txt)
    return "\n".join(out)


def read_any(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return read_docx(path)
    return path.read_text(encoding="utf-8-sig")


def split_blocks(text: str) -> list[dict]:
    """#NЗаголовок~50 сек + текст + строка 🎞 B-roll."""
    blocks, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = re.match(r"^#(\d+)\s*(.*?)\s*~\s*(\d+)\s*сек", line)
        if head:
            cur = {"n": int(head.group(1)), "title": head.group(2).strip(),
                   "planned_s": int(head.group(3)), "text": [], "broll": []}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("🎞") or re.match(r"^\W*B-roll", line, re.I):
            cur["broll"].append(re.sub(r"^🎞\s*", "", line).strip())
        else:
            cur["text"].append(line)
    return blocks


def sentences(text: str) -> list[str]:
    """One sentence per line: the eye returns to the start of a line, not to the
    middle of a wall of text — this is what makes a teleprompter readable."""
    return [s for s in SENTENCE_SPLIT.split(" ".join(text.split())) if s.strip()]


def font_src(explicit: str | None) -> tuple[str, str]:
    path = Path(explicit) if explicit else None
    if path is None:
        for cand in FONT_CANDIDATES:
            if cand.is_file():
                path = cand
                break
    if path is not None and path.is_file():
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"url(data:font/ttf;base64,{data}) format('truetype')", f"{path.name} (вшит, {path.stat().st_size // 1024} КБ)"
    return "url('fonts/Inter-800.ttf')", "не найден — запасной шрифт системы"


def build_html(blocks: list[dict], title: str, size: int, mirror: bool,
               lens_pct: float | None = None, column_vw: float = 46.0,
               speed: float = 1.0, size_min: int = 36, size_max: int = 120,
               font_path: str | None = None) -> str:
    """`lens_pct` switches on eyeline mode.

    Eyeline mode is the answer to "how do we keep the eyes on the camera": the line
    being read is parked at the height of the lens (a webcam sits at the top of the
    screen, so ~8-10 % down) and the column is narrow, instead of the text starting
    at 80 % of the screen height, which made the reader look down and off-axis.
    A ring marks the lens and everything below the reading line is dimmed.
    """
    planned = sum(b["planned_s"] for b in blocks)
    words = sum(len(" ".join(b["text"]).split()) for b in blocks)
    parts = []
    for b in blocks:
        note = "".join(f'<div class="note">{html.escape(n)}</div>' for n in b["broll"])
        body = "\n".join(html.escape(s) for s in sentences(" ".join(b["text"])))
        parts.append(
            f'<section id="blk{b["n"]}" data-n="{b["n"]}"><div class="head">'
            f'<span class="num">{b["n"]:02d}</span>'
            f'<span class="ttl">{html.escape(b["title"])}</span>'
            f'<span class="dur">~{b["planned_s"]} сек</span></div>'
            f'<p class="say">{body}</p>{note}</section>'
        )

    eyeline = lens_pct is not None
    lens = float(lens_pct if eyeline else 9.0)
    # колонка меряется в vw при базовом кегле и тянется вместе с ним (--fscale):
    # при любом размере шрифта в строке остаётся одно и то же число знаков
    colw = (f"min(92vw, calc({column_vw:.1f}vw * var(--fscale)))"
            if eyeline else "84vw")
    guides = ""
    extra_css = ""
    if eyeline:
        guides = (
            '<div id="dim"></div><div id="guide"></div>'
            '<div id="lens"><span class="ring"></span>'
            '<span class="lbl">объектив · линия чтения</span></div>'
        )
        extra_css = f"""
  /* eyeline mode: the line being read sits on the camera's optical axis */
  #dim {{ position:fixed; left:0; right:0; top:{lens:.2f}%; bottom:0; z-index:3;
    pointer-events:none; background:linear-gradient(rgba(255,255,255,0), rgba(255,255,255,.46) 34%,
    rgba(255,255,255,.75)); }}
  #guide {{ position:fixed; left:0; right:0; top:{lens:.2f}%; height:0; z-index:4;
    border-top:2px dashed rgba(239,49,36,.55); }}
  #lens {{ position:fixed; left:16px; top:{lens:.2f}%; transform:translateY(-50%); z-index:6;
    display:flex; align-items:center; gap:12px; pointer-events:none; }}
  #lens .ring {{ width:26px; height:26px; border-radius:50%; border:3px solid var(--red);
    background:#fff; box-shadow:0 0 0 5px rgba(239,49,36,.10); flex:none; }}
  #lens .lbl {{ color:var(--red); font-weight:800; font-size:15px; white-space:nowrap;
    background:#fff; padding:2px 8px; border-radius:5px; }}
  body.narrowcol #lens .lbl {{ display:none; }}
"""

    fsrc, _ = font_src(font_path)
    cfg = {
        "size": int(size),
        "sizeMin": int(size_min),
        "sizeMax": int(size_max),
        "speedFactor": float(speed),
        "plannedS": planned,
        "words": words,
        "eyeline": bool(eyeline),
        "lensPct": float(lens if eyeline else 9.0),
        "mirror": bool(mirror),
    }
    replacements = {
        "__TITLE__": html.escape(title),
        "__FONT_SRC__": fsrc,
        "__SIZE__": str(int(size)),
        "__FS_MIN__": str(int(size_min)),
        "__FS_MAX__": str(int(size_max)),
        "__COLW__": colw,
        "__BODY_CLASS__": "mirror" if mirror else "",
        "__EYELINE_CSS__": extra_css,
        "__GUIDES__": guides,
        "__SECTIONS__": "".join(parts),
        "__CFG__": json.dumps(cfg, ensure_ascii=False),
    }
    doc = TEMPLATE.read_text(encoding="utf-8")
    for token, value in replacements.items():
        doc = doc.replace(token, value)
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="множитель темпа: 1.0 = ровно плановая длительность сценария; "
                         "значения > 5 считаются старым px/s и игнорируются")
    ap.add_argument("--size", type=int, default=66,
                    help="кегль текста по умолчанию (в странице его можно менять)")
    ap.add_argument("--size-min", type=int, default=36, help="нижняя граница кегля")
    ap.add_argument("--size-max", type=int, default=120, help="верхняя граница кегля")
    ap.add_argument("--mirror", action="store_true", help="для суфлёрского стекла")
    ap.add_argument("--title", default=None)
    ap.add_argument("--eyeline", action="store_true",
                    help="режим «взгляд в объектив»: строка чтения стоит на высоте камеры")
    ap.add_argument("--lens-percent", type=float, default=9.0,
                    help="высота объектива в кадре, %% от высоты экрана (вебка сверху ≈ 8-11)")
    ap.add_argument("--column-vw", type=float, default=46.0,
                    help="ширина колонки текста при базовом кегле, vw "
                         "(колонка тянется вместе с кеглем; узкая = короче строка)")
    ap.add_argument("--font", default=None,
                    help="путь к .ttf для вшивания в страницу (по умолчанию — Inter 800 из брендбука)")
    args = ap.parse_args()

    src = Path(args.script)
    if not src.is_file():
        raise SystemExit(f"нет файла: {src}")
    blocks = split_blocks(read_any(src))
    if not blocks:
        raise SystemExit("не нашёл ни одного блока вида '#NЗаголовок~50 сек'")
    if not 0.35 <= args.speed <= 3.0:
        print(f"  ! --speed {args.speed} вне диапазона 0.35..3.0 "
              f"(старое значение в px/s больше не используется) — беру 1.0")
        args.speed = 1.0
    if not 20 <= args.size_min < args.size_max <= 200:
        raise SystemExit("кегли заданы странно: нужно 20 <= --size-min < --size-max <= 200")

    title = args.title or src.stem
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(blocks, title, args.size, args.mirror,
                              args.lens_percent if args.eyeline else None,
                              args.column_vw, args.speed,
                              args.size_min, args.size_max, args.font),
                   encoding="utf-8")

    planned = sum(b["planned_s"] for b in blocks)
    words = sum(len(" ".join(b["text"]).split()) for b in blocks)
    _, font_note = font_src(args.font)
    print(f"Teleprompter: {out} ({out.stat().st_size // 1024} КБ)")
    print(f"  блоков {len(blocks)} | плановая длительность {planned} с "
          f"({planned // 60}:{planned % 60:02d}) | слов {words} "
          f"| темп плана {words / max(1, planned) * 60:.0f} слов/мин")
    print(f"  кегль {args.size} px по умолчанию, выбор {args.size_min}..{args.size_max} px "
          f"в окне (A− / ползунок / A+ / клавиши + −)")
    print(f"  темп ×{args.speed:.2f} от плана | шрифт: {font_note}")
    if args.eyeline:
        print(f"  режим «взгляд в объектив»: линия чтения на {args.lens_percent:.1f} % высоты "
              f"(высота объектива), колонка {args.column_vw:.0f} vw при базовом кегле "
              f"(тянется вместе с кеглем)")
        print("  метка объектива — в левом поле на линии чтения; при крупном кегле "
              "колонка расширяется и подпись исчезает")
        print("  правило: объектив должен стоять на этой линии, иначе глаза уходят вниз")
    else:
        print("  обычный режим (текст идёт от 80 % высоты). Для съёмки лица "
              "используйте --eyeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
