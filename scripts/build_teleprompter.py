#!/usr/bin/env python3
"""Generate a standalone teleprompter page for an OBS Browser Source.

OBS has no built-in teleprompter, and the community plugin does not load on OBS 32
(verified: the module never appears in the OBS log). A Browser Source needs no plugin
at all, so this builds a self-contained page with the script text embedded — no file
access, no CORS, works on any OBS version.

Usage:
  build_teleprompter.py <script.md|.txt|.docx> <out.html>
                        [--speed 42] [--size 66] [--mirror] [--title "..."]

In OBS: Источники → + → Браузер → Local file → выбрать out.html,
размер 1920x1080. Управление в самом окне источника: пробел — пауза, ↑/↓ — скорость.
"""
from __future__ import annotations

import argparse
import html
import re
import zipfile
from pathlib import Path


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


def build_html(blocks: list[dict], title: str, speed: int, size: int, mirror: bool,
               lens_pct: float | None = None, lens_x_pct: float = 50.0,
               column_vw: float = 46.0) -> str:
    """`lens_pct` switches on eyeline mode.

    Eyeline mode is the answer to "how do we keep the eyes on the camera": the line
    being read is parked at the height of the lens (a webcam sits at the top of the
    screen, so ~8-10 % down) and the column is narrow, instead of the text starting
    at 80 % of the screen height, which made the reader look down and off-axis.
    A ring marks the lens and everything below the reading line is dimmed.
    """
    planned = sum(b["planned_s"] for b in blocks)
    parts = []
    for b in blocks:
        note = "".join(f'<div class="note">{html.escape(n)}</div>' for n in b["broll"])
        body = " ".join(html.escape(t) for t in b["text"])
        parts.append(
            f'<section><div class="head"><span class="num">{b["n"]:02d}</span>'
            f'<span class="ttl">{html.escape(b["title"])}</span>'
            f'<span class="dur">~{b["planned_s"]} сек</span></div>'
            f'<p class="say">{body}</p>{note}</section>'
        )
    eyeline = lens_pct is not None
    lens = float(lens_pct if eyeline else 80.0)
    guides = ""
    extra_css = ""
    if eyeline:
        guides = (
            f'<div id="dim"></div><div id="guide"></div>'
            f'<div id="lens" style="left:{lens_x_pct:.1f}%">'
            f'<span class="ring"></span><span class="lbl">объектив · читать здесь</span></div>'
        )
        extra_css = f"""
  /* eyeline mode: the line being read sits on the camera's optical axis */
  #wrap {{ padding:0 {max(8.0, (100 - column_vw) / 2):.1f}vw; }}
  #dim {{ position:fixed; left:0; right:0; top:{lens:.2f}%; bottom:0; z-index:3;
    pointer-events:none; background:linear-gradient(rgba(255,255,255,0), rgba(255,255,255,.55) 30%,
    rgba(255,255,255,.82)); }}
  #guide {{ position:fixed; left:0; right:0; top:{lens:.2f}%; height:0; z-index:4;
    border-top:2px dashed rgba(239,49,36,.55); }}
  #lens {{ position:fixed; top:{lens:.2f}%; transform:translate(-50%,-50%); z-index:6;
    display:flex; align-items:center; gap:10px; }}
  #lens .ring {{ width:34px; height:34px; border-radius:50%; border:3px solid var(--red);
    box-shadow:0 0 0 6px rgba(239,49,36,.12); }}
  #lens .lbl {{ color:var(--red); font-weight:800; font-size:18px; white-space:nowrap; }}
"""
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
  @font-face {{ font-family:'Inter'; src:url('fonts/Inter-800.ttf'); font-weight:800; }}
  :root {{ --red:#EF3124; --ink:#1A1C1C; --muted:#666; }}
  html,body {{ margin:0; height:100%; background:#FFFFFF; color:var(--ink); overflow:hidden;
    font-family:'Inter',Arial,sans-serif; }}
  #wrap {{ position:absolute; inset:0; padding:0 8vw; overflow:hidden; }}
  #roll {{ transform: translateY(100vh); will-change: transform; }}
  section {{ padding:5vh 0 4vh; border-top:4px solid #F3F3F3; }}
  .head {{ display:flex; align-items:baseline; gap:18px; margin-bottom:2vh; }}
  .num {{ color:var(--red); font-weight:800; font-size:calc({size}px * .62); }}
  .ttl {{ font-weight:800; font-size:calc({size}px * .58); letter-spacing:-.02em; }}
  .dur {{ margin-left:auto; color:var(--muted); font-weight:800; font-size:calc({size}px * .42); }}
  #top {{ position:fixed; top:0; left:0; right:0; z-index:8; display:flex; align-items:center; gap:14px;
    padding:14px 28px; background:var(--red); color:#fff; font-weight:800; font-size:24px; }}
  #top .meta {{ margin-left:auto; font-weight:500; font-size:20px; opacity:.9; }}
  .say {{ font-size:{size}px; line-height:1.5; font-weight:800; margin:0; }}
  .note {{ margin-top:1.6vh; color:#9a9a9a; font-size:calc({size}px * .42); line-height:1.35; }}
  #cue {{ position:fixed; top:0; left:0; right:0; height:5px; background:var(--red); width:0%; z-index:9; }}
  #hint {{ position:fixed; right:24px; bottom:16px; color:#c9c9c9; font-size:16px; z-index:9; }}
  body.mirror #wrap {{ transform: scaleX(-1); }}
{extra_css}</style></head>
<body{' class="mirror"' if mirror else ''}>
<div id="cue"></div>
<div id="top"><span>● REC</span><span>{html.escape(title)}</span>
  <span class="meta">пробел — пауза · ↑ ↓ — скорость</span></div>
{guides}
<div id="wrap"><div id="roll">{''.join(parts)}</div></div>
<script>
  const roll = document.getElementById('roll'), cue = document.getElementById('cue');
  const total = roll.scrollHeight + innerHeight;
  const LENS = innerHeight * {lens:.2f} / 100;
  let y = LENS, speed = {speed}, paused = false, last = performance.now(), wait = 1.2;
  roll.style.transform = `translateY(${{y}}px)`;
  document.addEventListener('keydown', e => {{
    if (e.code === 'Space') {{ paused = !paused; e.preventDefault(); }}
    if (e.code === 'ArrowUp')   speed = Math.min(300, speed + 4);
    if (e.code === 'ArrowDown') speed = Math.max(6, speed - 4);
  }});
  function tick(now) {{
    const dt = (now - last) / 1000; last = now;
    if (wait > 0) {{ wait -= dt; }}
    else if (!paused) {{ y -= speed * dt; roll.style.transform = `translateY(${{y}}px)`;
      cue.style.width = Math.min(100, Math.max(0, (1 - y / total) * 100)) + '%'; }}
    requestAnimationFrame(tick);
  }}
  requestAnimationFrame(tick);
</script>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--speed", type=int, default=42, help="пикселей в секунду")
    ap.add_argument("--size", type=int, default=66, help="кегль текста для чтения")
    ap.add_argument("--mirror", action="store_true", help="для суфлёрского стекла")
    ap.add_argument("--title", default=None)
    ap.add_argument("--eyeline", action="store_true",
                    help="режим «взгляд в объектив»: строка чтения стоит на высоте камеры")
    ap.add_argument("--lens-percent", type=float, default=9.0,
                    help="высота объектива в кадре, %% от высоты экрана (вебка сверху ≈ 8-11)")
    ap.add_argument("--lens-x-percent", type=float, default=50.0,
                    help="горизонталь объектива, %% от ширины экрана")
    ap.add_argument("--column-vw", type=float, default=46.0,
                    help="ширина колонки текста, vw (узкая колонка = короче строки = меньше беготни глаз)")
    args = ap.parse_args()

    src = Path(args.script)
    if not src.is_file():
        raise SystemExit(f"нет файла: {src}")
    blocks = split_blocks(read_any(src))
    if not blocks:
        raise SystemExit("не нашёл ни одного блока вида '#NЗаголовок~50 сек'")
    title = args.title or src.stem
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(blocks, title, args.speed, args.size, args.mirror,
                              args.lens_percent if args.eyeline else None,
                              args.lens_x_percent, args.column_vw), encoding="utf-8")
    planned = sum(b["planned_s"] for b in blocks)
    words = sum(len(" ".join(b["text"]).split()) for b in blocks)
    print(f"Teleprompter: {out}")
    print(f"  блоков {len(blocks)} | плановая длительность {planned} с "
          f"({planned // 60}:{planned % 60:02d}) | слов {words} "
          f"| темп {words / max(1, planned) * 60:.0f} слов/мин")
    print(f"  скорость {args.speed} px/s, кегль {args.size}px"
          + (", зеркало" if args.mirror else ""))
    if args.eyeline:
        print(f"  режим «взгляд в объектив»: линия чтения на {args.lens_percent:.1f} % высоты "
              f"(высота объектива), колонка {args.column_vw:.0f} vw, "
              f"метка объектива по центру {args.lens_x_percent:.0f} %")
        print("  правило: объектив должен стоять на этой линии, иначе глаза уходят вниз")
    else:
        print("  обычный режим (текст идёт от 80 % высоты). Для съёмки лица "
              "используйте --eyeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
