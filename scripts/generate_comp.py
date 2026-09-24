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
    root = Path(__file__).resolve().parents[1]
    edit = root / "runs" / "cursor" / "edit"
    data = json.loads((edit / "data.json").read_text(encoding="utf-8"))
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    dur, tl = edl_timeline(edl)
    subtitles_on = data.get("passport", {}).get("subtitles", False)
    subs_path = edit / "subtitles.json"
    subs = (
        json.loads(subs_path.read_text(encoding="utf-8"))
        if subtitles_on and subs_path.exists()
        else []
    )

    c = data["passport"]["colors"]
    comp_dir = edit / "comp"
    fonts_dir = comp_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    win = Path(r"C:\Windows\Fonts")
    for name in ["segoeui.ttf", "segoeuib.ttf"]:
        src = win / name
        if src.exists():
            shutil.copy2(src, fonts_dir / name)

    data["passport"]["fonts"] = {"accent": "Segoe UI Bold", "text": "Segoe UI"}
    data["passport"]["fps"] = 30
    (edit / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # key times from EDL text search
    def find_t(substr: str) -> float:
        for row in tl:
            if substr.lower() in row["text"].lower():
                return row["t0"] + 0.4
        return 0.0

    t_hook = 0.1
    t_factory = find_t("контент")
    t_cal = find_t("календар")
    t_events = find_t("рыночные")
    t_gen = find_t("Сгенерировать") or find_t("генер")
    t_metrics = find_t("метрик")
    t_ai = find_t("искусственный интеллект")
    t_local = find_t("локальными моделями")

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
    (edit / "graphics_plan.md").write_text(
        "| время | элемент | анимация | звук |\n|---|---|---|---|\n"
        + "\n".join(
            f"| {g['t']:.1f} | {g['el']} | {g['label']} | — |" for g in graphics
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
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face {{ font-family:'Segoe UI'; src:url('fonts/segoeui.ttf'); }}
@font-face {{ font-family:'Segoe UI Bold'; src:url('fonts/segoeuib.ttf'); font-weight:700; }}
html,body {{ margin:0; width:1920px; height:1080px; overflow:hidden; background:transparent; }}
*{{
  box-sizing:border-box;
  -webkit-font-smoothing:antialiased;
}}
.panel {{
  background:{c['dark_panel']}; border:1px solid rgba(255,255,255,.08);
  border-radius:22px; box-shadow:0 12px 40px rgba(0,0,0,.35);
  color:{c['white']}; font-family:'Segoe UI',sans-serif;
}}
.hook {{
  position:absolute; left:50%; top:8%; transform:translateX(-50%);
  font:700 92px/1 'Segoe UI Bold',sans-serif; color:{c['accent1']};
  text-shadow:0 4px 24px rgba(0,0,0,.45); opacity:0;
}}
.word-behind {{
  position:absolute; left:50%; top:34%; transform:translate(-50%,-50%) scale(.84);
  font:900 118px/1 'Segoe UI Bold',sans-serif; color:{c['accent1']}; opacity:0; white-space:nowrap;
}}
.card-right {{
  position:absolute; right:3.8%; top:14%; width:26%; min-height:120px; padding:18px 20px; opacity:0;
}}
.card-left {{
  position:absolute; left:3.8%; top:18%; width:24%; padding:16px 18px; opacity:0;
}}
.title {{ font:700 34px/1.1 'Segoe UI Bold',sans-serif; margin:0 0 10px; color:{c['accent2']}; }}
.body {{ font:400 26px/1.35 'Segoe UI',sans-serif; }}
.line {{ height:3px; background:{c['accent1']}; width:0; margin:8px 0 12px; border-radius:2px; }}
.item {{ display:flex; gap:10px; align-items:flex-start; margin:8px 0; font:400 24px/1.3 'Segoe UI',sans-serif; opacity:0; transform:translateY(8px); }}
.tick {{ width:22px; height:22px; flex:0 0 22px; border:2px solid {c['accent2']}; border-radius:6px; position:relative; }}
.tick.on::after {{ content:''; position:absolute; left:4px; top:1px; width:8px; height:14px; border-right:3px solid {c['accent1']}; border-bottom:3px solid {c['accent1']}; transform:rotate(45deg); }}
.chat-win {{ position:absolute; right:4%; top:16%; width:27%; padding:0; overflow:hidden; opacity:0; }}
.chat-head {{ background:#27272a; padding:10px 14px; font:600 22px/1 'Segoe UI Bold',sans-serif; }}
.chat-body {{ padding:14px; font:400 24px/1.4 'Segoe UI',sans-serif; min-height:140px; }}
.cursor {{ display:inline-block; width:2px; height:1em; background:{c['accent1']}; vertical-align:text-bottom; animation:blink .8s step-end infinite; }}
@keyframes blink {{ 50% {{ opacity:0; }} }}
.counter {{ font:700 64px/1 'Segoe UI Bold',sans-serif; color:{c['accent1']}; letter-spacing:.04em; }}
.bar-wrap {{ height:12px; background:#3f3f46; border-radius:8px; overflow:hidden; margin-top:12px; }}
.bar {{ height:100%; width:0; background:linear-gradient(90deg,{c['accent1']},{c['accent2']}); }}
.stepper {{ display:flex; gap:12px; align-items:center; margin-top:10px; }}
.step {{ width:36px; height:36px; border-radius:50%; border:2px solid #52525b; display:flex; align-items:center; justify-content:center; font:600 18px/1 'Segoe UI Bold',sans-serif; }}
.step.on {{ border-color:{c['accent1']}; background:{c['accent1']}; color:#111; }}
{subs_css}</style>
</head>
<body>
<div id="root" class="clip" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="1920" data-height="1080">

  <h1 id="hook" class="hook clip" data-start="{t_hook:.3f}" data-duration="3.2">Контент-завод</h1>

  <div id="word" class="word-behind clip" data-start="{t_factory:.3f}" data-duration="3.5" data-layout-allow-occlusion="true">КОНТЕНТ-ЗАВОД</div>

  <div id="cal" class="panel card-right clip" data-start="{t_cal:.3f}" data-duration="8">
    <div class="title">Календарь</div><div class="line" id="cal-line"></div>
    <div class="body" id="cal-text"></div>
  </div>

  <div id="chk" class="panel card-left clip" data-start="{t_events:.3f}" data-duration="10">
    <div class="title">События</div>
    <div class="item" id="i1"><span class="tick"></span><span>Рыночные</span></div>
    <div class="item" id="i2"><span class="tick"></span><span>Корпоративные</span></div>
    <div class="item" id="i3"><span class="tick"></span><span>Форумы</span></div>
  </div>

  <div id="chat" class="panel chat-win clip" data-start="{t_gen:.3f}" data-duration="9">
    <div class="chat-head">Генерация поста</div>
    <div class="chat-body"><span id="typed"></span><span class="cursor"></span></div>
  </div>

  <div id="metrics" class="panel card-right clip" data-start="{t_metrics:.3f}" data-duration="8">
    <div class="title">Метрики</div>
    <div class="counter" id="cnt">0</div>
    <div class="bar-wrap"><div class="bar" id="bar"></div></div>
  </div>

  <div id="scale" class="panel card-left clip" data-start="{t_ai:.3f}" data-duration="9">
    <div class="title">AI-анализ</div>
    <div class="body">Риски · Акции · Клиент</div>
    <div class="bar-wrap"><div class="bar" id="bar2"></div></div>
  </div>

  <div id="steps" class="panel card-right clip" data-start="{t_local:.3f}" data-duration="10">
    <div class="title">Модели</div>
    <div class="stepper">
      <div class="step" id="s1">1</div><div class="step" id="s2">2</div><div class="step" id="s3">3</div>
    </div>
    <div class="body" style="margin-top:12px;font-size:22px">Локальные → Внешние → Сводка</div>
  </div>

{subs_block}</div>
<script>
const expo = {{ out: p => 1 - Math.pow(1 - p, 3), in: p => Math.pow(p, 3) }};
const tl = gsap.timeline({{ paused: true }});

function pop(el, t, d=0.45) {{
  tl.fromTo(el, {{ opacity:0, scale:0.85 }}, {{ opacity:1, scale:1.04, duration:d*0.55, ease:p=>expo.out(p) }}, t);
  tl.to(el, {{ scale:1, duration:d*0.45, ease:p=>expo.out(p) }}, t+d*0.55);
}}
function out(el, t, d=0.3) {{
  tl.to(el, {{ opacity:0, scale:0.92, duration:d, ease:p=>expo.in(p) }}, t);
}}

pop('#hook', {t_hook:.3f}); out('#hook', {t_hook+2.5:.3f});
pop('#word', {t_factory:.3f}); out('#word', {t_factory+3.0:.3f});
pop('#cal', {t_cal:.3f});
tl.fromTo('#cal-line', {{ width:0 }}, {{ width:'100%', duration:0.35, ease:p=>expo.out(p) }}, {t_cal+0.2:.3f});
const calMsg = '28 мая · 4 события · клиенты';
let ci=0; for (const ch of calMsg) {{
  tl.call(()=>{{ document.getElementById('cal-text').textContent = calMsg.slice(0, ++ci); }}, null, {t_cal+0.35:.3f}+ci*0.03);
}}
out('#cal', {t_cal+7.2:.3f});

pop('#chk', {t_events:.3f});
{js_chk}
out('#chk', {t_events+9:.3f});

pop('#chat', {t_gen:.3f});
const prompt = 'Сгенерируй пост про форум...';
let pi=0; for (const ch of prompt) {{
  tl.call(()=>{{ document.getElementById('typed').textContent = prompt.slice(0, ++pi); }}, null, {t_gen+0.4:.3f}+pi*0.04);
}}
out('#chat', {t_gen+8:.3f});

pop('#metrics', {t_metrics:.3f});
tl.fromTo('#cnt', {{ innerText:0 }}, {{ innerText:24, duration:1.0, snap:'innerText', ease:p=>expo.out(p) }}, {t_metrics+0.3:.3f});
tl.fromTo('#bar', {{ width:'0%' }}, {{ width:'80%', duration:0.9, ease:p=>expo.out(p) }}, {t_metrics+0.35:.3f});
out('#metrics', {t_metrics+7.2:.3f});

pop('#scale', {t_ai:.3f});
tl.fromTo('#bar2', {{ width:'0%' }}, {{ width:'72%', duration:1.1, ease:p=>expo.out(p) }}, {t_ai+0.4:.3f});
out('#scale', {t_ai+8:.3f});

pop('#steps', {t_local:.3f});
{js_steps}
out('#steps', {t_local+9:.3f});

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
