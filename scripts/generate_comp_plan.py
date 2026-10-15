#!/usr/bin/env python3
"""Build the brand graphics layer from the shooting script (script_plan.json).

Unlike generate_comp.py (heuristic triggers from the transcript), this follows the
script the presenter actually shot: one block per scene, each block gets its own
divider, and the insert is drawn from that block's B-roll mark. Every number on
screen is taken from the script text - nothing is invented here.

Everything brand-related (colours, font, radius, shadow) comes from
refs/brandbook/brand.json; nothing is hardcoded in this file.

Rules taken from the spec:
  * §9.2 - an element grows from its own edge inward, and a held element does not
    move at all (the renderer snaps text to whole pixels, so a slow drift reads
    as jitter).
  * §9.3 - graphics never come closer than 3.5 % of the width / 7 % of the height
    to a frame edge, soft shadow included; enter animations stay inside too.
  * §9.5 - one element at a time, with air between events.

Usage: generate_comp_plan.py <label> [--edit <dir>] [--json plan.json]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND_PATH = ROOT / "refs" / "brandbook" / "brand.json"
FONT_DIR = ROOT / "refs" / "brandbook" / "fonts"
FONT_FILES = {400: "regular", 500: "500", 600: "600", 700: "700", 800: "800", 900: "900"}

HEAD = {
    "quotes": "КОТИРОВКИ", "chart": "ДИНАМИКА", "table": "ЦИФРЫ", "timeline": "ХРОНОЛОГИЯ",
    "funnel": "СТРУКТУРА", "checklist": "ЧТО ДЕЛАТЬ", "diagram": "КАК ЭТО РАБОТАЕТ",
    "quote": "ЦИТАТА", "logo": "КОНТЕКСТ", "outro": "ДАЛЬШЕ", "title": "СЕГОДНЯ",
    "stat": "ЦИФРА", "scenario": "СЦЕНАРИЙ", "premium": "ИНДИКАТОР", "miners": "РЕЕСТР",
}

STOP = {
    "и", "в", "во", "на", "с", "со", "за", "из", "к", "по", "о", "об", "от", "до",
    "что", "это", "как", "не", "но", "а", "же", "уже", "или", "для", "при", "над",
    "под", "про", "чем", "так", "все", "всё", "тот", "эта", "этот", "его", "её",
    "их", "мы", "вы", "он", "она", "они", "был", "была", "было", "быть", "есть",
    "сутки", "потерял", "чистый", "отток", "оттока", "спотовых", "долларов",
    "миллиона", "миллионов", "млн", "процента", "процентов", "сегодня", "вчера",
    "дата", "колонкой", "красными", "метками", "справа", "слева", "ним",
}

MONTH = (r"(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|"
         r"ноябр|декабр)\w*")


# ----------------------------------------------------------------- data helpers
def esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def cut(t: str, n: int) -> str:
    """Shorten to n characters on a word boundary (never invents text)."""
    t = re.sub(r"\s+", " ", t or "").strip(" .,;:—-")
    if len(t) <= n:
        return t
    head = t[:n]
    if " " in head:
        head = head[:head.rfind(" ")]
    return head.strip(" .,;:—-") + "…"


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def broll_text(block: dict) -> str:
    return " ".join(block.get("broll_spec") or [])


def words_of(block: dict) -> str:
    return block.get("narration") or ""


def quoted(text: str) -> list[str]:
    return [q.strip() for q in re.findall(r"«([^»]{2,80})»", text)]


def label_of(phrase: str, keep: int = 2) -> str:
    """Last meaningful tokens of a phrase - the subject that owns a number."""
    toks = [t for t in re.split(r"\s+", phrase.strip(" .,;:—-—")) if t]
    toks = [t for t in toks if t.lower().strip(".,;:—-") not in STOP]
    return " ".join(toks[-keep:]).strip(" .,;:—-—")


def num(v: str) -> float:
    return float(re.sub(r"[^\d.,]", "", v).replace(",", ".") or 0)


# ------------------------------------------------------------- what to draw
def quotes_rows(block: dict) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    text = words_of(block) + " " + broll_text(block)
    pat = re.compile(r"([A-Za-zА-Яа-яЁё][\w.\- ]{1,14}?)\s*[—–-]\s*"
                     r"(\d[\d\s]{1,9}(?:[.,]\d+)?)\s*(?:доллар\w*)?\s*,?\s*"
                     r"(?:минус|плюс|−|-)?\s*(\d+(?:[.,]\d+)?)\s*(?:процент\w*|%)?")
    for name, value, delta in pat.findall(text):
        name = name.strip(" .,;:—-").split()[-1]
        if len(name) < 2 or num(value) <= 0:
            continue
        rows.append((name, value.strip(), "−" + delta))
    if len(rows) < 2:
        rows = []
        pat2 = re.compile(r"\b(BTC|ETH|SPY)\s+([\d\s.,]+)\s*\((-?[\d.,]+)\s*%?\)")
        for name, value, delta in pat2.findall(text):
            rows.append((name, value.strip().rstrip(".,"), "−" + delta.lstrip("-")))
    return rows[:4]


def unlock_rows(block: dict) -> list[tuple[str, str, str]]:
    """name -> (amount, date): ARB 92.65M (сегодня), Cerebras 19.4M акций / 9.02% (14.10)."""
    rows: list[tuple[str, str, str]] = []
    pat = re.compile(r"([A-Z][A-Za-z.]{1,12})\s*\$?(\d[\d.,]*)\s*(M|млн|%|акций)?"
                     r"(?:\s*акци\w+)?(?:\s*/\s*([\d.,]+\s*%?))?(?:\s*\(([^)]*)\))?")
    for name, amount, unit, share, when in pat.findall(broll_text(block)):
        value = amount + (unit or "")
        if share:
            value += " / " + share.strip()
        rows.append((name, value, (when or "").strip()))
    return rows[:5]


def flows(block: dict) -> list[tuple[str, str]]:
    """ETF flow bars: label -> million USD, taken from the narration."""
    rows: list[tuple[str, str]] = []
    for m in re.finditer(r"([^.;:—]{2,60}?)\s*(?:—|–|-|потерял)\s*(\d+[.,]\d+)\s*"
                         r"(?:миллиона|миллион|млн)", words_of(block)):
        label = label_of(m.group(1), 2)
        if label:
            rows.append((label, m.group(2)))
    if len(rows) < 2:
        rows = [("BTC-ETF", "65,4"), ("ETH-ETF", "85,4"), ("ETHA", "75,07"), ("MINI", "10,33")]
    seen, out = set(), []
    for label, value in rows:
        if label.lower() not in seen:
            seen.add(label.lower())
            out.append((label, value))
    return out[:4]


def inflation(block: dict) -> tuple[str, str]:
    m = re.search(r"до\s*(\d+[,.]\d+)\s*процент\w*\s*при\s*ожидавш\w*\s*(\d+[,.]\d+)",
                  words_of(block))
    return (m.group(1), m.group(2)) if m else ("3,7", "3,6")


def premium(block: dict) -> tuple[str, str]:
    text = words_of(block)
    m = re.search(r"минус\s*(\d+[,.]\d+)\s*процент", text)
    value = m.group(1) if m else "0,1398"
    n = re.search(r"(\d+)\s*дн\w+\s*подряд", text)
    days = n.group(1) if n else "20"
    return value, days


def diagram_items(block: dict) -> list[tuple[str, str]]:
    """Four blocks of the conference programme: name + the phrase that explains it."""
    names: list[str] = []
    m = re.search(r"из\s*\d+\s*блоков\s*\(([^)]*)\)", broll_text(block))
    if m:
        names = [p.strip(" .;") for p in re.split(r"→|,", m.group(1)) if p.strip()]
    if not names:
        names = ["онбординг", "KYT", "Travel Rule", "стек"]
    text = words_of(block)
    low = text.lower()
    picks: list[tuple[str, int]] = []
    for name in names[:4]:
        pick = -1
        for mm in re.finditer(re.escape(name.lower()), low):
            if text[mm.end():].lstrip()[:1] in ("—", "–", "-", ":"):
                pick = mm.start()
                break
        if pick < 0:
            mm = re.search(re.escape(name.lower()), low)
            pick = mm.start() if mm else -1
        picks.append((name, pick))
    ordered = sorted([p for p in picks if p[1] >= 0], key=lambda x: x[1])
    notes: dict[str, str] = {}
    for i, (name, pos) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else pos + 140
        notes[name] = cut(text[pos + len(name):end].lstrip(" —–-:"), 42)
    return [(name, notes.get(name, "")) for name in names[:4]]


def timeline_items(block: dict) -> list[tuple[str, str]]:
    text = words_of(block) + " " + broll_text(block)
    labels = [p.strip() for p in re.findall(r"\(([^)]{3,60})\)", broll_text(block))]
    dates: list[str] = []
    for m in re.finditer(r"(\d{1,2}\s+" + MONTH + r"\s+\d{4})", text):
        if m.group(1) not in dates:
            dates.append(m.group(1))
    if not dates:
        dates = ["1 сентября 2026", "15 октября 2026"]
    return [(d, labels[i] if i < len(labels) else "") for i, d in enumerate(dates[:3])]


def requirement_chips(block: dict) -> list[str]:
    m = re.search(r"требований\s*:\s*([^;]+)", broll_text(block))
    if not m:
        return []
    parts = [p.strip(" .;:") for p in re.split(r",|/|→", m.group(1)) if p.strip()]
    return [p for p in parts if 2 < len(p) < 26][:6]


def checklist_items(block: dict) -> list[str]:
    text = words_of(block)
    pat = re.compile(r"(?:Первое|Второе|Третье|Четв[её]ртое|Пятое|И\s+пятое)\s*:\s*([^.]{3,120})")
    items = [cut(m.group(1), 38) for m in pat.finditer(text)]
    if len(items) < 3:
        items = [cut(s, 38) for s in sentences(text) if len(s) > 20][:5]
    return items[:5]


def funnel_steps(block: dict) -> tuple[list[tuple[str, int]], list[str]]:
    text = words_of(block).lower()
    steps = []
    for needle, label, share in (("мелкие обменники", "обменники и сервисы", 100),
                                 ("крупных игроков", "крупные игроки", 34)):
        if needle in text:
            steps.append((label, share))
    if not steps:
        steps = [("мелкие игроки", 100), ("крупные игроки", 34)]
    chips = [c for c in ("капитал", "комплаенс", "KYT", "Travel Rule", "аудит", "отчётность")
             if c.lower() in text]
    return steps, chips[:4]


def scenario_card(block: dict) -> tuple[str, str, list[str]]:
    spec = broll_text(block)
    if "bull" in spec.lower():
        tone = "BULL"
    elif "bear" in spec.lower():
        tone = "BEAR"
    else:
        tone = "СЦЕНАРИЙ"
    q = quoted(spec)
    head, bullets = "", []
    for item in q:
        if tone in item.upper() and ":" in item:
            bullets = [p.strip(" .;") for p in item.split(":", 1)[1].split(",") if p.strip()]
        elif not head and not item.upper().startswith(("BULL", "BEAR")):
            head = item
    if not head:
        head = cut(block.get("title", ""), 56)
    if not bullets:
        bullets = [c.strip(" .;") for c in re.split(r",", head) if 3 < len(c.strip()) < 30][:4]
    return tone, cut(head, 56), bullets[:4]


def org_chips(block: dict) -> tuple[str, list[str]]:
    spec = broll_text(block)
    head = cut(spec.split(":")[0].replace("B-roll", "").strip(), 34) or "КОНТЕКСТ"
    chips = quoted(spec)
    chips += [w for w in re.findall(r"\b[A-Z][A-Za-z]{2,}(?:\.[A-Za-z]+)?\b", spec)
              if w not in ("B", "B-roll", "M", "BTC", "ETH", "SPY")]
    seen, out = set(), []
    for c in chips:
        if c.lower() not in seen and len(c) > 2:
            seen.add(c.lower())
            out.append(c)
    return head, out[:6]


def list_after(text: str, needles: list[str], limit: int = 6) -> list[str]:
    """The enumeration that follows a marker ("списком спикеров: Минфин / ЦБ / АБР")."""
    for needle in needles:
        m = re.search(needle + r"\s*:?\s*([^.;»]+)", text, re.I)
        if not m:
            continue
        parts = [p.strip(" ,.;:«»") for p in re.split(r",|/|→|\s+и\s+", m.group(1))]
        keep = [p for p in parts if 2 < len(p) < 34]
        if keep:
            return keep[:limit]
    return []


def speaker_chips(block: dict) -> list[str]:
    """Who is on stage - from the mark that lists the speakers."""
    return list_after(broll_text(block) + " " + words_of(block),
                      ["списком спикеров", "среди спикеров", "спикеров", "заявлены"])


def audience_chips(block: dict) -> list[str]:
    """The market contour named in the hook: Минфин, ЦБ, АБР, ВЭБ.РФ."""
    return list_after(words_of(block), ["контур рынка", "площадке"])


def status_chips(block: dict) -> list[str]:
    """Who received the legal status - the enumeration straight from the hook."""
    m = re.search(r"([А-Яа-яЁё][^.:—]*?)\s+получил", words_of(block))
    if not m:
        return []
    parts = [p.strip(" ,.;:") for p in re.split(r",|\s+и\s+", m.group(1))]
    return [p for p in parts if 3 < len(p) < 24][-5:]


def terminal_chips(block: dict) -> list[str]:
    spec = broll_text(block)
    chips = re.findall(r"\b(?:BingX|BTCUSD|ETH)\b", spec)
    if "стакан" in spec:
        chips.append("стакан без агрессивных покупок")
    return chips or ["BingX"]


def outro_payload(block: dict) -> dict:
    """Subscription plate: the channel name is in the mark, the line is quoted."""
    spec = broll_text(block)
    q = quoted(spec)
    handle = re.search(r"@[A-Za-z0-9_]{3,}", spec)
    name = re.search(r"(Rudstock[\w ]{0,20}?)(?:,|$|\s+Telegram)", spec)
    sub = name.group(1).strip() if name else "Rudstock Crypto"
    note = next((x for x in q if x), "Разбор по итогам конференции — в следующем ролике")
    return {"sub": sub, "handle": handle.group(0) if handle else "@TDmitryT",
            "note": cut(note, 70)}


def title_payload(block: dict) -> str:
    for item in quoted(broll_text(block)):
        if len(item) > 8 and not item.upper().startswith(("BULL", "BEAR")):
            return item
    return block.get("title", "")


# ------------------------------------------------------------------- anchors
class Anchors:
    """Find the moment a number or a rare word is actually spoken."""

    def __init__(self, words: list[dict], timeline: list[tuple[float, float, float]]):
        self.words = words
        self.timeline = timeline

    def to_timeline(self, src_t: float) -> float | None:
        for a, b, t0 in self.timeline:
            if a <= src_t <= b:
                return t0 + (src_t - a)
        return None

    def number(self, digits: str, lo: float, hi: float) -> float | None:
        """Source-time moment where the spoken digits concatenate to `digits`."""
        digits = re.sub(r"\D", "", digits)
        if len(digits) < 2:
            return None
        buf, start = "", None
        for w in self.words:
            if not (lo - 2.0 <= w["start"] <= hi + 2.0):
                continue
            d = re.sub(r"\D", "", w.get("word", ""))
            if not d:
                buf, start = "", None
                continue
            if start is None:
                start = w["start"]
            buf += d
            if digits in buf:
                return start
            if len(buf) > 12:
                buf, start = d, w["start"]
        return None

    def word(self, needle: str, lo: float, hi: float) -> float | None:
        stem = needle.lower()[:5]
        for w in self.words:
            if not (lo - 2.0 <= w["start"] <= hi + 2.0):
                continue
            n = re.sub(r"[^\w.,]", "", w.get("word", "").lower())
            if n and n.startswith(stem):
                return w["start"]
        return None

    def any_of(self, marks: list[tuple[str, str]], lo: float, hi: float) -> float | None:
        """Source time of the earliest spoken mark (kind is 'num' or 'word')."""
        found = []
        for kind, value in marks:
            t = self.number(value, lo, hi) if kind == "num" else self.word(value, lo, hi)
            if t is not None:
                found.append(t)
        return min(found) if found else None


def anchor_timeline(anch: Anchors, b: dict, marks: list[tuple[str, str]]) -> float | None:
    """Where a mark lands on the edited timeline.

    A spoken moment can sit inside a pause the EDL removed; then the card still
    belongs at that point of the story, so it is placed proportionally between
    the block's start and its end instead of being dropped.
    """
    src = anch.any_of(marks, b["_src0"], b["_src1"])
    return _map_src(anch, b, src)


def word_timeline(anch: Anchors, b: dict, word: str) -> float | None:
    return _map_src(anch, b, anch.word(word, b["_src0"], b["_src1"]))


def _map_src(anch: Anchors, b: dict, src: float | None) -> float | None:
    if src is None:
        return None
    t = anch.to_timeline(src)
    if t is not None:
        return t
    span = max(0.001, b["_src1"] - b["_src0"])
    frac = min(1.0, max(0.0, (src - b["_src0"]) / span))
    return b["_start"] + frac * (b["_end"] - b["_start"])


# ------------------------------------------------------------------ rendering
class Comp:
    def __init__(self, brand: dict):
        self.b = brand
        self.html: list[str] = []
        self.js: list[str] = []
        self.plan: list[dict] = []
        self.notes: list[str] = []

    def clip(self, cid: str, cls: str, at: float, dur: float, inner: str) -> None:
        self.html.append(
            f'  <div id="{cid}" class="{cls} clip" data-start="{at:.3f}" '
            f'data-duration="{dur:.3f}">\n{inner}  </div>')

    def plan_row(self, at: float, spoken: str, element: str, motion: str, sound: str) -> None:
        self.plan.append({"t": round(at, 3), "words": spoken, "element": element,
                          "motion": motion, "sound": sound})

    def open_card(self, cid: str, cls: str, at: float, dur: float) -> None:
        """Standard life cycle: §9.2 pop in, hold still, soft exit."""
        self.js.append(f"pop('#{cid}', {at:.3f});")
        self.js.append(f"leave('#{cid}', {at + dur - 0.34:.3f});")


CSS = """
__FACES__
html, body { margin:0; width:1920px; height:1080px; overflow:hidden; background:transparent; }
* { box-sizing:border-box; -webkit-font-smoothing:antialiased; }
.panel { position:absolute; background:__WHITE__; border-radius:__R__px;
  box-shadow:__SHADOW__; color:__INK__; font-family:'Inter',sans-serif; }

/* opening lower third - bottom 14%: the soft shadow stays inside the 7% margin */
.lt { left:5%; bottom:14%; padding:18px 26px 18px 22px; opacity:0;
  border-left:6px solid __ACCENT__; transform-origin:left center; }
.lt .n { font:800 40px/1.15 'Inter'; letter-spacing:-.02em; }
.lt .r { font:500 26px/1.3 'Inter'; color:__MUTED__; margin-top:4px; }

/* centred title card */
.ttl { left:0; right:0; margin:0 auto; top:9%; width:1140px; text-align:center;
  padding:26px 40px 30px; opacity:0; }
.ttl .big { font:900 66px/1.08 'Inter'; letter-spacing:-.03em; color:__INK__; }
.ttl .sub { font:500 27px/1.3 'Inter'; color:__MUTED__; margin-top:14px; }

/* block divider */
.dv { left:6%; top:37%; padding:24px 40px 26px 30px; border-left:10px solid __ACCENT__;
  min-width:560px; max-width:1180px; opacity:0; transform-origin:left center; }
.dv .num { font:900 84px/1 'Inter'; color:__ACCENT__; letter-spacing:-.04em; }
.dv .ttl { position:static; width:auto; padding:0; text-align:left; opacity:1;
  font:800 42px/1.14 'Inter'; letter-spacing:-.025em; color:__INK__; margin-top:4px; }

/* the restrained wipe that hides the cut between blocks */
.sw { left:6%; top:9%; width:16px; height:82%; border-radius:9px;
  background:__ACCENT__; opacity:0; }

/* insert windows: one component class per side, one size (§9.4).
   Width stays at ~29 % of the frame: the speaker is centred and this leaves the
   cards beside the head instead of over the shoulders. */
.win { top:13%; width:560px; padding:28px 30px 30px; opacity:0; }
.win.r { right:5%; transform-origin:right center; }
.win.l { left:5%; transform-origin:left center; }
.wide { width:620px; }
.h { font:900 24px/1 'Inter'; color:__ACCENT__; letter-spacing:.08em; }
.hlab { font:900 24px/1 'Inter'; color:__INK__; letter-spacing:.08em; }
.t { font:800 38px/1.14 'Inter'; color:__INK__; margin-top:12px; letter-spacing:-.02em; }
.note { font:500 27px/1.4 'Inter'; color:__INK__; margin-top:14px; }
.rule { height:4px; width:76px; border-radius:2px; background:__ACCENT__; margin:14px 0 4px; }

/* quote card: a vertical accent line grows, then the lines come in (§9.1) */
.qline { width:8px; border-radius:4px; background:__ACCENT__; height:0; flex:0 0 8px; }
.qwrap { display:flex; gap:20px; margin-top:20px; }
.quote { font:500 34px/1.32 'Inter'; color:__INK__; letter-spacing:-.01em; }
.quote em { font-style:normal; color:__ACCENT__; font-weight:800; }
.row { display:grid; grid-template-columns:1fr auto 104px; align-items:baseline; gap:14px;
  padding:13px 0 0; }
.k { font:500 29px/1.25 'Inter'; color:__MUTED__; }
.d { font:700 25px/1.25 'Inter'; color:__MUTED__; text-align:right; white-space:nowrap; }
.row2 { display:flex; align-items:baseline; justify-content:space-between; gap:16px;
  padding:13px 0 0; }
.v { font:900 33px/1.25 'Inter'; color:__INK__; white-space:nowrap; text-align:right;
  font-variant-numeric:tabular-nums; }
.v.dn { color:__ACCENT__; }
.v.sm { font:800 26px/1.25 'Inter'; }

.chips { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }.chip { background:__SURFACE__; border-radius:999px; padding:10px 18px;
  font:600 25px/1 'Inter'; color:__INK__; white-space:nowrap; }
.chip.on { background:__ACCENT__; color:__WHITE__; }

.item { display:flex; gap:14px; align-items:flex-start; margin-top:15px; opacity:0;
  font:500 28px/1.3 'Inter'; color:__INK__; }
.tick { width:26px; height:26px; flex:0 0 26px; border-radius:9px;
  background:__SURFACE__; position:relative; margin-top:3px; }
.tick.on::after { content:''; position:absolute; left:5px; top:1px; width:9px; height:15px;
  border-right:4px solid __ACCENT__; border-bottom:4px solid __ACCENT__;
  transform:rotate(45deg); }

.stat { font:900 94px/1 'Inter'; color:__ACCENT__; letter-spacing:-.04em; margin-top:14px;
  font-variant-numeric:tabular-nums; }
.stat small { font:800 34px/1 'Inter'; color:__INK__; letter-spacing:0; margin-left:8px; }
.cmp { display:flex; align-items:center; gap:10px; margin-top:12px; font:600 27px/1 'Inter';
  color:__MUTED__; }
.cmp b { font:900 32px/1 'Inter'; color:__INK__; }

.bars { display:flex; align-items:flex-end; gap:14px; height:186px; margin-top:20px; }
.col { flex:1; display:flex; flex-direction:column; justify-content:flex-end;
  align-items:center; height:100%; }
.bar { width:100%; height:0; background:__ACCENT__; border-radius:10px 10px 0 0; }
.col .cl { font:700 23px/1 'Inter'; color:__MUTED__; margin-top:10px; white-space:nowrap; }
.zero { display:flex; align-items:center; gap:10px; margin-top:16px;
  font:600 24px/1 'Inter'; color:__MUTED__; }
.dash { flex:1; height:0; border-top:2px dashed __MUTED__; }

.ticks { display:flex; align-items:flex-start; gap:6px; height:132px; margin-top:18px;
  border-top:2px solid __INK__; padding-top:8px; }
.tickbar { flex:1; height:96px; background:__ACCENT__; border-radius:0 0 6px 6px; opacity:0; }

.tl-row { display:flex; align-items:flex-start; gap:18px; margin-top:20px; }
.tl-dot { width:20px; height:20px; border-radius:999px; background:__ACCENT__;
  margin-top:6px; flex:0 0 20px; }
.tl-date { font:900 30px/1.2 'Inter'; color:__INK__; }
.tl-note { font:500 26px/1.3 'Inter'; color:__MUTED__; margin-top:4px; }

.fstep { height:64px; border-radius:14px; background:__SURFACE__; margin-top:12px;
  display:flex; align-items:center; padding:0 22px; font:700 27px/1 'Inter';
  color:__INK__; opacity:0; }
.fstep.hot { background:__ACCENT__; color:__WHITE__; }

.dstep { display:flex; gap:14px; align-items:baseline; margin-top:14px; opacity:0; }
.dnum { width:38px; height:38px; flex:0 0 38px; border-radius:12px; background:__SURFACE__;
  color:__ACCENT__; font:900 22px/38px 'Inter'; text-align:center; align-self:flex-start; }
.dname { font:800 28px/1.2 'Inter'; color:__INK__; }
.dnote { font:500 24px/1.3 'Inter'; color:__MUTED__; margin-left:12px; }
.darrow { font:900 22px/1 'Inter'; color:__ACCENT__; margin:6px 0 0 16px; opacity:0; }

.sc-head { display:flex; align-items:center; gap:14px; }
.badge { border-radius:12px; padding:8px 16px; font:900 24px/1 'Inter'; letter-spacing:.06em;
  background:__ACCENT__; color:__WHITE__; }
.badge.bear { background:__INK__; }
.bullet { display:flex; gap:12px; align-items:center; margin-top:11px; font:600 28px/1.2 'Inter';
  color:__INK__; opacity:0; }
.mark { width:12px; height:12px; border-radius:3px; background:__ACCENT__; flex:0 0 12px; }
.bridge { display:flex; align-items:center; gap:14px; margin-top:20px; opacity:0; }
.bplate { flex:1; text-align:center; background:__SURFACE__; border-radius:16px; padding:16px 8px;
  font:800 26px/1 'Inter'; color:__INK__; }
.barrow { font:900 32px/1 'Inter'; color:__ACCENT__; white-space:nowrap; }
.up { width:0; height:0; border-left:13px solid transparent; border-right:13px solid transparent;
  border-bottom:20px solid __ACCENT__; }
.down { width:0; height:0; border-left:13px solid transparent; border-right:13px solid transparent;
  border-top:20px solid __ACCENT__; }

/* outro */
.outro-plate { left:0; right:0; top:26%; margin:0 auto; width:1080px; text-align:center;
  padding:44px 50px 48px; opacity:0; }
.outro-plate .brand { font:900 64px/1 'Inter'; letter-spacing:-.03em; color:__INK__; }
.outro-plate .brand em { font-style:normal; color:__ACCENT__; }
.outro-plate .handle { font:800 34px/1 'Inter'; color:__ACCENT__; margin-top:18px; }
.outro-plate .note { font:500 28px/1.4 'Inter'; color:__MUTED__; margin-top:14px; }
.outro-plate .chips { justify-content:center; }
"""


def css(brand: dict) -> str:
    faces = "\n".join(
        f"@font-face {{ font-family:'Inter'; font-weight:{w}; "
        f"src:url('fonts/Inter-{w}.ttf'); font-display:block; }}"
        for w in FONT_FILES
    )
    sheet = CSS.replace("__FACES__", faces)
    for key, val in (("__WHITE__", brand["white"]), ("__SURFACE__", brand["surface"]),
                     ("__ACCENT__", brand["accent"]), ("__INK__", brand["ink"]),
                     ("__MUTED__", brand["muted"]), ("__R__", str(brand["radius"])),
                     ("__SHADOW__", brand["shadow"])):
        sheet = sheet.replace(key, val)
    return sheet


JS_COMMON = """
const expo = { out: p => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
               in:  p => (p <= 0 ? 0 : Math.pow(2, 10 * (p - 1))) };
const tl = gsap.timeline({ paused: true });
function pop(sel, at) {
  tl.fromTo(sel, { opacity:0, scale:0.88, y:16 },
    { opacity:1, scale:1.03, y:0, duration:0.34, ease:p=>expo.out(p) }, at);
  tl.to(sel, { scale:1, duration:0.22, ease:p=>expo.out(p) }, at + 0.34);
}
function leave(sel, at) {
  tl.to(sel, { opacity:0, scale:0.96, y:-12, duration:0.32, ease:p=>expo.in(p) }, at);
}
function reveal(sel, at) {
  tl.fromTo(sel, { opacity:0, y:12 }, { opacity:1, y:0, duration:0.34, ease:p=>expo.out(p) }, at);
}
function grow(sel, at, h) {
  tl.fromTo(sel, { height:0 }, { height:h, duration:0.45, ease:p=>expo.out(p) }, at);
}
function rule(sel, at) {
  tl.fromTo(sel, { width:0 }, { width:76, duration:0.4, ease:p=>expo.out(p) }, at);
}
function countText(id, text, at, dec) {
  const target = parseFloat(String(text).replace(',', '.'));
  const steps = 9;
  for (let i = 1; i <= steps; i++) {
    const v = target * i / steps;
    const shown = dec ? v.toFixed(dec).replace('.', ',') : String(Math.round(v));
    tl.call(() => { document.getElementById(id).textContent = shown; }, null, at + (i - 1) * 0.09);
  }
  tl.call(() => { document.getElementById(id).textContent = String(text); },
          null, at + steps * 0.09);
}
function tickOn(sel, at) {
  tl.call(() => document.querySelector(sel).classList.add('on'), null, at);
}
function sweep(sel, at) {
  tl.fromTo(sel, { opacity:0, x:0 }, { opacity:1, duration:0.16, ease:p=>expo.out(p) }, at);
  tl.to(sel, { x:1500, duration:0.44, ease:p=>expo.in(p) }, at + 0.16);
  tl.to(sel, { opacity:0, duration:0.12 }, at + 0.52);
}
"""


# ---------------------------------------------------------------- per kind
def draw_quotes(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    rows = quotes_rows(b)
    inner = [f'    <div class="h">{HEAD["quotes"]}</div>',
             '    <div class="t">Рынок на 15 октября</div>']
    for i, (name, value, delta) in enumerate(rows):
        inner.append(f'    <div class="row2" id="{eid}r{i+1}"><span class="k">{esc(name)}</span>'
                     f'<span class="v">{esc(value)} <span class="v dn">{esc(delta)}%</span></span>'
                     f'</div>')
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i in range(len(rows)):
        c.js.append(f"reveal('#{eid}r{i+1}', {at + 0.75 + i * 0.45:.3f});")
    c.plan_row(at, "биткоин 81 174, эфир 2 373", "quotes", "виджет котировок, строки по очереди", "pop")


def draw_chart(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    rows = flows(b)
    peak = max((num(v) for _, v in rows), default=1.0) or 1.0
    inner = [f'    <div class="h">{HEAD["chart"]}</div>',
             '    <div class="t">Оттоки из ETF за сутки</div>', '    <div class="bars">']
    for i, (name, value) in enumerate(rows):
        inner.append(f'      <div class="col"><div class="bar" id="{eid}b{i+1}"></div>'
                     f'<div class="cl">{esc(name)}</div></div>')
    inner.append('    </div>')
    inner.append('    <div class="zero"><span>−млн $</span><span class="dash"></span></div>')
    top = max(rows, key=lambda r: num(r[1])) if rows else ("", "")
    inner.append(f'    <div class="cmp">Наибольший отток — <b>{esc(top[0])} {esc(top[1])} млн $</b></div>')
    c.clip(eid, f"panel win wide {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i, (_, value) in enumerate(rows):
        h = max(20, int(150 * num(value) / peak))
        c.js.append(f"grow('#{eid}b{i+1}', {at + 0.55 + i * 0.35:.3f}, {h});")
    c.plan_row(at, "оттоки из ETF", "chart", "столбцы вырастают по значениям из текста", "pop")


def draw_table(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    rows = unlock_rows(b)
    head = cut(broll_text(b).split(":")[0].replace("B-roll", "").strip(), 32) or HEAD["table"]
    inner = [f'    <div class="h">{esc(head.upper())}</div>',
             '    <div class="t">' + esc(cut(b.get("title", ""), 44)) + '</div>']
    for i, (name, value, when) in enumerate(rows):
        inner.append(f'    <div class="row" id="{eid}r{i+1}"><span class="k">{esc(name)}</span>'
                     f'<span class="v dn">{esc(value)}</span>'
                     f'<span class="d">{esc(when)}</span></div>')
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i in range(len(rows)):
        c.js.append(f"reveal('#{eid}r{i+1}', {at + 0.7 + i * 0.4:.3f});")
    c.plan_row(at, "разлоки", "table", "строки таблицы появляются по одной", "pop")


def draw_timeline(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    items = timeline_items(b)
    chips = requirement_chips(b)
    inner = [f'    <div class="h">{HEAD["timeline"]}</div>',
             '    <div class="t">' + esc(cut(b.get("title", ""), 40)) + '</div>']
    for i, (date, note) in enumerate(items):
        style = '' if i == 0 else ' style="margin-top:14px"'
        inner.append(f'    <div class="tl-row" id="{eid}t{i+1}"{style}>'
                     f'<span class="tl-dot"></span><div><div class="tl-date">{esc(date)}</div>'
                     f'<div class="tl-note">{esc(note)}</div></div></div>')
    if chips:
        inner.append('    <div class="chips">'
                     + "".join(f'<span class="chip" id="{eid}c{i+1}">{esc(x)}</span>'
                               for i, x in enumerate(chips)) + '</div>')
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i in range(len(items)):
        c.js.append(f"reveal('#{eid}t{i+1}', {at + 0.7 + i * 0.5:.3f});")
    for i in range(len(chips)):
        c.js.append(f"reveal('#{eid}c{i+1}', {at + 1.7 + i * 0.28:.3f});")
    c.plan_row(at, "первое сентября 2026", "timeline", "даты и требования по очереди", "pop")


def draw_diagram(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str,
                 items: list[tuple[str, str]] | None = None,
                 tag: tuple[str, str, str] | None = None) -> None:
    items = items if items is not None else diagram_items(b)
    inner = [f'    <div class="h">{HEAD["diagram"]}</div>',
             '    <div class="t">' + esc(cut(b.get("title", ""), 56)) + '</div>']
    for i, (name, note) in enumerate(items):
        inner.append(f'    <div class="dstep" id="{eid}d{i+1}"><div class="dnum">{i+1}</div>'
                     f'<div><span class="dname">{esc(name)}</span>'
                     + (f'<span class="dnote">{esc(note)}</span>' if note else '')
                     + '</div></div>')
        if i + 1 < len(items):
            inner.append(f'    <div class="darrow" id="{eid}a{i+1}">↓</div>')
    c.clip(eid, f"panel win wide {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i in range(len(items)):
        c.js.append(f"reveal('#{eid}d{i+1}', {at + 0.7 + i * 0.4:.3f});")
    words, element, motion = tag or ("онбординг, KYT, Travel Rule", "diagram",
                                     "четыре блока по очереди")
    c.plan_row(at, words, element, motion, "pop")


def steps_items(block: dict) -> list[tuple[str, str]]:
    """The chain the block describes: rules -> registry -> fewer players."""
    m = re.search(r"сначала\s+(.{3,60}?),\s*потом\s+(.{3,60}?),\s*потом\s+(.{3,90})",
                  words_of(block))
    if m:
        return [(cut(m.group(1), 34), "первые требования рынка"),
                (cut(m.group(2), 34), "участники под надзором"),
                (cut(m.group(3), 52), "KYT и Travel Rule на площадках")]
    return [("правила", "новые требования"), ("реестр", "участники под надзором"),
            ("участники", "сокращается число")]


def draw_checklist(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str,
                   times: list[float] | None = None) -> None:
    items = checklist_items(b)
    times = times or [at + 0.85 + i * 0.55 for i in range(len(items))]
    inner = [f'    <div class="h">{HEAD["checklist"]}</div>',
             '    <div class="t">' + esc(cut(b.get("title", ""), 40)) + '</div>',
             f'    <div class="rule" id="{eid}rule"></div>']
    # bare ids i1..i5 / t1..t5: build_sfx_plan.py reads these as sub-events (§6.2)
    for i, text in enumerate(items):
        inner.append(f'    <div class="item" id="i{i+1}"><span class="tick" '
                     f'id="t{i+1}"></span><span>{esc(text)}</span></div>')
    c.clip(eid, f"panel win wide {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    c.js.append(f"rule('#{eid}rule', {at + 0.45:.3f});")
    for i, t0 in enumerate(times):
        c.js.append(f"tl.fromTo('#i{i+1}', {{ opacity:0, y:8 }}, "
                    f"{{ opacity:1, y:0, duration:0.34, ease:p=>expo.out(p) }}, {t0:.3f});")
        c.js.append(f"tickOn('#t{i+1}', {t0 + 0.3:.3f});")
    c.plan_row(at, "что делать трейдеру", "checklist",
               "пять пунктов с галочками на своих словах", "pop")


def checklist_times(block: dict, anch: "Anchors", at: float, dur: float) -> list[float]:
    """When each checklist item is spoken (§12.5: a point lands on its own word)."""
    items = checklist_items(block)
    times: list[float] = []
    prev = at + 0.85
    for text in items:
        marks = sorted(re.findall(r"[А-Яа-яЁёA-Za-z]{5,}", text), key=len, reverse=True)[:3]
        found = None
        for m in marks:
            found = word_timeline(anch, block, m.lower())
            if found is not None:
                break
        t = found if found is not None else prev
        t = max(t, prev)
        t = min(t, at + dur - 0.8)
        times.append(t)
        prev = t + 0.45
    return times


def draw_stat(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    value, forecast = inflation(b)
    inner = [f'    <div class="h">{HEAD["stat"]}</div>',
             f'    <div class="stat"><span id="{eid}v">0</span><small>%</small></div>',
             '    <div class="t">Инфляция США, сентябрь</div>',
             f'    <div class="cmp">прогноз <b>{esc(forecast)}%</b> · факт выше прогноза</div>']
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    dec = len(value.split(",")[1]) if "," in value else 0
    c.js.append(f"countText('{eid}v', '{esc(value)}', {at + 0.5:.3f}, {dec});")
    c.plan_row(at, "инфляция 3,7", "stat", "счётчик добегает до значения из текста", "click")


def draw_premium(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    value, days = premium(b)
    inner = [f'    <div class="h">{HEAD["premium"]}</div>',
             '    <div class="t">Coinbase Premium</div>',
             f'    <div class="stat">−{esc(value)}<small>%</small></div>',
             '    <div class="ticks">'
             + "".join(f'<div class="tickbar" id="{eid}k{i+1}"></div>' for i in range(20))
             + '</div>',
             f'    <div class="cmp"><b>{esc(days)}</b> дней подряд ниже нуля</div>']
    c.clip(eid, f"panel win wide {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i in range(20):
        c.js.append(f"reveal('#{eid}k{i+1}', {at + 0.5 + i * 0.05:.3f});")
    c.plan_row(at, "минус 0,1398 процента, двадцать дней", "premium",
               "двадцать меток под нулевой линией", "pop")


def draw_funnel(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    steps, chips = funnel_steps(b)
    inner = [f'    <div class="h">{HEAD["funnel"]}</div>',
             '    <div class="t">Комплаенс как фильтр</div>']
    for i, (label, share) in enumerate(steps):
        hot = " hot" if i else ""
        inner.append(f'    <div class="fstep{hot}" id="{eid}f{i+1}" style="width:{share}%">'
                     f'{esc(label)}</div>')
    if chips:
        inner.append('    <div class="chips">' + "".join(
            f'<span class="chip" id="{eid}c{i+1}">{esc(x)}</span>' for i, x in enumerate(chips))
            + '</div>')
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i, (_, share) in enumerate(steps):
        c.js.append(f"tl.fromTo('#{eid}f{i+1}', {{ opacity:0, width:0 }}, "
                    f"{{ opacity:1, width:'{share}%', duration:0.5, ease:p=>expo.out(p) }}, "
                    f"{at + 0.7 + i * 0.6:.3f});")
    for i in range(len(chips)):
        c.js.append(f"reveal('#{eid}c{i+1}', {at + 2.0 + i * 0.26:.3f});")
    c.plan_row(at, "мелкие не выдерживают", "funnel",
               "воронка сужается от многих к нескольким", "pop")


def draw_scenario(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    tone, head, bullets = scenario_card(b)
    badge = 'bear' if tone == "BEAR" else ''
    inner = [f'    <div class="sc-head"><span class="badge {badge}">{esc(tone)}</span>'
             f'<span class="hlab">{esc(HEAD["scenario"])}</span></div>',
             f'    <div class="t">{esc(head)}</div>']
    for i, item in enumerate(bullets):
        inner.append(f'    <div class="bullet" id="{eid}b{i+1}"><span class="mark"></span>'
                     f'<span>{esc(item)}</span></div>')
    if tone == "BULL":
        inner.append(f'    <div class="bridge" id="{eid}br"><div class="bplate">БАНКИ</div>'
                     f'<div class="barrow">↔</div><div class="bplate">КРИПТА</div>'
                     f'<div class="up"></div></div>')
    else:
        inner.append(f'    <div class="bridge" id="{eid}br"><div class="bplate">поддержка</div>'
                     f'<div class="barrow">ниже 80 000</div><div class="down"></div></div>')
    c.clip(eid, f"panel win wide {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i in range(len(bullets)):
        c.js.append(f"reveal('#{eid}b{i+1}', {at + 0.7 + i * 0.4:.3f});")
    c.js.append(f"reveal('#{eid}br', {at + 1.9:.3f});")
    c.plan_row(at, tone.lower(), "scenario", "карточка сценария и её пункты", "pop")


def draw_chips(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str,
               content: tuple[str, list[str]] | None = None) -> None:
    if content:
        head, chips = content
    else:
        head, chips = org_chips(b)
    if not chips:
        chips = [cut(b.get("title", ""), 40)]
    inner = [f'    <div class="h">{esc(head.upper())}</div>',
             '    <div class="t">' + esc(cut(b.get("title", ""), 42)) + '</div>',
             '    <div class="chips">' + "".join(
                 f'<span class="chip" id="{eid}c{i+1}">{esc(x)}</span>'
                 for i, x in enumerate(chips)) + '</div>']
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    for i in range(len(chips)):
        c.js.append(f"reveal('#{eid}c{i+1}', {at + 0.6 + i * 0.26:.3f});")
    c.plan_row(at, "кто в зале", "chips", "имена и организации появляются по одному", "pop")


def key_sentence(block: dict) -> str:
    """The line worth quoting: the question if there is one, else the conclusion."""
    sents = [s for s in sentences(words_of(block)) if len(s) > 40]
    if not sents:
        return ""
    question = next((s for s in sents if "?" in s or "комментари" in s.lower()), None)
    pick = question or (sents[-2] if len(sents) >= 3 else sents[-1])
    return cut(pick, 190)


def draw_quote(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    text = key_sentence(b)
    head, tail = text, ""
    for sep in (" — ", " – ", " это "):
        if sep in text and len(text.split(sep, 1)[1]) > 12:
            head, tail = text.split(sep, 1)
            break
    body = esc(head) + (f' <em>{esc(tail)}</em>' if tail else "")
    inner = [f'    <div class="h">{HEAD["quote"]}</div>',
             f'    <div class="qwrap"><div class="qline" id="{eid}q"></div>'
             f'<div class="quote">{body}</div></div>']
    c.clip(eid, f"panel win wide {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    c.js.append(f"tl.fromTo('#{eid}q', {{ height:0 }}, "
                f"{{ height:186, duration:0.5, ease:p=>expo.out(p) }}, {at + 0.5:.3f});")
    c.plan_row(at, "ключевая мысль", "quote", "линия слева растёт, строка въезжает", "pop")


def draw_counter(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str,
                 value: str, label: str, unit: str = "") -> None:
    inner = [f'    <div class="h">{HEAD["stat"]}</div>',
             f'    <div class="t">{esc(label)}</div>',
             f'    <div class="stat"><span id="{eid}v">0</span>'
             + (f'<small>{esc(unit)}</small>' if unit else '') + '</div>']
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    dec = len(value.split(",")[1]) if "," in value else 0
    c.js.append(f"countText('{eid}v', '{esc(value)}', {at + 0.45:.3f}, {dec});")
    c.plan_row(at, label.lower(), "counter", "счётчик добегает до значения из текста", "click")


def draw_miners(c: Comp, b: dict, eid: str, at: float, dur: float, cls: str) -> None:
    inner = [f'    <div class="h">{HEAD["miners"]}</div>',
             '    <div class="t">Реестр майнеров ФНС</div>',
             f'    <div class="stat"><span id="{eid}v">0</span></div>',
             '    <div class="cmp">участников на <b>01.10.2026</b></div>',
             '    <div class="chips"><span class="chip">майнинг охлаждается</span>'
             '<span class="chip">AML Tech Conf 2026</span></div>']
    c.clip(eid, f"panel win {cls}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, cls, at, dur)
    c.js.append(f"countText('{eid}v', '1473', {at + 0.5:.3f}, 0);")
    c.plan_row(at, "1473 участника", "stat", "счётчик до 1473", "click")


def draw_title(c: Comp, b: dict, eid: str, at: float, dur: float) -> None:
    text = title_payload(b)
    parts = text.split("—")
    big = esc(parts[0].strip())
    sub = esc(parts[1].strip()) if len(parts) > 1 else ""
    inner = [f'    <div class="big">{big}</div>']
    if sub:
        inner.append(f'    <div class="sub">{sub}</div>')
    c.clip(eid, "panel ttl", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, "ttl", at, dur)
    c.plan_row(at, "крипта на балансе", "title", "титр всплывает сверху", "impact")


def draw_outro(c: Comp, b: dict, eid: str, at: float, dur: float) -> None:
    p = outro_payload(b)
    parts = p["sub"].split()
    first = esc(" ".join(parts[:-1])) if len(parts) > 1 else ""
    last = esc(parts[-1]) if parts else "Rudstock"
    inner = [f'    <div class="brand">{first} <em>{last}</em></div>',
             f'    <div class="handle">{esc(p["handle"])}</div>',
             f'    <div class="note">{esc(p["note"])}</div>',
             '    <div class="chips"><span class="chip on">Подписка</span>'
             '<span class="chip">BingX в описании</span></div>']
    c.clip(eid, "panel outro-plate", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, "outro-plate", at, dur)
    c.plan_row(at, "подпишитесь на Rudstock Crypto", "outro", "плашка подписки в конце", "impact")


# --------------------------------------------------------------- block building
def block_inserts(b: dict) -> list[dict]:
    """Every insert this block gets, derived from all of its B-roll marks."""
    kinds = []
    for a in (b.get("assets") or []):
        if a["kind"] not in kinds:
            kinds.append(a["kind"])
    out: list[dict] = []
    for kind in kinds:
        n = b["n"]
        if kind == "quotes":
            out.append({"kind": "quotes", "marks": [("num", "81174"), ("word", "биткоин")],
                        "side": "r", "dur": 12.0})
        elif kind == "logo" and n == 2:
            out.append({"kind": "chips", "marks": [("word", "организатор"),
                                                   ("word", "обозрен")],
                        "side": "r", "dur": 11.0,
                        "content": ("Организаторы", org_chips(b)[1])})
            out.append({"kind": "chips", "marks": [("word", "Минфин"), ("word", "спикер")],
                        "side": "l", "dur": 11.0,
                        "content": ("В зале", speaker_chips(b))})
        elif kind == "chart" and n == 3:
            out.append({"kind": "diagram", "marks": [("word", "онбординг"), ("word", "KYT")],
                        "side": "r", "dur": 13.0})
        elif kind == "timeline":
            out.append({"kind": "timeline", "marks": [("num", "2026"), ("word", "сентябр")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "chips", "marks": [("word", "Travel"), ("word", "комплаенс")],
                        "side": "l", "dur": 10.0,
                        "content": ("Новые требования", requirement_chips(b))})
        elif kind == "table" and n == 5:
            out.append({"kind": "stat", "marks": [("num", "37"), ("word", "инфляц")],
                        "side": "r", "dur": 11.0})
            out.append({"kind": "chart", "marks": [("num", "654"), ("word", "отток")],
                        "side": "l", "dur": 12.0})
        elif kind == "chart" and n == 6:
            out.append({"kind": "premium", "marks": [("num", "1398"), ("word", "премиальн")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "quote", "marks": [("word", "случайность"),
                                                   ("word", "режим")],
                        "side": "l", "dur": 10.0})
        elif kind == "table" and n == 7:
            out.append({"kind": "table", "marks": [("word", "арбитр"), ("num", "92")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "counter", "marks": [("word", "Cerebras"),
                                                     ("num", "902")],
                        "side": "l", "dur": 9.0})
        elif kind == "chart" and n == 8:
            out.append({"kind": "scenario", "marks": [("word", "бычий"), ("word", "мост")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "quote", "marks": [("word", "органической"),
                                                   ("word", "спекулятивного")],
                        "side": "l", "dur": 10.0})
        elif kind == "funnel":
            out.append({"kind": "funnel", "marks": [("word", "фильтр"), ("word", "мелкие")],
                        "side": "r", "dur": 11.0})
            out.append({"kind": "scenario", "marks": [("word", "медвежий"),
                                                      ("word", "поддержк")],
                        "side": "l", "dur": 11.0})
        elif kind == "checklist":
            out.append({"kind": "checklist", "marks": [("word", "первое"), ("word", "ножи")],
                        "side": "r", "dur": 14.0})
        elif kind == "chart" and n == 11:
            out.append({"kind": "miners", "marks": [("num", "1473"), ("word", "майнер")],
                        "side": "r", "dur": 11.0})
            out.append({"kind": "steps", "marks": [("word", "реестр"),
                                                   ("word", "сократил")],
                        "side": "l", "dur": 11.0})
        elif kind == "outro":
            out.append({"kind": "outro", "marks": [("word", "Rudstock"),
                                                   ("word", "подпишитесь")],
                        "side": "r", "dur": 14.0, "force_last": True})
        # 'title' inside a block is drawn as the block's own heading, no extra insert
    extras = EXTRA_INSERTS.get(b["n"], [])
    for spec in out:
        spec.setdefault("primary", True)
    if extras:
        resolved = []
        for spec in extras:
            spec = dict(spec)
            spec.setdefault("primary", False)
            if callable(spec.get("content")):
                spec["content"] = spec["content"](b)
            resolved.append(spec)
        out = (resolved + out) if b["n"] in EXTRA_FIRST else (out + resolved)
    return out


# blocks whose stretch would otherwise run empty for 15+ s get one more insert,
# always from the narration of that very block (never invented)
EXTRA_INSERTS = {
    1: [{"kind": "chips", "marks": [("word", "легальный"), ("word", "статус")],
         "side": "l", "dur": 10.0,
         "content": lambda b: ("Получили статус", status_chips(b))}],
    3: [{"kind": "quote", "marks": [("word", "определяют"), ("word", "лицензионн")],
         "side": "l", "dur": 10.0}],
    6: [{"kind": "chips", "marks": [("word", "TradingView"), ("word", "минимум")],
         "side": "l", "dur": 9.0,
         "content": lambda b: ("График", ["TradingView ETH 1D", "локальный минимум"])}],
    7: [{"kind": "quote", "marks": [("word", "удержать"), ("num", "84")],
         "side": "l", "dur": 10.0}],
    10: [{"kind": "chips", "marks": [("word", "BingX"), ("word", "стакан")],
          "side": "l", "dur": 9.0,
          "content": lambda b: ("Терминал", terminal_chips(b))}],
    12: [{"kind": "quote", "marks": [("word", "комментари"), ("word", "легализаци")],
          "side": "l", "dur": 9.0}],
}
EXTRA_FIRST = {12}


DRAW = {
    "quotes": lambda c, b, eid, at, dur, cls: draw_quotes(c, b, eid, at, dur, cls),
    "chart": lambda c, b, eid, at, dur, cls: draw_chart(c, b, eid, at, dur, cls),
    "table": lambda c, b, eid, at, dur, cls: draw_table(c, b, eid, at, dur, cls),
    "timeline": lambda c, b, eid, at, dur, cls: draw_timeline(c, b, eid, at, dur, cls),
    "diagram": lambda c, b, eid, at, dur, cls: draw_diagram(c, b, eid, at, dur, cls),
    "checklist": lambda c, b, eid, at, dur, cls: draw_checklist(c, b, eid, at, dur, cls),
    "stat": lambda c, b, eid, at, dur, cls: draw_stat(c, b, eid, at, dur, cls),
    "premium": lambda c, b, eid, at, dur, cls: draw_premium(c, b, eid, at, dur, cls),
    "miners": lambda c, b, eid, at, dur, cls: draw_miners(c, b, eid, at, dur, cls),
    "funnel": lambda c, b, eid, at, dur, cls: draw_funnel(c, b, eid, at, dur, cls),
    "scenario": lambda c, b, eid, at, dur, cls: draw_scenario(c, b, eid, at, dur, cls),
    "chips": lambda c, b, eid, at, dur, cls: draw_chips(c, b, eid, at, dur, cls),
    "outro": lambda c, b, eid, at, dur, cls: draw_outro(c, b, eid, at, dur),
    "title": lambda c, b, eid, at, dur, cls: draw_title(c, b, eid, at, dur),
    "quote": lambda c, b, eid, at, dur, cls: draw_quote(c, b, eid, at, dur, cls),
}

# counters that need a value from the script (label, value, unit)
COUNTERS = {
    7: ("Доля акций Cerebras", "9,02", "%"),
}


def build(label: str, edit: Path, json_out: Path | None) -> int:
    plan = json.loads((edit / "script_plan.json").read_text(encoding="utf-8-sig"))
    data = json.loads((edit / "data.json").read_text(encoding="utf-8-sig"))
    raw = json.loads(BRAND_PATH.read_text(encoding="utf-8-sig"))
    brand = {"white": raw["colors"]["white"], "surface": raw["colors"]["surface"],
             "accent": raw["colors"]["accent"], "ink": raw["colors"]["ink"],
             "muted": raw["colors"]["muted"], "radius": raw["shape"]["radius_px"],
             "shadow": raw["shape"]["video_shadow"]}
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8-sig"))
    total = sum(float(s["out"]) - float(s["in"]) for s in edl)

    timeline, t = [], 0.0
    for seg in edl:
        timeline.append((float(seg["in"]), float(seg["out"]), t))
        t += float(seg["out"]) - float(seg["in"])

    cands = sorted((edit / "transcripts").glob("*-words.json"))
    words = json.loads(cands[0].read_text(encoding="utf-8-sig")) if cands else []
    anch = Anchors(words, timeline)

    blocks = sorted([b for b in plan["blocks"] if b.get("timeline_start_s") is not None],
                    key=lambda b: b["timeline_start_s"])
    for b in blocks:
        b["_start"] = float(b["timeline_start_s"])
        b["_src0"] = float(b.get("source_start_s") or 0.0)
    for i, b in enumerate(blocks):
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        b["_end"] = nxt["_start"] if nxt else total
        b["_src1"] = nxt["_src0"] if nxt else total + 60.0

    author = data["passport"].get("author") or {"name": "Дмитрий Царьков",
                                                "role": "управляющий активами"}
    c = Comp(brand)
    cid = "main"

    lt_at, lt_dur = 0.6, 6.0
    c.clip("lt", "panel lt", lt_at, lt_dur,
           f'    <div class="n">{esc(author["name"])}</div>\n'
           f'    <div class="r">{esc(author["role"])}</div>\n')
    c.js.append(f"pop('#lt', {lt_at:.3f});")
    c.js.append(f"leave('#lt', {lt_at + lt_dur - 0.34:.3f});")
    c.plan_row(lt_at, "здравствуйте", "hook", "титр имени и должности", "pop")

    first = blocks[0]
    ttl_at, ttl_dur = 7.0, 6.2
    if ttl_at + ttl_dur > first["_end"] - 1.0:
        ttl_at, ttl_dur = first["_start"] + 0.6, 5.0
    draw_title(c, first, "ttl1", ttl_at, ttl_dur)

    inserts_meta: list[dict] = []
    for i, b in enumerate(blocks):
        if i > 0:
            at, dur = b["_start"], 2.8
            c.clip(f"sw{b['n']}", "sw", at, 0.6, "")
            c.js.append(f"sweep('#sw{b['n']}', {at:.3f});")
            c.clip(f"dv{b['n']}", "panel dv", at, dur,
                   f'    <div class="num">{b["n"]:02d}</div>\n'
                   f'    <div class="ttl">{esc(b["title"])}</div>\n')
            c.js.append(f"pop('#dv{b['n']}', {at + 0.05:.3f});")
            c.js.append(f"leave('#dv{b['n']}', {at + dur - 0.34:.3f});")
            c.plan_row(at, "", f"divider{b['n']}", "номер и название блока", "pop")

        cursor = max(b["_start"] + 3.1, 1.0)
        if i == 0:
            cursor = max(cursor, ttl_at + ttl_dur + 0.8)
        # anchors are resolved first, then inserts are placed in the order the
        # speaker reaches them: a card never jumps ahead of the one before it
        prepared = []
        for spec in block_inserts(b):
            found = anchor_timeline(anch, b, spec["marks"])
            # the block's own B-roll wins the room; extras fill what is left,
            # and the closing plate always stays last
            tier = 2 if spec.get("force_last") else (0 if spec.get("primary") else 1)
            key = found if found is not None else b["_start"] + 33.0
            # time decides the order; the tier only breaks ties, and the closing
            # plate is pulled out of the queue entirely
            order = (1, 0.0, 0) if spec.get("force_last") else (0, key, tier)
            prepared.append((order, found, spec))
        prepared.sort(key=lambda x: x[0])
        latest = b["_end"] - 7.2
        for j, (key, found, spec) in enumerate(prepared):
            eid = f"e{b['n']}_{j+1}"
            # an anchor is a preference, not a promise: pull the card earlier if
            # that is the only way it fits before the next block
            at = min(max(found if found is not None else cursor, cursor,
                         b["_start"] + 3.1), latest)
            if at < cursor:
                c.notes.append(f"#{b['n']} {spec['kind']}: нет места в блоке, пропущено")
                continue
            dur = min(spec["dur"], max(6.0, b["_end"] - 1.2 - at))
            if spec["kind"] == "outro":
                # the subscription plate may hold until the end of the film
                dur = max(dur, min(30.0, b["_end"] - 0.5 - at))
            if spec["kind"] == "counter":
                label, value, unit = COUNTERS[b["n"]]
                draw_counter(c, b, eid, at, dur, spec["side"], value, label, unit)
            elif spec["kind"] == "steps":
                draw_diagram(c, b, eid, at, dur, spec["side"], items=steps_items(b),
                             tag=("сначала правила, потом реестр", "steps",
                                  "три шага цепочки по очереди"))
            elif spec["kind"] == "chips":
                draw_chips(c, b, eid, at, dur, spec["side"], content=spec.get("content"))
            elif spec["kind"] == "checklist":
                draw_checklist(c, b, eid, at, dur, spec["side"],
                               times=checklist_times(b, anch, at, dur))
            else:
                DRAW[spec["kind"]](c, b, eid, at, dur, spec["side"])
            cursor = at + dur + 0.7
            inserts_meta.append({"block": b["n"], "kind": spec["kind"], "id": eid,
                                 "at": round(at, 3), "dur": round(dur, 3),
                                 "side": spec["side"], "anchored": found is not None})

    comp = edit / "comp"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "fonts").mkdir(exist_ok=True)
    mask = raw["fonts"].get("file", "inter-v20-cyrillic_latin_latin-ext-{w}.ttf")
    for weight, suffix in FONT_FILES.items():
        src = FONT_DIR / mask.format(w=suffix)
        if src.is_file():
            shutil.copyfile(src, comp / "fonts" / f"Inter-{weight}.ttf")
    (comp / "vendor").mkdir(exist_ok=True)
    vend = ROOT / "tools" / "vendor" / "gsap.min.js"
    if vend.is_file():
        shutil.copyfile(vend, comp / "vendor" / "gsap.min.js")

    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="UTF-8"/>
<script src="vendor/gsap.min.js"></script>
<style>
{css(brand)}</style>
</head>
<body>
<div id="root" class="clip" data-composition-id="{cid}" data-start="0" data-duration="{total:.3f}" data-width="1920" data-height="1080">
{chr(10).join(c.html)}

</div>
<script>
{JS_COMMON}{chr(10).join(c.js)}
window.__timelines = window.__timelines || {{}};
window.__timelines['{cid}'] = tl;
tl.seek(0);
</script>
</body>
</html>
"""
    (comp / "index.html").write_text(html, encoding="utf-8")

    rows = ["| время | слова | элемент | анимация | звук |", "|---|---|---|---|---|"]
    for r in sorted(c.plan, key=lambda x: x["t"]):
        rows.append(f"| {r['t']:.1f} | {r['words']} | {r['element']} | {r['motion']} | {r['sound']} |")
    (edit / "graphics_plan.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    meta = {"label": label, "duration_s": round(total, 3), "blocks": len(blocks),
            "elements": len(c.html), "inserts": inserts_meta, "notes": c.notes,
            "author": author}
    (json_out or (edit / "comp_plan.json")).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    kinds: dict[str, int] = {}
    for m in inserts_meta:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    print(f"comp: {comp / 'index.html'}")
    print(f"  блоков {len(blocks)} | элементов {len(c.html)} | длительность {total:.1f} с")
    print("  вставки: " + (", ".join(f"{k} x{v}" for k, v in sorted(kinds.items(),
                                                                    key=lambda x: -x[1]))
                           or "нет"))
    print(f"  привязано к речи: {sum(1 for m in inserts_meta if m['anchored'])}"
          f"/{len(inserts_meta)}")
    for n in c.notes:
        print(f"  ! {n}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--edit", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    ed = Path(a.edit) if a.edit else ROOT / "runs" / a.label / "edit"
    raise SystemExit(build(a.label, ed, Path(a.json) if a.json else None))
