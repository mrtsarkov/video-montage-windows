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


def build_html(blocks: list[dict], title: str, speed: int, size: int, mirror: bool) -> str:
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
  #top {{ position:fixed; top:0; left:0; right:0; z-index:5; display:flex; align-items:center; gap:14px;
    padding:14px 28px; background:var(--red); color:#fff; font-weight:800; font-size:24px; }}
  #top .meta {{ margin-left:auto; font-weight:500; font-size:20px; opacity:.9; }}
  .say {{ font-size:{size}px; line-height:1.5; font-weight:800; margin:0; }}
  .note {{ margin-top:1.6vh; color:#9a9a9a; font-size:calc({size}px * .42); line-height:1.35; }}
  #cue {{ position:fixed; top:0; left:0; right:0; height:5px; background:var(--red); width:0%; }}
  #hint {{ position:fixed; right:24px; bottom:16px; color:#c9c9c9; font-size:16px; }}
  body.mirror #wrap {{ transform: scaleX(-1); }}
</style></head>
<body{' class="mirror"' if mirror else ''}>
<div id="cue"></div>
<div id="top"><span>● REC</span><span>{html.escape(title)}</span>
  <span class="meta">пробел — пауза · ↑ ↓ — скорость</span></div>
<div id="wrap"><div id="roll">{''.join(parts)}</div></div>
<script>
  const roll = document.getElementById('roll'), cue = document.getElementById('cue');
  const total = roll.scrollHeight + innerHeight;
  let y = innerHeight * 0.80, speed = {speed}, paused = false, last = performance.now(), wait = 1.2;
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
    out.write_text(build_html(blocks, title, args.speed, args.size, args.mirror), encoding="utf-8")
    planned = sum(b["planned_s"] for b in blocks)
    words = sum(len(" ".join(b["text"]).split()) for b in blocks)
    print(f"Teleprompter: {out}")
    print(f"  блоков {len(blocks)} | плановая длительность {planned} с "
          f"({planned // 60}:{planned % 60:02d}) | слов {words} "
          f"| темп {words / max(1, planned) * 60:.0f} слов/мин")
    print(f"  скорость {args.speed} px/s, кегль {args.size}px"
          + (", зеркало" if args.mirror else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
