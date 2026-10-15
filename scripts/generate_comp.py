#!/usr/bin/env python3
"""Generate HyperFrames composition from data.json + EDL (+ optional subtitles)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def edl_timeline(edl: list[dict]) -> tuple[float, list[dict]]:
    t = 0.0
    rows = []
    for c in edl:
        dur = c["out"] - c["in"]
        rows.append({**c, "t0": t, "t1": t + dur, "dur": dur})
        t += dur
    return t, rows


def main() -> int:
    back = "--back" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    label = args[0] if args else "cursor"
    root = Path(__file__).resolve().parents[1]
    edit = root / "runs" / label / "edit"
    if not (edit / "data.json").exists():
        print(f"No passport: {edit / 'data.json'}", file=sys.stderr)
        return 1
    data = json.loads((edit / "data.json").read_text(encoding="utf-8-sig"))
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8-sig"))
    dur, tl = edl_timeline(edl)
    subtitles_on = data.get("passport", {}).get("subtitles", False)
    subs_path = edit / "subtitles.json"
    subs = (
        json.loads(subs_path.read_text(encoding="utf-8-sig"))
        if subtitles_on and subs_path.exists()
        else []
    )

    c = data["passport"]["colors"]
    # brand tokens live in refs/brandbook/brand.json (brandbook «Architectural Monolith» v2.0)
    brand_path = root / "refs" / "brandbook" / "brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8-sig")) if brand_path.exists() else None
    if brand:
        bc = brand["colors"]
        c = {"white": bc["white"], "accent1": bc["accent"], "accent2": bc["accent_dark"],
             "dark_panel": bc["surface"], "surface": bc["surface"], "ink": bc["ink"],
             "muted": bc["muted"]}
    shadow = brand["shape"]["video_shadow"] if brand else "0 10px 22px rgba(0,0,0,.35)"
    author = data["passport"].get("author") or {"name": "Дмитрий Царьков",
                                                "role": "управляющий активами"}
    lt_in, lt_hold = 0.6, 6.0
    brand_fonts = brand["fonts"]["files"] if brand else {}
    comp_dir = edit / "comp"
    fonts_dir = comp_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    win = Path(r"C:\Windows\Fonts")
    font_src = root / "refs" / "brandbook" / "fonts"
    if brand_fonts:
        for weight, fname in brand_fonts.items():
            src = font_src / fname
            if src.exists():
                shutil.copy2(src, fonts_dir / f"Inter-{weight}.ttf")
    for name in ["segoeui.ttf", "segoeuib.ttf"]:
        if not brand_fonts and (win / name).exists():
            shutil.copy2(win / name, fonts_dir / name)

    # gsap must be local: the composition has to render with no internet (spec §1)
    gsap_src = root / "tools" / "vendor" / "gsap.min.js"
    if gsap_src.exists():
        (comp_dir / "vendor").mkdir(parents=True, exist_ok=True)
        shutil.copy2(gsap_src, comp_dir / "vendor" / "gsap.min.js")

    # Key times come from the transcript, but a take can be worded differently:
    # a missing trigger must not pile every element at t=0 (that fails
    # `hyperframes check` with content_overlap). Unmatched elements are packed into
    # free slots with a minimum gap, and every element's duration is clamped so it
    # cannot run past the end of a short composition.
    MIN_GAP = 1.6

    def find_t(substr: str):
        for row in tl:
            if substr.lower() in row["text"].lower():
                return row["t0"] + 0.4
        return None

    def free_slot(taken: list[float]) -> float | None:
        t = 0.8
        while t <= dur - 1.0:
            if all(abs(t - x) >= MIN_GAP for x in taken):
                return round(t, 3)
            t += 0.4
        return None

    taken: list[float] = [0.1]  # the hook always opens the piece
    resolved: dict[str, float] = {"hook": 0.1}
    triggers = [
        ("word", ["контент"]),
        ("calendar", ["календар"]),
        ("checklist", ["рыночные"]),
        ("chat", ["сгенерировать", "генер"]),
        ("counter", ["метрик"]),
        ("scale", ["искусственный интеллект"]),
        ("stepper", ["локальными моделями"]),
    ]
    unmatched: list[str] = []
    for name, needles in triggers:
        t = None
        for needle in needles:
            t = find_t(needle)
            if t is not None:
                break
        if t is None:
            unmatched.append(name)
            continue
        resolved[name] = round(t, 3)
        taken.append(round(t, 3))
    for name in unmatched:
        slot = free_slot(taken)
        if slot is None:
            continue
        resolved[name] = slot
        taken.append(slot)
    if unmatched:
        placed = [n for n in unmatched if n in resolved]
        print(f"WARNING: no trigger in the transcript for: {', '.join(unmatched)}"
              + (f"; placed at free slots: {', '.join(placed)}" if placed else "; dropped"))

    def T(name: str) -> float:
        """An element that found no slot is parked past the end so it never renders."""
        return resolved.get(name, round(dur + 60.0, 3))

    def edur(default: float, t: float) -> float:
        return round(max(0.6, min(default, dur - t - 0.4)), 3)

    t_hook = resolved["hook"]
    t_factory, t_cal, t_events = T("word"), T("calendar"), T("checklist")
    t_gen, t_metrics = T("chat"), T("counter")
    t_ai, t_local = T("scale"), T("stepper")
    o_hook, o_factory = t_hook + 2.5, t_factory + 3.0
    d_hook, d_factory = edur(3.2, t_hook), edur(3.5, t_factory)
    d_cal, o_cal = edur(8, t_cal), 0.0
    o_cal = t_cal + d_cal - 0.8
    d_chk, o_chk = edur(10, t_events), 0.0
    o_chk = t_events + d_chk - 1.0
    d_chat, o_chat = edur(9, t_gen), 0.0
    o_chat = t_gen + d_chat - 1.0
    d_met, o_met = edur(8, t_metrics), 0.0
    o_met = t_metrics + d_met - 0.8
    d_scl, o_scl = edur(9, t_ai), 0.0
    o_scl = t_ai + d_scl - 1.0
    d_stp, o_stp = edur(10, t_local), 0.0
    o_stp = t_local + d_stp - 1.0

    graphics = [
        {"t": t_hook, "el": "hook", "label": "Контент-завод для советника"},
        {"t": t_factory, "el": "word", "label": "КОНТЕНТ-ЗАВОД"},
        {"t": t_cal, "el": "calendar", "label": "Календарь событий"},
        {"t": t_events, "el": "checklist", "label": "Типы событий"},
        {"t": t_gen, "el": "chat", "label": "Генерация поста"},
        {"t": t_metrics, "el": "counter", "label": "Метрики дня"},
        {"t": t_ai, "el": "scale", "label": "AI-анализ продукта"},
        {"t": t_local, "el": "stepper", "label": "Локальные / внешние модели"},
    ]

    # §8: the big word goes BEHIND the speaker, so it renders as its own layer
    # together with a person matte; a second, short composition is written for it.
    if back:
        back_dir = edit / "comp-back"
        (back_dir / "fonts").mkdir(parents=True, exist_ok=True)
        for weight, fname in (brand_fonts or {"700": "segoeuib.ttf"}).items():
            src = (root / "refs" / "brandbook" / "fonts" / fname) if brand_fonts else (win / fname)
            if src.exists():
                shutil.copy2(src, back_dir / "fonts" / (f"Inter-{weight}.ttf" if brand_fonts else fname))
        (back_dir / "vendor").mkdir(parents=True, exist_ok=True)
        if gsap_src.exists():
            shutil.copy2(gsap_src, back_dir / "vendor" / "gsap.min.js")
        word_dur = max(0.8, d_factory)
        back_html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="UTF-8"/>
<script src="vendor/gsap.min.js"></script>
<style>
@font-face {{ font-family:'Inter'; src:url('fonts/Inter-900.ttf'); font-weight:900; }}
html,body {{ margin:0; width:1920px; height:1080px; overflow:hidden; background:transparent; }}
.word-behind {{
  position:absolute; left:50%; top:34%; transform:translate(-50%,-50%) scale(.84);
  font:900 118px/1 'Inter',sans-serif; color:{c['accent1']}; letter-spacing:-.04em; opacity:0; white-space:nowrap;
}}
</style>
</head>
<body>
<div id="root" class="clip" data-composition-id="main" data-start="0" data-duration="{word_dur:.3f}"
     data-width="1920" data-height="1080">
  <div id="word" class="word-behind clip" data-start="0" data-duration="{word_dur:.3f}"
       data-layout-allow-occlusion="true">КОНТЕНТ-ЗАВОД</div>
</div>
<script>
const expo = {{ out: p => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)), in: p => (p <= 0 ? 0 : Math.pow(2, 10 * (p - 1))) }};
const tl = gsap.timeline({{ paused: true }});
tl.fromTo('#word', {{ opacity:0, scale:0.84 }}, {{ opacity:1, scale:1.04, duration:1.925, ease:p=>expo.out(p) }}, 0);
tl.to('#word', {{ scale:1, duration:1.575, ease:p=>expo.out(p) }}, 1.925);
tl.to('#word', {{ opacity:0, scale:0.92, duration:0.3, ease:p=>expo.in(p) }}, Math.max(0, {word_dur:.3f} - 0.3));
window.__timelines = window.__timelines || {{}};
window.__timelines['main'] = tl;
tl.seek(0);
</script>
</body>
</html>
"""
        (back_dir / "index.html").write_text(back_html, encoding="utf-8")
        (edit / "back_layer.json").write_text(json.dumps({
            "layer": "layer-back.mov",
            "start_s": round(t_factory, 3),
            "duration_s": round(word_dur, 3),
            "element": "word",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Back layer composition: {back_dir / 'index.html'} "
              f"({word_dur:.2f}s at t={t_factory:.2f}s)")
        return 0

    def words_at(t: float) -> str:
        for row in tl:
            if row["t0"] <= t <= row["t1"]:
                return (row["text"][:52] or "—").replace("|", "/")
        return "—"

    (edit / "graphics_plan.md").write_text(
        "| время | слова | элемент | анимация | звук |\n|---|---|---|---|---|\n"
        + "\n".join(
            f"| {g['t']:.1f} | {words_at(g['t'])} | {g['el']} | {g['label']} | — |" for g in graphics
        ),
        encoding="utf-8",
    )

    sub_html = ""
    for s in subs:
        sub_html += f'<div class="sub clip" data-start="{s["start"]:.3f}" data-duration="{max(0.24, s["end"]-s["start"]):.3f}">{s["text"]}</div>\n'

    subs_css = (
        """
.subs { position:absolute; left:50%; bottom:7.5%; transform:translateX(-50%); width:88%; text-align:center; pointer-events:none; }
.sub { position:absolute; left:0; right:0; bottom:0; opacity:0; font:500 38px/1.25 'Segoe UI',sans-serif; color:"""
        + c["white"]
        + """; text-shadow:0 2px 12px rgba(0,0,0,.85); }
"""
        if subtitles_on
        else ""
    )
    subs_block = f'  <div class="subs">{sub_html}</div>\n' if subtitles_on else ""
    subs_js = (
        """
document.querySelectorAll('.sub').forEach(el=>{
  const s=parseFloat(el.dataset.start), d=parseFloat(el.dataset.duration);
  tl.fromTo(el, { opacity:0, y:6 }, { opacity:1, y:0, duration:0.12, ease:p=>expo.out(p) }, Math.max(0,s-0.1));
  tl.to(el, { opacity:0, duration:0.08, ease:p=>expo.in(p) }, s+d-0.08);
});
"""
        if subtitles_on
        else ""
    )

    js_chk = "\n".join(
        f"  tl.fromTo('{sel}', {{ opacity:0, y:8 }}, {{ opacity:1, y:0, duration:0.35, ease:p=>expo.out(p) }}, {t_events + 0.4 + i * 0.5:.3f});\n"
        f"  tl.call(()=>document.querySelector('{sel} .tick').classList.add('on'), null, {t_events + 0.7 + i * 0.5:.3f});"
        for i, sel in enumerate(["#i1", "#i2", "#i3"])
    )
    js_steps = "\n".join(
        f"  tl.call(()=>document.querySelector('{sel}').classList.add('on'), null, {t_local + 0.5 + i * 0.6:.3f});"
        for i, sel in enumerate(["#s1", "#s2", "#s3"])
    )

    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="UTF-8"/>
<script src="vendor/gsap.min.js"></script>
<style>
@font-face {{ font-family:'Inter'; src:url('fonts/Inter-500.ttf'); font-weight:500; }}
@font-face {{ font-family:'Inter'; src:url('fonts/Inter-800.ttf'); font-weight:800; }}
@font-face {{ font-family:'Inter'; src:url('fonts/Inter-900.ttf'); font-weight:900; }}
html,body {{ margin:0; width:1920px; height:1080px; overflow:hidden; background:transparent; }}
*{{
  box-sizing:border-box;
  -webkit-font-smoothing:antialiased;
}}
    .panel {{
    background:{c['white']}; border-radius:32px; box-shadow:{shadow};
    color:{c['ink']}; font-family:'Inter',sans-serif;
  }}
  .hook {{
    position:absolute; left:50%; top:8%; transform:translateX(-50%);
    font:900 92px/1 'Inter',sans-serif; color:{c['accent1']}; letter-spacing:-.03em;
    text-shadow:0 6px 24px rgba(0,0,0,.18); opacity:0;
  }}
  .lower-third {{
    position:absolute; left:5%; bottom:7.5%; padding:18px 26px 18px 22px; opacity:0;
    border-left:6px solid {c['accent1']};
  }}
  .lower-third .lt-name {{ font:800 40px/1.15 'Inter',sans-serif; color:{c['ink']}; letter-spacing:-.02em; }}
  .lower-third .lt-role {{ font:500 26px/1.3 'Inter',sans-serif; color:{c['muted']}; margin-top:4px; }}
  .word-behind {{
    position:absolute; left:50%; top:34%; transform:translate(-50%,-50%) scale(.84);
    font:900 118px/1 'Inter',sans-serif; color:{c['accent1']}; letter-spacing:-.04em;
    opacity:0; white-space:nowrap;
  }}
  .card-right {{
    position:absolute; right:5%; top:14%; width:26%; min-height:120px; padding:22px 24px; opacity:0;
  }}
  .card-left {{
    position:absolute; left:5%; top:18%; width:24%; padding:20px 22px; opacity:0;
  }}
  .title {{ font:800 34px/1.1 'Inter',sans-serif; margin:0 0 12px; color:{c['accent1']}; letter-spacing:-.02em; }}
  .body {{ font:500 26px/1.45 'Inter',sans-serif; color:{c['ink']}; }}
  .line {{ height:4px; background:{c['accent1']}; width:0; margin:8px 0 14px; border-radius:2px; }}
  .item {{ display:flex; gap:12px; align-items:flex-start; margin:10px 0; font:500 24px/1.35 'Inter',sans-serif; color:{c['ink']}; opacity:0; transform:translateY(8px); }}
  .tick {{ width:24px; height:24px; flex:0 0 24px; background:{c['surface']}; border-radius:8px; position:relative; }}
  .tick.on::after {{ content:''; position:absolute; left:5px; top:1px; width:8px; height:14px; border-right:3px solid {c['accent1']}; border-bottom:3px solid {c['accent1']}; transform:rotate(45deg); }}
  .chat-win {{ position:absolute; right:5%; top:16%; width:27%; padding:0; overflow:hidden; opacity:0; }}
  .chat-head {{ background:{c['surface']}; padding:14px 16px; font:800 22px/1 'Inter',sans-serif; color:{c['ink']}; letter-spacing:-.01em; }}
  .chat-body {{ padding:16px; font:500 24px/1.45 'Inter',sans-serif; color:{c['ink']}; min-height:140px; }}
  .cursor {{ display:inline-block; width:2px; height:1em; background:{c['accent1']}; vertical-align:text-bottom; }}
  .counter {{ font:900 72px/1 'Inter',sans-serif; color:{c['accent1']}; letter-spacing:-.03em; }}
  .bar-wrap {{ height:14px; background:{c['surface']}; border-radius:999px; overflow:hidden; margin-top:14px; }}
  .bar {{ height:100%; width:0; background:{c['accent1']}; }}
  .stepper {{ display:flex; gap:12px; align-items:center; margin-top:12px; }}
  .step {{ width:38px; height:38px; border-radius:999px; background:{c['surface']}; color:{c['ink']}; display:flex; align-items:center; justify-content:center; font:800 18px/1 'Inter',sans-serif; }}
  .step.on {{ background:{c['accent1']}; color:{c['white']}; }}
{subs_css}</style>
</head>
<body>
<div id="root" class="clip" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="1920" data-height="1080">

  <h1 id="hook" class="hook clip" data-start="{t_hook:.3f}" data-duration="{d_hook:.3f}">Контент-завод</h1>

  <div id="lt" class="panel lower-third clip" data-start="{lt_in:.3f}" data-duration="{min(lt_hold, max(1.0, dur - lt_in - 0.5)):.3f}">
    <div class="lt-name">{author["name"]}</div>
    <div class="lt-role">{author["role"]}</div>
  </div>

  <div id="cal" class="panel card-right clip" data-start="{t_cal:.3f}" data-duration="{d_cal:.3f}">
    <div class="title">Календарь</div><div class="line" id="cal-line"></div>
    <div class="body" id="cal-text"></div>
  </div>

  <div id="chk" class="panel card-left clip" data-start="{t_events:.3f}" data-duration="{d_chk:.3f}">
    <div class="title">События</div>
    <div class="item" id="i1"><span class="tick"></span><span>Рыночные</span></div>
    <div class="item" id="i2"><span class="tick"></span><span>Корпоративные</span></div>
    <div class="item" id="i3"><span class="tick"></span><span>Форумы</span></div>
  </div>

  <div id="chat" class="panel chat-win clip" data-start="{t_gen:.3f}" data-duration="{d_chat:.3f}">
    <div class="chat-head">Генерация поста</div>
    <div class="chat-body"><span id="typed"></span><span class="cursor"></span></div>
  </div>

  <div id="metrics" class="panel card-right clip" data-start="{t_metrics:.3f}" data-duration="{d_met:.3f}">
    <div class="title">Метрики</div>
    <div class="counter" id="cnt">0</div>
    <div class="bar-wrap"><div class="bar" id="bar"></div></div>
  </div>

  <div id="scale" class="panel card-left clip" data-start="{t_ai:.3f}" data-duration="{d_scl:.3f}">
    <div class="title">AI-анализ</div>
    <div class="body">Риски · Акции · Клиент</div>
    <div class="bar-wrap"><div class="bar" id="bar2"></div></div>
  </div>

  <div id="steps" class="panel card-right clip" data-start="{t_local:.3f}" data-duration="{d_stp:.3f}">
    <div class="title">Модели</div>
    <div class="stepper">
      <div class="step" id="s1">1</div><div class="step" id="s2">2</div><div class="step" id="s3">3</div>
    </div>
    <div class="body" style="margin-top:12px;font-size:22px">Локальные → Внешние → Сводка</div>
  </div>

{subs_block}</div>
<script>
const expo = {{ out: p => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)), in: p => (p <= 0 ? 0 : Math.pow(2, 10 * (p - 1))) }};
const tl = gsap.timeline({{ paused: true }});

function pop(el, t, d=0.45) {{
  tl.fromTo(el, {{ opacity:0, scale:0.85 }}, {{ opacity:1, scale:1.04, duration:d*0.55, ease:p=>expo.out(p) }}, t);
  tl.to(el, {{ scale:1, duration:d*0.45, ease:p=>expo.out(p) }}, t+d*0.55);
}}
function out(el, t, d=0.3) {{
  tl.to(el, {{ opacity:0, scale:0.92, duration:d, ease:p=>expo.in(p) }}, t);
}}

pop('#hook', {t_hook:.3f}); out('#hook', {o_hook:.3f});
tl.fromTo('#lt', {{ opacity:0, x:-48 }}, {{ opacity:1, x:0, duration:0.5, ease:p=>expo.out(p) }}, {lt_in:.3f});
out('#lt', {lt_in + min(lt_hold, max(1.0, dur - lt_in - 0.5)) - 0.45:.3f});
pop('#cal', {t_cal:.3f});
tl.fromTo('#cal-line', {{ width:0 }}, {{ width:'100%', duration:0.35, ease:p=>expo.out(p) }}, {t_cal+0.2:.3f});
const calMsg = '28 мая · 4 события · клиенты';
let ci=0; for (const ch of calMsg) {{
  tl.call(()=>{{ document.getElementById('cal-text').textContent = calMsg.slice(0, ++ci); }}, null, {t_cal+0.35:.3f}+ci*0.03);
}}
out('#cal', {o_cal:.3f});

pop('#chk', {t_events:.3f});
{js_chk}
out('#chk', {o_chk:.3f});

pop('#chat', {t_gen:.3f});
const prompt = 'Сгенерируй пост про форум...';
let pi=0; for (const ch of prompt) {{
  tl.call(()=>{{ document.getElementById('typed').textContent = prompt.slice(0, ++pi); }}, null, {t_gen+0.4:.3f}+pi*0.04);
}}
for (let i=0;i<6;i++) {{ tl.set('.cursor', {{ opacity: i % 2 === 0 ? 0 : 1 }}, {t_gen+0.45:.3f}+i*0.18); }}
tl.set('.cursor', {{ opacity:0 }}, {t_gen+0.45:.3f}+prompt.length*0.04);
out('#chat', {o_chat:.3f});

pop('#metrics', {t_metrics:.3f});
tl.fromTo('#cnt', {{ innerText:0 }}, {{ innerText:24, duration:1.0, snap:'innerText', ease:p=>expo.out(p) }}, {t_metrics+0.3:.3f});
tl.fromTo('#bar', {{ width:'0%' }}, {{ width:'80%', duration:0.9, ease:p=>expo.out(p) }}, {t_metrics+0.35:.3f});
out('#metrics', {o_met:.3f});

pop('#scale', {t_ai:.3f});
tl.fromTo('#bar2', {{ width:'0%' }}, {{ width:'72%', duration:1.1, ease:p=>expo.out(p) }}, {t_ai+0.4:.3f});
out('#scale', {o_scl:.3f});

pop('#steps', {t_local:.3f});
{js_steps}
out('#steps', {o_stp:.3f});

{subs_js}
window.__timelines = window.__timelines || {{}};
window.__timelines['main'] = tl;
tl.seek(0);
</script>
</body>
</html>
"""
    out = comp_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Composition: {out} ({dur:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
