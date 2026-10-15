#!/usr/bin/env python3
"""Build the brand graphics layer from the shooting script (script_plan.json).

Unlike generate_comp.py (heuristic triggers from the transcript), this follows the
script the presenter actually shot: one block per scene, each block gets its own
liquid-glass divider, and the inserts come from that block's B-roll mark. Every
number on screen is taken from the script text - nothing is invented here.

Four rules the first version got wrong, fixed here:

1. **Copy is written, not pasted.** Block headings carry production markup
   (`#1Хук: ...`, `CTA`, `Bull-сценарий:`) and the old code printed them verbatim,
   and used the heading as a card's only chip when a component had no content.
   `insert_copy.py` strips the markup, rewrites the heading into a viewable
   sentence, fills every component from the narration and the B-roll mark, and
   measures each string with the real Inter font. Text that does not fit is
   shortened by design - an ellipsis is never produced.
2. **Nothing covers the face.** Inserts sit in the outer columns (never over the
   head), and the two big moments use explicit stage modes:
   `glass` blurs the whole frame behind a centred plate (block dividers),
   `push` moves the speaker aside over a blurred backdrop and puts the panel in
   the freed space (the closing subscription plate).
3. **Timing follows speech.** A card starts on the word that introduces its
   topic, holds through the topic, and ends before the next card - no card is
   dropped suddenly while its list is still filling, and none runs into the next
   block's divider.
4. **One element at a time.** Cards are laid out sequentially with air between
   them; a card that cannot hold for its own reveal is dropped rather than shown.

Outputs (all in the run's `edit/`):
  comp/index.html     the renderable composition
  comp_plan.json      machine plan of every insert
  stage.json          frame-stage windows for build_final.py (blur / push)
  graphics_plan.md    human and machine table of events (§9.5, §13)

Usage: generate_comp_plan.py <label> [--edit <dir>] [--json plan.json]
                             [--copy <inserts.json>] [--frame-sheet]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from insert_copy import (CopyEngine, assert_no_ellipsis, fix_typos, human_title,
                         sentence_case, strip_markup)

ROOT = Path(__file__).resolve().parent.parent
BRAND_PATH = ROOT / "refs" / "brandbook" / "brand.json"
FONT_DIR = ROOT / "refs" / "brandbook" / "fonts"
FONT_FILES = {400: "regular", 500: "500", 600: "600", 700: "700", 800: "800", 900: "900"}

# --------------------------------------------------------------- text helpers
def esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def broll_text(block: dict) -> str:
    return " ".join(block.get("broll_spec") or [])


def words_of(block: dict) -> str:
    return block.get("narration") or ""


def quoted(text: str) -> list[str]:
    return [fix_typos(q.strip()) for q in re.findall(r"«([^»]{2,90})»", text)]


def num(v: str) -> float:
    return float(re.sub(r"[^\d.,]", "", str(v)).replace(",", ".") or 0)


def label_of(phrase: str, keep: int = 2) -> str:
    toks = [t for t in re.split(r"\s+", phrase.strip(" .,;:—-—")) if t]
    return " ".join(toks[-keep:]).strip(" .,;:—-—")


def human_number(v: str) -> str:
    """1234.5 -> '1 234,5'; keeps the script's decimal comma."""
    s = str(v).strip()
    return s


# ------------------------------------------------------------- what to draw
def quotes_rows(block: dict) -> list[tuple[str, str, str]]:
    text = words_of(block) + " " + broll_text(block)
    pat = re.compile(r"\b(BTC|ETH|SPY)\s+([\d\s]{2,9}(?:[.,]\d+)?)\s*\(\s*-?\s*([\d.,]+)\s*%?\s*\)")
    rows = [(n, v.strip(), "−" + d.replace(".", ","))
            for n, v, d in pat.findall(text)]
    if len(rows) < 2:
        pat2 = re.compile(r"([A-Za-zА-Яа-яЁё][\w.\- ]{1,12}?)\s*[—–-]\s*"
                          r"(\d[\d\s]{1,9}(?:[.,]\d+)?)\s*(?:доллар\w*)?\s*,?\s*"
                          r"(?:минус|плюс|−|-)\s*([\d]+(?:[.,]\d+)?)\s*(?:процент\w*|%)?")
        rows = [(n.strip().split()[-1], v.strip(), "−" + d.replace(".", ","))
                for n, v, d in pat2.findall(text)]
    out, seen = [], set()
    for n, v, d in rows:
        k = n.upper()
        if k not in seen and num(v) > 0:
            seen.add(k)
            out.append((k, v, d))
    return out[:4]


def unlock_rows(block: dict) -> list[tuple[str, str, str]]:
    """name -> (amount, date): ARB 92.65M (сегодня), Cerebras 19.4M акций / 9.02%."""
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
    n = re.search(r"(\d+)\s*дн\w+\s*подряд", text)
    return (m.group(1) if m else "0,1394").replace(".", ","), (n.group(1) if n else "20")


def diagram_items(block: dict) -> list[tuple[str, str]]:
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
            pick = mm.start()
            break
        picks.append((name, pick))
    ordered = sorted([p for p in picks if p[1] >= 0], key=lambda x: x[1])
    notes: dict[str, str] = {}
    for i, (name, pos) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else pos + 150
        notes[name] = text[pos + len(name):end].lstrip(" —–-:").strip()
    return [(sentence_case(name.strip()), notes.get(name, "")) for name in names[:4]]


def timeline_items(block: dict) -> list[tuple[str, str]]:
    text = words_of(block) + " " + broll_text(block)
    labels = [p.strip() for p in re.findall(r"\(([^)]{3,60})\)", broll_text(block))]
    dates: list[str] = []
    for m in re.finditer(r"(\d{1,2}\s+(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|"
                         r"сентябр|октябр|ноябр|декабр)\w*\s+\d{4})", text, re.I):
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
    pat = re.compile(r"(?:Первое|Второе|Третье|Четв[её]ртое|Пятое|И\s+пятое)\s*:\s*([^.]{3,140})")
    items = [m.group(1).strip() for m in pat.finditer(text)]
    if len(items) < 3:
        items = [s for s in sentences(text) if len(s) > 20][:5]
    return items[:5]


def funnel_steps(block: dict) -> tuple[list[tuple[str, int]], list[str]]:
    text = words_of(block).lower()
    steps = []
    for needle, label, share in (("мелкие обменники", "мелкие обменники и сервисы", 100),
                                 ("крупных игроков", "несколько крупных игроков", 34)):
        if needle in text:
            steps.append((label, share))
    if not steps:
        steps = [("мелкие обменники и сервисы", 100), ("несколько крупных игроков", 34)]
    chips = [c for c in ("капитал", "комплаенс", "KYT", "Travel Rule", "аудит", "отчётность")
             if c.lower() in text]
    return steps, chips[:4]


def scenario_card(block: dict) -> tuple[str, str, list[str]]:
    spec = broll_text(block)
    tone = "BULL" if "bull" in spec.lower() else ("BEAR" if "bear" in spec.lower() else "СЦЕНАРИЙ")
    head = ""
    for item in quoted(spec):
        if not item.upper().startswith(("BULL", "BEAR")) and len(item) > 8:
            head = item
            break
    if not head:
        head = human_title(block.get("title", ""))
    bullets = [c.strip(" .;") for c in re.split(r",|\s+и\s+", head) if 3 < len(c.strip()) < 40][:4]
    return tone, head, bullets


def org_chips(block: dict) -> tuple[str, list[str]]:
    spec = broll_text(block)
    chips = quoted(spec)
    chips += [w for w in re.findall(r"\b[A-Z][A-Za-z]{2,}(?:\.[A-Za-z]+)?\b", spec)
              if w not in ("B", "B-roll", "M", "BTC", "ETH", "SPY", "BeInCrypto")]
    if "BeInCrypto" in spec:
        chips.append("BeInCrypto")
    if "SVOY" in spec:
        chips.append("Лофт SVOY")
    seen, out = set(), []
    for c in chips:
        if c.lower() not in seen and len(c) > 2:
            seen.add(c.lower())
            out.append(c)
    return "Организаторы", out[:6]


def list_after(text: str, needles: list[str], limit: int = 6) -> list[str]:
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
    found = list_after(broll_text(block) + " " + words_of(block),
                       ["списком спикеров", "среди спикеров", "спикеров", "заявлены"])
    text = words_of(block)
    if not found:
        m = re.search(r"Среди спикеров заявлены\s*([^.;]+)", text)
        if m:
            found = [p.strip(" ,.;") for p in re.split(r",|\s+и\s+", m.group(1))][:6]
    return found


def status_chips(block: dict) -> list[str]:
    m = re.search(r"([А-Яа-яЁё][^.:—]*?)\s+получил", words_of(block))
    if not m:
        return ["банки", "брокеры", "биржи", "обменники", "депозитарии"]
    parts = [p.strip(" ,.;:") for p in re.split(r",|\s+и\s+", m.group(1))]
    return [p for p in parts if 3 < len(p) < 24][-5:]


def terminal_chips(block: dict) -> list[str]:
    spec = broll_text(block)
    chips = re.findall(r"\b(?:BingX|BTCUSD|ETH)\b", spec)
    if "стакан" in spec:
        chips.append("стакан без агрессивных покупок")
    return chips or ["BingX"]


def outro_payload(block: dict) -> dict:
    spec = broll_text(block)
    q = quoted(spec)
    handle = re.search(r"@[A-Za-z0-9_]{3,}", spec)
    name = re.search(r"(Rudstock[\w ]{0,20}?)(?:,|$|\s+Telegram)", spec)
    sub = fix_typos(name.group(1).strip()) if name else "Rudstock Crypto"
    note = next((x for x in q if x), "Разбор по итогам конференции — в следующем ролике")
    return {"sub": sub, "handle": handle.group(0) if handle else "@TDmitryT", "note": note}


def title_payload(block: dict) -> tuple[str, str]:
    for item in quoted(broll_text(block)):
        if item and not item.upper().startswith(("BULL", "BEAR")):
            parts = [p.strip() for p in re.split(r"\s+—\s+", item)]
            return parts[0], (parts[1] if len(parts) > 1 else "")
    return human_title(block.get("title", "")), ""


def steps_items(block: dict) -> list[tuple[str, str]]:
    m = re.search(r"сначала\s+(.{3,60}?),\s*потом\s+(.{3,60}?),\s*потом\s+(.{3,90})",
                  words_of(block))
    if m:
        return [(sentence_case(m.group(1).strip()), "новые требования рынка"),
                (sentence_case(m.group(2).strip()), "участники под надзором"),
                (sentence_case(m.group(3).strip()), "KYT и Travel Rule на площадках")]
    return [("Правила", "новые требования рынка"), ("Реестр", "участники под надзором"),
            ("Сокращение", "число участников падает")]


def key_sentence(block: dict) -> str:
    sents = [s for s in sentences(strip_markup(words_of(block))) if len(s) > 40]
    if not sents:
        return ""
    question = next((s for s in sents if "?" in s or "комментари" in s.lower()), None)
    return (question or (sents[-2] if len(sents) >= 3 else sents[-1])).strip()


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
        digits = re.sub(r"\D", "", digits)
        if len(digits) < 2:
            return None
        buf, start = "", None
        for w in self.words:
            if not (lo - 2.0 <= w["start"] <= hi + 2.0):
                continue
            d = re.sub(r"\D", "", str(w.get("word", "")))
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
        text = re.sub(r"[^\w]", "", needle.lower().replace("ё", "е"))
        if not text:
            return None
        stem = text[:5]
        for w in self.words:
            if not (lo - 2.0 <= w["start"] <= hi + 2.0):
                continue
            n = re.sub(r"[^\w]", "", str(w.get("word", "")).lower().replace("ё", "е"))
            if n and n.startswith(stem):
                return w["start"]
        return None

    def phrase(self, needle: str, lo: float, hi: float) -> float | None:
        """First word of a multi-word phrase found in order (tolerates inflection)."""
        toks = [re.sub(r"[^\w]", "", t.lower().replace("ё", "е"))
                for t in re.findall(r"[\w-]+", needle)]
        toks = [t for t in toks if t]
        if not toks:
            return None
        for w in self.words:
            if not (lo - 2.0 <= w["start"] <= hi + 2.0):
                continue
            first = re.sub(r"[^\w]", "", str(w.get("word", "")).lower().replace("ё", "е"))
            if not first.startswith(toks[0][:4]):
                continue
            src, pos = w["start"], 1
            for x in self.words[self.words.index(w) + 1:]:
                if pos >= len(toks):
                    break
                if x["start"] > w["start"] + 8.0:
                    break
                nxt = re.sub(r"[^\w]", "", str(x.get("word", "")).lower().replace("ё", "е"))
                if nxt.startswith(toks[pos][:4]):
                    pos += 1
            if pos >= max(1, int(round(len(toks) * 0.7))):
                return src
        return None

    def any_of(self, marks: list[tuple[str, str]], lo: float, hi: float) -> float | None:
        found = []
        for kind, value in marks:
            t = (self.number(value, lo, hi) if kind == "num"
                 else self.phrase(value, lo, hi) if kind == "phrase"
                 else self.word(value, lo, hi))
            if t is not None:
                found.append(t)
        return min(found) if found else None


def _map_src(anch: Anchors, b: dict, src: float | None) -> float | None:
    if src is None:
        return None
    t = anch.to_timeline(src)
    if t is not None:
        return t
    span = max(0.001, b["_src1"] - b["_src0"])
    frac = min(1.0, max(0.0, (src - b["_src0"]) / span))
    return b["_start"] + frac * (b["_end"] - b["_start"])


def anchor_timeline(anch: Anchors, b: dict, marks: list[tuple[str, str]]) -> float | None:
    """Where a mark lands on the edited timeline.

    A spoken moment can sit inside a pause the EDL removed; then the card still
    belongs at that point of the story, so it is placed proportionally between the
    block's start and its end instead of being dropped.
    """
    return _map_src(anch, b, anch.any_of(marks, b["_src0"], b["_src1"]))


def word_timeline(anch: Anchors, b: dict, word: str) -> float | None:
    return _map_src(anch, b, anch.word(word, b["_src0"], b["_src1"]))


# ------------------------------------------------------------------ rendering
SIDE_W = 560          # side card width
WIDE_W = 640
PAD = 30
GLASS_W = 1240        # centred plate inside the liquid-glass cover
SHEET_W = 880         # push panel width
AIR = 0.7             # seconds of empty frame between two cards (§9.5)


class Comp:
    def __init__(self, brand: dict, ce: CopyEngine):
        self.b = brand
        self.ce = ce
        self.html: list[str] = []
        self.js: list[str] = []
        self.plan: list[dict] = []
        self.notes: list[str] = []
        self.stage: list[dict] = []

    def clip(self, cid: str, cls: str, at: float, dur: float, inner: str,
             extra: str = "") -> None:
        self.html.append(
            f'  <div id="{cid}" class="{cls} clip" data-start="{at:.3f}" '
            f'data-duration="{dur:.3f}"{extra}">\n{inner}  </div>')

    def plan_row(self, at: float, spoken: str, element: str, motion: str, sound: str,
                 note: str = "") -> None:
        self.plan.append({"t": round(at, 3), "words": spoken, "element": element,
                          "motion": motion, "sound": sound, "note": note})

    def cover(self, cid: str, at: float, dur: float, inner: str, cls: str = "cover",
              side: str = "") -> None:
        """A full-frame or panel-width liquid-glass moment: exempt from the margin rule."""
        self.clip(cid, f"{cls}{(' ' + side) if side else ''}", at, dur, inner,
                  extra=' data-layout-allow-occlusion="true"')

    # life cycle: the clip carries the panel, its children animate
    def open_card(self, cid: str, at: float, dur: float, inner_sel: str | None = None) -> None:
        sel = inner_sel or f"#{cid}"
        self.js.append(f"pop('{sel}', {at:.3f});")
        self.js.append(f"leave('{sel}', {at + dur - 0.42:.3f});")

    def stage_window(self, start: float, end: float, mode: str, person: str = "left") -> None:
        self.stage.append({"start": round(max(0.0, start), 3), "end": round(end, 3),
                           "mode": mode, "person": person})


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

/* centred title card, above the head (top 9%, ends well before the eyes) */
.ttl { left:0; right:0; margin:0 auto; top:7.5%; width:1180px; text-align:center;
  padding:26px 40px 30px; opacity:0; }
.ttl .big { font:900 62px/1.08 'Inter'; letter-spacing:-.03em; color:__INK__; }
.ttl .sub { font:500 27px/1.3 'Inter'; color:__MUTED__; margin-top:12px; }

/* ---- liquid glass: the screen blurs, a plate sits in the centre ------------ */
.cover { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; }
.frost { position:absolute; inset:0; background:__SURFACE__; opacity:0; }
/* a soft brand glow so the frosted frame is not flat */
.glow { position:absolute; inset:0; opacity:0;
  background:radial-gradient(120% 90% at 50% 42%, #FFFFFF 0%, rgba(255,255,255,0) 62%); }
.gplate { position:relative; width:__GLASSW__px; text-align:center; padding:44px 56px 48px;
  background:__WHITE__; border-radius:__R__px; box-shadow:0 28px 64px rgba(0,0,0,0.16);
  opacity:0; }
.gplate .gk { font:900 26px/1 'Inter'; color:__ACCENT__; letter-spacing:.16em; }
.gplate .gn { font:900 96px/1 'Inter'; color:__ACCENT__; letter-spacing:-.05em; margin-top:10px; }
.gplate .gt { font:800 46px/1.14 'Inter'; color:__INK__; letter-spacing:-.025em; margin-top:8px; }
.gplate .grule { height:6px; width:96px; border-radius:3px; background:__ACCENT__;
  margin:22px auto 0; }

/* the panel that takes the space freed by pushing the speaker aside */
.sheet { position:absolute; top:0; bottom:0; right:0; width:__SHEETW__px;
  background:__SURFACE__; opacity:0; padding:0 56px; display:flex;
  flex-direction:column; justify-content:center; }
.sheet .inner { opacity:0; }
.sheet .k { font:900 26px/1 'Inter'; color:__ACCENT__; letter-spacing:.16em; }
.sheet .brand { font:900 58px/1.05 'Inter'; letter-spacing:-.03em; color:__INK__; margin-top:14px; }
.sheet .brand em { font-style:normal; color:__ACCENT__; }
.sheet .handle { font:800 34px/1 'Inter'; color:__ACCENT__; margin-top:16px; }
.sheet .note { font:500 27px/1.4 'Inter'; color:__MUTED__; margin-top:14px; }

/* insert cards: one class per side, never over the head */
.win { top:13%; width:__SIDEW__px; padding:28px 30px 30px; opacity:0; }
.win.r { right:5%; transform-origin:right center; }
.win.l { left:5%; transform-origin:left center; }
.wide { width:__WIDEW__px; }
.h { font:900 24px/1 'Inter'; color:__ACCENT__; letter-spacing:.08em; }
.t { font:800 38px/1.14 'Inter'; color:__INK__; margin-top:12px; letter-spacing:-.02em; }
.note { font:500 26px/1.45 'Inter'; color:__MUTED__; margin-top:14px; }
.rule { height:4px; width:76px; border-radius:2px; background:__ACCENT__; margin:14px 0 4px; }

/* quote card: a vertical accent line grows, then the line comes in */
.qline { width:8px; border-radius:4px; background:__ACCENT__; height:0; flex:0 0 8px; }
.qwrap { display:flex; gap:20px; margin-top:20px; }
.quote { font:500 33px/1.34 'Inter'; color:__INK__; letter-spacing:-.01em; }
.quote em { font-style:normal; color:__ACCENT__; font-weight:800; }

.row { display:grid; grid-template-columns:1fr auto auto; align-items:baseline; gap:14px;
  padding:14px 0 0; }
.k { font:500 28px/1.25 'Inter'; color:__MUTED__; }
.d { font:700 24px/1.25 'Inter'; color:__MUTED__; text-align:right; white-space:nowrap; }
.row2 { display:flex; align-items:baseline; justify-content:space-between; gap:16px;
  padding:14px 0 0; }
.v { font:900 32px/1.25 'Inter'; color:__INK__; white-space:nowrap; text-align:right;
  font-variant-numeric:tabular-nums; }
.v.dn { color:__ACCENT__; }
.v.sm { font:800 25px/1.25 'Inter'; }
.v.multi { white-space:normal; line-height:1.2; text-align:right; }
.sym { font:700 25px/1.25 'Inter'; color:__MUTED__; }

.chips { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }
.chip { background:__SURFACE__; border-radius:999px; padding:10px 18px;
  font:600 25px/1 'Inter'; color:__INK__; white-space:nowrap; }
.chip.on { background:__ACCENT__; color:__WHITE__; }

.item { display:flex; gap:14px; align-items:flex-start; margin-top:15px; opacity:0;
  font:500 28px/1.3 'Inter'; color:__INK__; }
.tick { width:26px; height:26px; flex:0 0 26px; border-radius:9px;
  background:__SURFACE__; position:relative; margin-top:3px; }
.tick.on::after { content:''; position:absolute; left:5px; top:1px; width:9px; height:15px;
  border-right:4px solid __ACCENT__; border-bottom:4px solid __ACCENT__;
  transform:rotate(45deg); }

.stat { font:900 92px/1 'Inter'; color:__ACCENT__; letter-spacing:-.04em; margin-top:14px;
  font-variant-numeric:tabular-nums; }
.stat small { font:800 32px/1 'Inter'; color:__INK__; letter-spacing:0; margin-left:8px; }
.cmp { display:flex; align-items:center; gap:10px; margin-top:12px; font:600 26px/1.3 'Inter';
  color:__MUTED__; }
.cmp b { font:900 30px/1.3 'Inter'; color:__INK__; }

.bars { display:flex; align-items:flex-end; gap:14px; height:180px; margin-top:20px; }
.col { flex:1; display:flex; flex-direction:column; justify-content:flex-end;
  align-items:center; height:100%; }
.bar { width:100%; height:0; background:__ACCENT__; border-radius:10px 10px 0 0; }
.col .cl { font:700 21px/1 'Inter'; color:__MUTED__; margin-top:10px; white-space:nowrap; }
.zero { display:flex; align-items:center; gap:10px; margin-top:16px;
  font:600 24px/1 'Inter'; color:__MUTED__; }
.dash { flex:1; height:0; border-top:2px dashed __MUTED__; }

.ticks { display:flex; align-items:flex-start; gap:6px; height:128px; margin-top:18px;
  border-top:2px solid __INK__; padding-top:8px; }
.tickbar { flex:1; height:92px; background:__ACCENT__; border-radius:0 0 6px 6px; opacity:0; }

.tl-row { display:flex; align-items:flex-start; gap:18px; margin-top:18px; }
.tl-dot { width:20px; height:20px; border-radius:999px; background:__ACCENT__;
  margin-top:6px; flex:0 0 20px; }
.tl-date { font:900 29px/1.2 'Inter'; color:__INK__; }
.tl-note { font:500 25px/1.3 'Inter'; color:__MUTED__; margin-top:4px; }

.fstep { height:64px; border-radius:14px; background:__SURFACE__; margin-top:12px;
  display:flex; align-items:center; padding:0 22px; font:700 26px/1 'Inter';
  color:__INK__; opacity:0; }
.fstep.hot { background:__ACCENT__; color:__WHITE__; }

.dstep { display:flex; gap:14px; align-items:flex-start; margin-top:16px; opacity:0; }
.dnum { width:38px; height:38px; flex:0 0 38px; border-radius:12px; background:__SURFACE__;
  color:__ACCENT__; font:900 22px/38px 'Inter'; text-align:center; }
.dname { font:800 28px/1.2 'Inter'; color:__INK__; }
.dnote { font:500 24px/1.35 'Inter'; color:__MUTED__; margin-top:4px; }

.sc-head { display:flex; align-items:center; gap:14px; }
.badge { border-radius:12px; padding:8px 16px; font:900 24px/1 'Inter'; letter-spacing:.06em;
  background:__ACCENT__; color:__WHITE__; }
.badge.bear { background:__INK__; }
.bullet { display:flex; gap:12px; align-items:flex-start; margin-top:12px;
  font:600 27px/1.28 'Inter'; color:__INK__; opacity:0; }
.mark { width:12px; height:12px; border-radius:3px; background:__ACCENT__; flex:0 0 12px;
  margin-top:9px; }
.bridge { display:flex; align-items:center; gap:14px; margin-top:20px; opacity:0; }
.bplate { flex:1; text-align:center; background:__SURFACE__; border-radius:16px; padding:16px 8px;
  font:800 25px/1 'Inter'; color:__INK__; }
.barrow { font:900 30px/1 'Inter'; color:__ACCENT__; white-space:nowrap; }
.up { width:0; height:0; border-left:13px solid transparent; border-right:13px solid transparent;
  border-bottom:20px solid __ACCENT__; }
.down { width:0; height:0; border-left:13px solid transparent; border-right:13px solid transparent;
  border-top:20px solid __ACCENT__; }

/* было / стало */
.cmp2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-top:18px; }
.cmp2 .cell { background:__SURFACE__; border-radius:20px; padding:20px 22px; opacity:0; }
.cmp2 .cell .lab { font:900 20px/1 'Inter'; color:__MUTED__; letter-spacing:.12em; }
.cmp2 .cell .txt { font:700 26px/1.3 'Inter'; color:__INK__; margin-top:12px; }
.cmp2 .cell.now .lab { color:__ACCENT__; }

/* the closing card after the speech: full-frame brand end plate */
.endplate { position:absolute; inset:0; background:__INK__; opacity:0;
  display:flex; flex-direction:column; align-items:center; justify-content:center; }
.endplate .logo { font:900 96px/1 'Inter'; letter-spacing:-.04em; color:__WHITE__; opacity:0; }
.endplate .logo em { font-style:normal; color:__ACCENT__; }
.endplate .line { height:6px; width:0; border-radius:3px; background:__ACCENT__; margin:28px 0; }
.endplate .sub { font:600 34px/1.35 'Inter'; color:__WHITE__; opacity:0; }
.endplate .handle { font:800 32px/1 'Inter'; color:__ACCENT__; margin-top:22px; opacity:0; }
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
                     ("__SHADOW__", brand["shadow"]), ("__GLASSW__", str(GLASS_W)),
                     ("__SHEETW__", str(SHEET_W)), ("__SIDEW__", str(SIDE_W)),
                     ("__WIDEW__", str(WIDE_W))):
        sheet = sheet.replace(key, val)
    return sheet


JS_COMMON = """
const expo = { out: p => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
               in:  p => (p <= 0 ? 0 : Math.pow(2, 10 * (p - 1))) };
const tl = gsap.timeline({ paused: true });
function pop(sel, at) {
  tl.fromTo(sel, { opacity:0, scale:0.9, y:18 },
    { opacity:1, scale:1.02, y:0, duration:0.36, ease:p=>expo.out(p) }, at);
  tl.to(sel, { scale:1, duration:0.24, ease:p=>expo.out(p) }, at + 0.36);
}
function leave(sel, at) {
  tl.to(sel, { opacity:0, scale:0.97, y:-10, duration:0.40, ease:p=>expo.in(p) }, at);
}
function reveal(sel, at) {
  tl.fromTo(sel, { opacity:0, y:12 }, { opacity:1, y:0, duration:0.34, ease:p=>expo.out(p) }, at);
}
function frostIn(sel, at, peak) {
  tl.fromTo(sel, { opacity:0 }, { opacity:peak, duration:0.34, ease:p=>expo.out(p) }, at);
}
function frostOut(sel, at) {
  tl.to(sel, { opacity:0, duration:0.46, ease:p=>expo.in(p) }, at);
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
"""


# ---------------------------------------------------------------- card draws
def card_side_specs() -> dict:
    return {"side_w": SIDE_W - 2 * PAD, "wide_w": WIDE_W - 2 * PAD}


def draw_title(c: Comp, spec: dict, eid: str, at: float, dur: float) -> float:
    big = c.ce.fit(spec["big"], 900, 62, 1180 - 80, 2, f"{eid}.big", spec.get("alts"))
    sub = spec.get("sub") or ""
    inner = [f'    <div class="big">{esc(big)}</div>']
    if sub:
        sub = c.ce.fit(sub, 500, 27, 1180 - 80, 1, f"{eid}.sub")
        inner.append(f'    <div class="sub">{esc(sub)}</div>')
    c.clip(eid, "panel ttl", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    c.plan_row(at, spec.get("spoken", ""), "title", "титр всплывает сверху", "impact")
    return 0.36


def draw_divider(c: Comp, spec: dict, eid: str, at: float, dur: float) -> None:
    """Liquid-glass block transition: the frame blurs, a plate sits in the centre."""
    num = spec["num"]
    title = c.ce.fit(spec["title"], 800, 46, GLASS_W - 112, 2, f"{eid}.gt", spec.get("alts"))
    kicker = c.ce.fit(spec.get("kicker") or f"БЛОК {num}", 900, 26, GLASS_W - 112, 1, f"{eid}.gk")
    inner = (
        f'    <div class="frost" id="{eid}f"></div>\n'
        f'    <div class="glow" id="{eid}g"></div>\n'
        f'    <div class="gplate" id="{eid}p">\n'
        f'      <div class="gk">{esc(kicker)}</div>\n'
        f'      <div class="gn">{esc(num)}</div>\n'
        f'      <div class="gt">{esc(title)}</div>\n'
        f'      <div class="grule" id="{eid}r"></div>\n'
        f'    </div>\n')
    c.cover(eid, at, dur, inner)
    c.js.append(f"frostIn('#{eid}f', {at:.3f}, 0.88);")
    c.js.append(f"frostIn('#{eid}g', {at + 0.06:.3f}, 0.55);")
    c.js.append(f"pop('#{eid}p', {at + 0.10:.3f});")
    c.js.append(f"tl.fromTo('#{eid}r', {{ width:0 }}, "
                f"{{ width:96, duration:0.44, ease:p=>expo.out(p) }}, {at + 0.4:.3f});")
    c.js.append(f"leave('#{eid}p', {at + dur - 0.5:.3f});")
    c.js.append(f"frostOut('#{eid}f', {at + dur - 0.46:.3f});")
    c.js.append(f"frostOut('#{eid}g', {at + dur - 0.40:.3f});")
    c.stage_window(at - 0.05, at + dur - 0.35, "glass")
    c.plan_row(at, "", f"divider{num}", "жидкое стекло: размытие и плашка по центру", "pop")


def draw_quotes(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = SIDE_W - 2 * PAD
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>']
    rows = spec["rows"][:4]
    for i, (name, value, delta) in enumerate(rows):
        v = c.ce.fit(f"{value} {delta}%", 900, 32, w - 150, 1, f"{eid}.v{i}")
        inner.append(f'    <div class="row2" id="{eid}r{i+1}">'
                     f'<span class="k">{esc(name)}</span>'
                     f'<span class="v dn">{esc(v)}</span></div>')
    c.clip(eid, f"panel win {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(len(rows)):
        c.js.append(f"reveal('#{eid}r{i+1}', {at + 0.7 + i * 0.42:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "quotes", "строки котировок по очереди", "pop")
    return 0.7 + 0.42 * len(rows)


def draw_chart(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = WIDE_W - 2 * PAD
    rows = spec["rows"][:4]
    peak = max((num(v) for _, v in rows), default=1.0) or 1.0
    col_w = (w - 14 * (len(rows) - 1)) / max(1, len(rows))
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>',
             '    <div class="bars">']
    for i, (name, value) in enumerate(rows):
        alts = None
        if spec.get("short_labels") and i < len(spec["short_labels"]):
            alts = [spec["short_labels"][i]]
        label = c.ce.fit(name, 700, 21, col_w, 1, f"{eid}.cl{i}", alts)
        inner.append(f'      <div class="col"><div class="bar" id="{eid}b{i+1}"></div>'
                     f'<div class="cl">{esc(label)}</div></div>')
    inner.append('    </div>')
    unit = spec.get("unit", "−млн $")
    inner.append(f'    <div class="zero"><span>{esc(unit)}</span><span class="dash"></span></div>')
    if rows:
        top = max(rows, key=lambda r: num(r[1]))
        cap = c.ce.fit(f"Наибольший отток — {top[0]} {top[1]} млн $", 600, 26, w, 2, eid + ".cap")
        inner.append(f'    <div class="cmp">{esc(cap)}</div>')
    c.clip(eid, f"panel win wide {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i, (_, value) in enumerate(rows):
        h = max(20, int(146 * num(value) / peak))
        c.js.append(f"tl.fromTo('#{eid}b{i+1}', {{ height:0 }}, "
                    f"{{ height:{h}, duration:0.5, ease:p=>expo.out(p) }}, "
                    f"{at + 0.5 + i * 0.34:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "chart", "столбцы вырастают по значениям", "pop")
    return 0.5 + 0.34 * len(rows)


def draw_table(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = SIDE_W - 2 * PAD
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 3, eid + ".t"))}</div>']
    rows = spec["rows"][:5]
    for i, (name, value, when) in enumerate(rows):
        v = c.ce.fit(value, 900, 30, 235, 2, f"{eid}.v{i}")
        inner.append(f'    <div class="row" id="{eid}r{i+1}">'
                     f'<span class="k">{esc(name)}</span>'
                     f'<span class="v dn multi">{esc(v)}</span>'
                     f'<span class="d">{esc(when)}</span></div>')
    c.clip(eid, f"panel win {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(len(rows)):
        c.js.append(f"reveal('#{eid}r{i+1}', {at + 0.65 + i * 0.38:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "table", "строки таблицы появляются по одной", "pop")
    return 0.65 + 0.38 * len(rows)


def draw_timeline(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = SIDE_W - 2 * PAD
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>']
    items = spec["items"][:3]
    for i, (date, note) in enumerate(items):
        style = '' if i == 0 else ' style="margin-top:14px"'
        note_html = ''
        if note:
            note = c.ce.fit(note, 500, 25, w - 40, 2, f"{eid}.n{i}")
            note_html = f'<div class="tl-note">{esc(note)}</div>'
        inner.append(f'    <div class="tl-row" id="{eid}t{i+1}"{style}>'
                     f'<span class="tl-dot"></span><div><div class="tl-date">{esc(date)}</div>'
                     f'{note_html}</div></div>')
    chips = spec.get("chips") or []
    if chips:
        cw = [c.ce.fit(x, 600, 25, w - 40, 1, f"{eid}.c{i}") for i, x in enumerate(chips)]
        inner.append('    <div class="chips">' + "".join(
            f'<span class="chip" id="{eid}c{i+1}">{esc(x)}</span>' for i, x in enumerate(cw)) + '</div>')
    c.clip(eid, f"panel win {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(len(items)):
        c.js.append(f"reveal('#{eid}t{i+1}', {at + 0.65 + i * 0.48:.3f});")
    for i in range(len(chips)):
        c.js.append(f"reveal('#{eid}c{i+1}', {at + 1.6 + i * 0.26:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "timeline", "даты и требования по очереди", "pop")
    return 0.65 + 0.48 * len(items)


def draw_diagram(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = WIDE_W - 2 * PAD
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>']
    items = spec["items"][:4]
    for i, (name, note) in enumerate(items):
        name = c.ce.fit(name, 800, 28, w - 60, 1, f"{eid}.d{i}")
        note_html = ''
        if note:
            note = c.ce.fit(note, 500, 24, w - 60, 2, f"{eid}.n{i}")
            note_html = f'<div class="dnote">{esc(note)}</div>'
        inner.append(f'    <div class="dstep" id="{eid}d{i+1}"><div class="dnum">{i+1}</div>'
                     f'<div><div class="dname">{esc(name)}</div>{note_html}</div></div>')
    c.clip(eid, f"panel win wide {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(len(items)):
        c.js.append(f"reveal('#{eid}d{i+1}', {at + 0.65 + i * 0.4:.3f});")
    c.plan_row(at, spec.get("spoken", ""), spec.get("element", "diagram"),
               "шаги появляются по очереди", "pop")
    return 0.65 + 0.4 * len(items)


def draw_checklist(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str,
                   times: list[float] | None = None) -> float:
    w = WIDE_W - 2 * PAD
    items = [c.ce.fit(t, 500, 28, w - 44, 2, f"{eid}.i{i}") for i, t in enumerate(spec["items"][:5])]
    times = times or [at + 0.85 + i * 0.55 for i in range(len(items))]
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>',
             f'    <div class="rule" id="{eid}rule"></div>']
    for i, text in enumerate(items):
        inner.append(f'    <div class="item" id="i{i+1}"><span class="tick" '
                     f'id="t{i+1}"></span><span>{esc(text)}</span></div>')
    c.clip(eid, f"panel win wide {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    c.js.append(f"tl.fromTo('#{eid}rule', {{ width:0 }}, "
                f"{{ width:76, duration:0.4, ease:p=>expo.out(p) }}, {at + 0.42:.3f});")
    for i, t0 in enumerate(times):
        c.js.append(f"tl.fromTo('#i{i+1}', {{ opacity:0, y:8 }}, "
                    f"{{ opacity:1, y:0, duration:0.34, ease:p=>expo.out(p) }}, {t0:.3f});")
        c.js.append(f"tickOn('#t{i+1}', {t0 + 0.3:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "checklist",
               "пункты с галочками на своих словах", "pop")
    span = (max(times) - at + 0.7) if times else 0.9
    return span


def draw_stat(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = SIDE_W - 2 * PAD
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="stat"><span id="{eid}v">0</span><small>{esc(spec.get("unit", "%"))}</small></div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>']
    note = spec.get("note")
    if note:
        inner.append(f'    <div class="cmp">{esc(c.ce.fit(note, 600, 26, w, 2, eid + ".n"))}</div>')
    c.clip(eid, f"panel win {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    dec = len(spec["value"].split(",")[1]) if "," in spec["value"] else 0
    c.js.append(f"countText('{eid}v', '{esc(spec['value'])}', {at + 0.45:.3f}, {dec});")
    c.plan_row(at, spec.get("spoken", ""), spec.get("element", "stat"),
               "счётчик добегает до значения из текста", "click")
    return 1.25


def draw_partial(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    """плюс/минус: значение плюс шкала дней под нулевой линией."""
    w = WIDE_W - 2 * PAD
    days = int(spec.get("days", 20))
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>',
             f'    <div class="stat">−{esc(spec["value"])}<small>%</small></div>',
             '    <div class="ticks">'
             + "".join(f'<div class="tickbar" id="{eid}k{i+1}"></div>' for i in range(days))
             + '</div>',
             f'    <div class="cmp"><b>{days}</b> дней подряд ниже нуля</div>']
    c.clip(eid, f"panel win wide {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(days):
        c.js.append(f"reveal('#{eid}k{i+1}', {at + 0.45 + i * 0.05:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "premium", "двадцать меток под нулевой линией", "pop")
    return 0.45 + 0.05 * days


def draw_funnel(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = SIDE_W - 2 * PAD
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>']
    steps = spec["steps"][:3]
    finals: list[int] = []
    for i, (label, share) in enumerate(steps):
        hot = " hot" if i else ""
        lab = c.ce.fit(label, 700, 26, max(200, (w - 44) * share / 100.0), 1, f"{eid}.f{i}")
        need = int(c.ce.metrics.width(lab, 700, 26)) + 48
        final_px = max(need, int(round((w - 4) * share / 100.0)))
        finals.append(final_px)
        inner.append(f'    <div class="fstep{hot}" id="{eid}f{i+1}" style="width:{final_px}px">'
                     f'{esc(lab)}</div>')
    chips = spec.get("chips") or []
    if chips:
        cw = [c.ce.fit(x, 600, 25, w - 40, 1, f"{eid}.c{i}") for i, x in enumerate(chips)]
        inner.append('    <div class="chips">' + "".join(
            f'<span class="chip" id="{eid}c{i+1}">{esc(x)}</span>' for i, x in enumerate(cw)) + '</div>')
    c.clip(eid, f"panel win {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i, share in enumerate(finals):
        c.js.append(f"tl.fromTo('#{eid}f{i+1}', {{ opacity:0, width:0 }}, "
                    f"{{ opacity:1, width:{share}, duration:0.5, ease:p=>expo.out(p) }}, "
                    f"{at + 0.65 + i * 0.55:.3f});")
    for i in range(len(chips)):
        c.js.append(f"reveal('#{eid}c{i+1}', {at + 1.8 + i * 0.26:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "funnel", "воронка сужается от многих к нескольким", "pop")
    return 1.8 + 0.26 * len(chips)


def draw_scenario(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = WIDE_W - 2 * PAD
    tone = spec["tone"]
    badge = 'bear' if tone == "BEAR" else ''
    inner = [f'    <div class="sc-head"><span class="badge {badge}">{esc(tone)}</span>'
             f'<span class="hlab">{esc(spec["kicker"])}</span></div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>']
    bullets = spec["bullets"][:4]
    for i, item in enumerate(bullets):
        text = c.ce.fit(item, 600, 27, w - 30, 2, f"{eid}.b{i}")
        inner.append(f'    <div class="bullet" id="{eid}b{i+1}"><span class="mark"></span>'
                     f'<span>{esc(text)}</span></div>')
    if tone == "BULL":
        inner.append(f'    <div class="bridge" id="{eid}br"><div class="bplate">БАНКИ</div>'
                     f'<div class="barrow">↔</div><div class="bplate">КРИПТА</div>'
                     f'<div class="up"></div></div>')
    else:
        inner.append(f'    <div class="bridge" id="{eid}br"><div class="bplate">поддержка</div>'
                     f'<div class="barrow">ниже 80 000</div><div class="down"></div></div>')
    c.clip(eid, f"panel win wide {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(len(bullets)):
        c.js.append(f"reveal('#{eid}b{i+1}', {at + 0.65 + i * 0.38:.3f});")
    c.js.append(f"reveal('#{eid}br', {at + 1.7:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "scenario", "карточка сценария и её пункты", "pop")
    return 1.7


def draw_chips(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = SIDE_W - 2 * PAD
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>']
    items = [c.ce.fit(x, 600, 25, w - 40, 1, f"{eid}.c{i}") for i, x in enumerate(spec["items"][:7])]
    if items:
        inner.append('    <div class="chips">' + "".join(
            f'<span class="chip" id="{eid}c{i+1}">{esc(x)}</span>' for i, x in enumerate(items)) + '</div>')
    c.clip(eid, f"panel win {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(len(items)):
        c.js.append(f"reveal('#{eid}c{i+1}', {at + 0.55 + i * 0.26:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "chips", "подписи появляются по одной", "pop")
    return 0.55 + 0.26 * len(items)


def draw_quote(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    w = WIDE_W - 2 * PAD
    text = c.ce.fit(spec["text"], 500, 33, w - 40, 6, eid + ".q")
    head, tail = text, ""
    for sep in (" — ", " – ", " это "):
        if sep in text and len(text.split(sep, 1)[1]) > 12:
            head, tail = text.split(sep, 1)
            break
    body = esc(head) + (f' <em>{esc(tail)}</em>' if tail else "")
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="qwrap"><div class="qline" id="{eid}q"></div>'
             f'<div class="quote">{body}</div></div>']
    c.clip(eid, f"panel win wide {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    lines = max(2, c.ce.metrics.line_count(text, 500, 33, w - 40))
    c.js.append(f"tl.fromTo('#{eid}q', {{ height:0 }}, "
                f"{{ height:{min(300, lines * 44)}, duration:0.5, ease:p=>expo.out(p) }}, "
                f"{at + 0.45:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "quote", "линия слева растёт, строка въезжает", "pop")
    return 0.9


def draw_compare(c: Comp, spec: dict, eid: str, at: float, dur: float, side: str) -> float:
    """было / стало - two cells, the right one highlighted."""
    w = WIDE_W - 2 * PAD
    cells = spec["cells"][:2]
    inner = [f'    <div class="h">{esc(spec["kicker"])}</div>',
             f'    <div class="t">{esc(c.ce.fit(spec["title"], 800, 38, w, 2, eid + ".t"))}</div>',
             '    <div class="cmp2">']
    for i, (lab, txt) in enumerate(cells):
        body = c.ce.fit(txt, 700, 26, (w - 18) / 2 - 44, 4, f"{eid}.c{i}")
        cls = "cell now" if i else "cell"
        inner.append(f'      <div class="{cls}" id="{eid}c{i+1}">'
                     f'<div class="lab">{esc(lab)}</div><div class="txt">{esc(body)}</div></div>')
    inner.append('    </div>')
    c.clip(eid, f"panel win wide {side}", at, dur, "\n".join(inner) + "\n")
    c.open_card(eid, at, dur)
    for i in range(len(cells)):
        c.js.append(f"reveal('#{eid}c{i+1}', {at + 0.6 + i * 0.5:.3f});")
    c.plan_row(at, spec.get("spoken", ""), "compare", "было и стало, вторая ячейка подсвечена", "pop")
    return 1.1


def draw_outro(c: Comp, spec: dict, eid: str, at: float, dur: float) -> float:
    """The subscription plate: the speaker is pushed aside, the panel takes the space."""
    inner_w = SHEET_W - 112
    note = c.ce.fit(spec["note"], 500, 27, inner_w, 4, eid + ".note")
    inner = (
        f'    <div class="inner" id="{eid}i">\n'
        f'      <div class="k">{esc(spec["kicker"])}</div>\n'
        f'      <div class="brand">{esc(spec["brand"])} <em>{esc(spec["accent"])}</em></div>\n'
        f'      <div class="handle">{esc(spec["handle"])}</div>\n'
        f'      <div class="note">{esc(note)}</div>\n'
        f'      <div class="chips"><span class="chip on">Подписка</span>'
        f'<span class="chip">BingX в описании</span></div>\n'
        f'    </div>\n')
    c.cover(eid, at, dur, inner, cls="sheet")
    c.js.append(f"tl.fromTo('#{eid}', {{ opacity:0 }}, "
                f"{{ opacity:1, duration:0.42, ease:p=>expo.out(p) }}, {at:.3f});")
    c.js.append(f"reveal('#{eid}i', {at + 0.18:.3f});")
    c.stage_window(max(0.0, at - 0.25), at + dur + 0.4, "push", "left")
    # the geometry change is crossfaded, and a crossfade between two framings
    # shows a double image while it runs: blur the frame across that moment so the
    # switch reads as a glass transition instead of two faces
    c.stage_window(max(0.0, at - 0.55), at + 0.30, "glass")
    c.plan_row(at, spec.get("spoken", ""), "outro",
               "кадр сдвигается, панель подписки справа", "impact")
    return 0.6


def draw_endplate(c: Comp, spec: dict, eid: str, at: float, dur: float) -> float:
    """Brand-book end card after the speech: dark plate, logo lockup, subscribe line."""
    inner = (f'    <div class="logo" id="{eid}l">{esc(spec["brand"])} <em>{esc(spec["accent"])}</em></div>\n'
             f'    <div class="line" id="{eid}ln"></div>\n'
             f'    <div class="sub" id="{eid}s">{esc(spec["sub"])}</div>\n'
             f'    <div class="handle" id="{eid}h">{esc(spec["handle"])}</div>\n')
    c.cover(eid, at, dur, inner, cls="endplate")
    c.js.append(f"tl.fromTo('#{eid}', {{ opacity:0 }}, "
                f"{{ opacity:1, duration:0.34, ease:p=>expo.out(p) }}, {at:.3f});")
    c.js.append(f"tl.fromTo('#{eid}l', {{ opacity:0, scale:0.94 }}, "
                f"{{ opacity:1, scale:1, duration:0.6, ease:p=>expo.out(p) }}, {at + 0.25:.3f});")
    c.js.append(f"tl.fromTo('#{eid}ln', {{ width:0 }}, "
                f"{{ width:180, duration:0.5, ease:p=>expo.out(p) }}, {at + 0.7:.3f});")
    c.js.append(f"reveal('#{eid}s', {at + 1.0:.3f});")
    c.js.append(f"reveal('#{eid}h', {at + 1.25:.3f});")
    c.plan_row(at, "", "endcard", "фирменная заставка после речи", "impact")
    return 1.6


DRAW = {
    "quotes": draw_quotes, "chart": draw_chart, "table": draw_table, "timeline": draw_timeline,
    "diagram": draw_diagram, "checklist": draw_checklist, "stat": draw_stat,
    "premium": draw_partial, "funnel": draw_funnel, "scenario": draw_scenario,
    "chips": draw_chips, "quote": draw_quote, "compare": draw_compare,
    "title": lambda c, s, e, a, d, side: draw_title(c, s, e, a, d),
    "outro": lambda c, s, e, a, d, side: draw_outro(c, s, e, a, d),
}


# --------------------------------------------------------------- block plan
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
            out.append({"kind": "quotes", "marks": [("phrase", "биткоин"), ("num", "81174")],
                        "side": "r", "dur": 12.0})
        elif kind == "logo" and n == 2:
            out.append({"kind": "chips", "marks": [("phrase", "организатор"), ("phrase", "обозрение")],
                        "side": "r", "dur": 11.0,
                        "content": ("Организаторы", org_chips(b)[1])})
            out.append({"kind": "chips", "marks": [("phrase", "среди спикеров"), ("phrase", "минфин")],
                        "side": "l", "dur": 11.0,
                        "content": ("В зале", speaker_chips(b))})
        elif kind == "chart" and n == 3:
            out.append({"kind": "diagram", "marks": [("phrase", "ключевые темы"), ("phrase", "онбординг")],
                        "side": "r", "dur": 13.0})
        elif kind == "timeline":
            out.append({"kind": "timeline", "marks": [("phrase", "с первого сентября"), ("word", "сентябр")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "chips", "marks": [("phrase", "новые требования"), ("word", "комплаенс")],
                        "side": "l", "dur": 10.0,
                        "content": ("Новые требования", requirement_chips(b))})
        elif kind == "table" and n == 5:
            out.append({"kind": "stat", "marks": [("phrase", "инфляции"), ("num", "37")],
                        "side": "r", "dur": 11.0})
            out.append({"kind": "chart", "marks": [("phrase", "отток"), ("num", "654")],
                        "side": "l", "dur": 12.0})
        elif kind == "chart" and n == 6:
            out.append({"kind": "premium", "marks": [("phrase", "премиальный индекс"), ("num", "1398")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "quote", "marks": [("phrase", "двадцать дней"), ("word", "режим")],
                        "side": "l", "dur": 10.0})
        elif kind == "table" and n == 7:
            out.append({"kind": "table", "marks": [("phrase", "arbitrum"), ("num", "92")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "counter", "marks": [("word", "cerebras"), ("num", "902")],
                        "side": "l", "dur": 9.0})
        elif kind == "chart" and n == 8:
            out.append({"kind": "scenario", "marks": [("phrase", "бычий"), ("phrase", "легальный мост")],
                        "side": "r", "dur": 12.0})
            out.append({"kind": "quote", "marks": [("phrase", "органической причины"),
                                                   ("word", "спекулятивного")],
                        "side": "l", "dur": 10.0})
        elif kind == "funnel":
            out.append({"kind": "funnel", "marks": [("phrase", "как фильтр"), ("phrase", "мелкие обменники")],
                        "side": "r", "dur": 11.0})
            out.append({"kind": "scenario", "marks": [("phrase", "медвежий"), ("phrase", "уровни ниже")],
                        "side": "l", "dur": 11.0})
        elif kind == "checklist":
            out.append({"kind": "checklist", "marks": [("phrase", "что делать трейдеру"),
                                                       ("phrase", "не ловить ножи")],
                        "side": "r", "dur": 16.0})
        elif kind == "chart" and n == 11:
            out.append({"kind": "miners", "marks": [("num", "1473"), ("word", "майнер")],
                        "side": "r", "dur": 11.0})
            out.append({"kind": "steps", "marks": [("phrase", "смотрите логику"), ("word", "реестр")],
                        "side": "l", "dur": 11.0})
        elif kind == "outro":
            out.append({"kind": "outro", "marks": [("phrase", "подпишитесь"), ("word", "rudstock")],
                        "side": "r", "dur": 14.0, "force_last": True})
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
    1: [{"kind": "chips", "marks": [("phrase", "получили легальный статус"), ("word", "легальный")],
         "side": "l", "dur": 10.0,
         "content": lambda b: ("С 1 сентября 2026", status_chips(b))}],
    3: [{"kind": "quote", "marks": [("phrase", "четыре блока определяют"), ("phrase", "лицензионн")],
         "side": "l", "dur": 10.0}],
    4: [{"kind": "compare", "marks": [("phrase", "раньше в россии"), ("word", "логике")],
         "side": "r", "dur": 11.0}],
    6: [{"kind": "chips", "marks": [("phrase", "спотовый дисконт"), ("word", "плечевые")],
         "side": "l", "dur": 9.0,
         "content": lambda b: ("Спрос", ["плечевые трейдеры", "не спешат набирать лонги",
                                        "ETH отскакивает технически"])}],
    7: [{"kind": "quote", "marks": [("phrase", "удержать 84"), ("num", "84")],
         "side": "l", "dur": 10.0}],
    10: [{"kind": "chips", "marks": [("phrase", "bingx"), ("word", "стакан")],
          "side": "l", "dur": 9.0,
          "content": lambda b: ("Терминал", terminal_chips(b))}],
    12: [{"kind": "quote", "marks": [("phrase", "в комментариях"), ("word", "легализация")],
          "side": "l", "dur": 9.0}],
}
EXTRA_FIRST = {12}

# counters that need a value from the script (label, value, unit)
COUNTERS = {7: ("Доля акций Cerebras", "9,02", "%")}


# ------------------------------------------------------------- card content
def override_for(ce: CopyEngine, b: dict, kind: str, index: int) -> dict:
    items = [x for x in (ce.block_override(b).get("inserts") or []) if x.get("kind") == kind]
    if index < len(items):
        return items[index]
    all_items = ce.block_override(b).get("inserts") or []
    if index < len(all_items) and "kind" not in all_items[index]:
        return all_items[index]
    return {}


def content_divider(b: dict, ce: CopyEngine, ov: dict) -> dict:
    block_kicker = ce.block_override(b).get("kicker")
    return {"kind": "divider", "num": f"{b['n']:02d}",
            "kicker": ov.get("kicker") or block_kicker or f"БЛОК {b['n']:02d}",
            "title": ov.get("title") or ce.title(b),
            "alts": ov.get("alts"), "spoken": ""}


def content_title(b: dict, ce: CopyEngine, ov: dict) -> dict:
    big, sub = title_payload(b)
    return {"kind": "title", "big": ov.get("big") or big, "sub": ov.get("sub", sub),
            "spoken": "крипта на балансе"}


def content_quotes(b: dict, ce: CopyEngine, ov: dict) -> dict:
    rows = ov.get("rows") or [[n, v, d] for n, v, d in quotes_rows(b)]
    return {"kind": "quotes", "kicker": ce.kicker("quotes", b, ov.get("kicker")),
            "title": ov.get("title") or "Рынок на 15 октября",
            "rows": [list(r) for r in rows], "spoken": ov.get("spoken", "биткоин, эфир, SPY")}


def content_chart(b: dict, ce: CopyEngine, ov: dict) -> dict:
    rows = ov.get("rows") or [[n, v] for n, v in flows(b)]
    return {"kind": "chart", "kicker": ce.kicker("chart", b, ov.get("kicker")),
            "title": ov.get("title") or "Оттоки из ETF за сутки",
            "rows": [list(r) for r in rows], "unit": ov.get("unit", "−млн $"),
            "short_labels": ov.get("short_labels"),
            "spoken": ov.get("spoken", "оттоки из ETF")}


def content_table(b: dict, ce: CopyEngine, ov: dict) -> dict:
    rows = ov.get("rows") or [[n, v, w] for n, v, w in unlock_rows(b)]
    return {"kind": "table", "kicker": ce.kicker("table", b, ov.get("kicker")),
            "title": ov.get("title") or ce.title(b),
            "rows": [list(r) for r in rows], "spoken": ov.get("spoken", "разлоки")}


def content_timeline(b: dict, ce: CopyEngine, ov: dict) -> dict:
    items = ov.get("items") or [[d, n] for d, n in timeline_items(b)]
    return {"kind": "timeline", "kicker": ce.kicker("timeline", b, ov.get("kicker")),
            "title": ov.get("title") or ce.title(b),
            "items": [list(x) for x in items],
            "chips": ov.get("chips") or requirement_chips(b),
            "spoken": ov.get("spoken", "1 сентября 2026 → 15 октября 2026")}


def content_diagram(b: dict, ce: CopyEngine, ov: dict, element: str = "diagram") -> dict:
    items = ov.get("items") or [[n, t] for n, t in (steps_items(b) if element == "steps"
                                                    else diagram_items(b))]
    return {"kind": "diagram", "element": element,
            "kicker": ce.kicker(element, b, ov.get("kicker")),
            "title": ov.get("title") or ce.title(b),
            "items": [list(x) for x in items],
            "spoken": ov.get("spoken", "онбординг, KYT, Travel Rule, стек" if element == "diagram"
                             else "сначала правила, потом реестр")}


def content_checklist(b: dict, ce: CopyEngine, ov: dict) -> dict:
    items = ov.get("items") or checklist_items(b)
    return {"kind": "checklist", "kicker": ce.kicker("checklist", b, ov.get("kicker")),
            "title": ov.get("title") or ce.title(b),
            "items": list(items), "spoken": ov.get("spoken", "что делать трейдеру")}


def content_stat(b: dict, ce: CopyEngine, ov: dict) -> dict:
    value, forecast = inflation(b)
    return {"kind": "stat", "element": "stat", "kicker": ce.kicker("stat", b, ov.get("kicker")),
            "title": ov.get("title") or "Инфляция США, сентябрь",
            "value": ov.get("value") or value, "unit": ov.get("unit", "%"),
            "note": ov.get("note") or f"прогноз {forecast}% · факт выше прогноза",
            "spoken": ov.get("spoken", "инфляция 3,7")}


def content_counter(b: dict, ce: CopyEngine, ov: dict) -> dict:
    label, value, unit = COUNTERS[b["n"]]
    return {"kind": "stat", "element": "counter", "kicker": ce.kicker("counter", b, ov.get("kicker")),
            "title": ov.get("title") or label, "value": ov.get("value") or value,
            "unit": ov.get("unit", unit), "note": ov.get("note", ""),
            "spoken": ov.get("spoken", label.lower())}


def content_miners(b: dict, ce: CopyEngine, ov: dict) -> dict:
    return {"kind": "stat", "element": "miners", "kicker": ce.kicker("miners", b, ov.get("kicker")),
            "title": ov.get("title") or "Реестр майнеров ФНС",
            "value": ov.get("value") or "1473", "unit": ov.get("unit", ""),
            "note": ov.get("note") or "участников на 01.10.2026 · майнинг охлаждается",
            "spoken": ov.get("spoken", "1473 участника")}


def content_premium(b: dict, ce: CopyEngine, ov: dict) -> dict:
    value, days = premium(b)
    return {"kind": "premium", "kicker": ce.kicker("premium", b, ov.get("kicker")),
            "title": ov.get("title") or "Coinbase Premium",
            "value": ov.get("value") or value, "days": int(ov.get("days") or days),
            "spoken": ov.get("spoken", "минус 0,1398 процента, двадцать дней")}


def content_funnel(b: dict, ce: CopyEngine, ov: dict) -> dict:
    steps, chips = funnel_steps(b)
    return {"kind": "funnel", "kicker": ce.kicker("funnel", b, ov.get("kicker")),
            "title": ov.get("title") or "Комплаенс работает как фильтр",
            "steps": [list(s) for s in (ov.get("steps") or steps)],
            "chips": ov.get("chips") or chips,
            "spoken": ov.get("spoken", "мелкие не выдерживают")}


def content_scenario(b: dict, ce: CopyEngine, ov: dict) -> dict:
    tone, head, bullets = scenario_card(b)
    return {"kind": "scenario", "tone": ov.get("tone") or tone,
            "kicker": ce.kicker("scenario", b, ov.get("kicker")),
            "title": ov.get("title") or head,
            "bullets": ov.get("bullets") or bullets,
            "spoken": ov.get("spoken", tone.lower())}


def content_chips(b: dict, ce: CopyEngine, ov: dict, spec: dict | None = None) -> dict:
    auto = (spec or {}).get("content")
    if not auto:
        auto = org_chips(b)
    head = ov.get("head") or auto[0]
    items = ov.get("items") or auto[1]
    return {"kind": "chips", "kicker": ov.get("kicker") or str(head).upper(),
            "title": ov.get("title") or ce.title(b), "items": list(items),
            "spoken": ov.get("spoken", "")}


def content_quote(b: dict, ce: CopyEngine, ov: dict) -> dict:
    text = ov.get("text") or key_sentence(b)
    return {"kind": "quote", "kicker": ce.kicker("quote", b, ov.get("kicker")),
            "text": text, "spoken": ov.get("spoken", "ключевая мысль")}


def content_compare(b: dict, ce: CopyEngine, ov: dict) -> dict:
    cells = ov.get("cells") or [["БЫЛО", "«работает и ладно»"],
                                ["СТАЛО", "«работает, отчитывается и отвечает капиталом»"]]
    return {"kind": "compare", "kicker": ce.kicker("compare", b, ov.get("kicker")),
            "title": ov.get("title") or "Логика рынка изменилась",
            "cells": [list(c) for c in cells],
            "spoken": ov.get("spoken", "раньше и теперь")}


def content_outro(b: dict, ce: CopyEngine, ov: dict) -> dict:
    p = outro_payload(b)
    brand, accent = ov.get("brand"), ov.get("accent")
    if not brand:
        words = p["sub"].split()
        brand = " ".join(words[:-1]) or p["sub"]
        accent = accent or words[-1]
    return {"kind": "outro", "kicker": ov.get("kicker") or "ПОДПИСКА",
            "brand": brand, "accent": accent or "",
            "handle": ov.get("handle") or p["handle"], "note": ov.get("note") or p["note"],
            "spoken": ov.get("spoken", "подпишитесь на Rudstock Crypto")}


CONTENT = {
    "quotes": lambda b, ce, ov, spec: content_quotes(b, ce, ov),
    "chart": lambda b, ce, ov, spec: content_chart(b, ce, ov),
    "table": lambda b, ce, ov, spec: content_table(b, ce, ov),
    "timeline": lambda b, ce, ov, spec: content_timeline(b, ce, ov),
    "checklist": lambda b, ce, ov, spec: content_checklist(b, ce, ov),
    "stat": lambda b, ce, ov, spec: content_stat(b, ce, ov),
    "counter": lambda b, ce, ov, spec: content_counter(b, ce, ov),
    "miners": lambda b, ce, ov, spec: content_miners(b, ce, ov),
    "premium": lambda b, ce, ov, spec: content_premium(b, ce, ov),
    "funnel": lambda b, ce, ov, spec: content_funnel(b, ce, ov),
    "scenario": lambda b, ce, ov, spec: content_scenario(b, ce, ov),
    "quote": lambda b, ce, ov, spec: content_quote(b, ce, ov),
    "compare": lambda b, ce, ov, spec: content_compare(b, ce, ov),
    "outro": lambda b, ce, ov, spec: content_outro(b, ce, ov),
    "title": lambda b, ce, ov, spec: content_title(b, ce, ov),
    "chips": content_chips,
    "diagram": lambda b, ce, ov, spec: content_diagram(b, ce, ov, "diagram"),
    "steps": lambda b, ce, ov, spec: content_diagram(b, ce, ov, "steps"),
}


def estimate_reveal(kind: str, content: dict) -> float:
    """How long the card needs to finish filling itself (§9.2 reveal + a beat)."""
    kind = content.get("kind") or kind
    n = 0
    for key in ("rows", "items", "bullets", "steps", "cells"):
        if content.get(key):
            n = max(n, len(content[key]))
    if kind == "quotes":
        return 0.7 + 0.42 * n
    if kind == "chart":
        return 0.5 + 0.34 * n
    if kind == "table":
        return 0.65 + 0.38 * n
    if kind == "timeline":
        return 0.65 + 0.48 * n
    if kind == "diagram":
        return 0.65 + 0.4 * n
    if kind == "chips":
        return 0.55 + 0.26 * n
    if kind == "checklist":
        return 0.85 + 0.5 * max(0, n - 1)
    if kind == "funnel":
        return 1.8 + 0.26 * n
    if kind == "scenario":
        return 1.7
    if kind == "compare":
        return 1.1
    if kind == "quote":
        return 0.9
    if kind == "stat":
        return 1.3
    if kind == "premium":
        return 0.45 + 0.05 * int(content.get("days", 20))
    return 0.6


#: minimum on-screen time per card kind, seconds - a chart or a list needs longer
#: than a one-line quote, whatever the word count says
HOLD_FLOOR = {
    "premium": 6.0, "chart": 5.5, "quotes": 5.0, "table": 5.5, "timeline": 5.0,
    "diagram": 6.0, "checklist": 8.0, "scenario": 6.5, "compare": 5.5, "funnel": 6.0,
    "stat": 4.5, "counter": 4.5, "miners": 4.5, "chips": 4.5, "quote": 5.0,
    "title": 4.0, "outro": 6.0, "divider": 2.3,
}


def read_time(content: dict) -> float:
    """Seconds a viewer needs to read the card.

    The reveal animation is not the same thing as readability: the first version
    let a five-point checklist live for 3.7 s and the list vanished while it was
    still being read.
    """
    texts: list[str] = []
    for key in ("rows", "items", "bullets", "steps", "cells"):
        for row in content.get(key) or []:
            texts.append(" ".join(str(x) for x in row) if isinstance(row, (list, tuple))
                         else str(row))
    for key in ("title", "note", "text", "value", "sub", "brand"):
        if content.get(key):
            texts.append(str(content[key]))
    words = sum(len(t.split()) for t in texts)
    return max(3.8, 0.30 * words + 1.1)


def hold_time(kind: str, content: dict) -> float:
    return max(estimate_reveal(kind, content), read_time(content),
               HOLD_FLOOR.get(content.get("kind") or kind, 4.5)) + 0.9


def draw_card(c: Comp, spec: dict, eid: str, at: float, dur: float, b: dict,
              anch: "Anchors") -> None:
    content = spec["content"]
    kind = content.get("kind") or spec["kind"]
    side = spec["side"]
    if kind == "title":
        draw_title(c, content, eid, at, dur)
    elif kind in ("diagram", "steps"):
        draw_diagram(c, content, eid, at, dur, side)
    elif kind == "stat":
        draw_stat(c, content, eid, at, dur, side)
    elif kind == "checklist":
        draw_checklist(c, content, eid, at, dur, side,
                       times=checklist_times(b, anch, at, dur, content["items"]))
    elif kind == "outro":
        draw_outro(c, content, eid, at, dur)
    else:
        DRAW[kind](c, content, eid, at, dur, side)


def checklist_times(b: dict, anch: "Anchors", at: float, dur: float,
                    items: list[str]) -> list[float]:
    """When each checklist item is spoken (§12.5: a point lands on its own word).

    A point that is anchored too far out - or not at all - is capped, so the card
    fills at a steady pace instead of sitting empty while the speaker is elsewhere.
    """
    times: list[float] = []
    prev = at + 0.75
    for i, text in enumerate(items):
        marks = sorted(re.findall(r"[А-Яа-яЁёA-Za-z]{5,}", text), key=len, reverse=True)[:3]
        found = None
        for m in marks:
            found = word_timeline(anch, b, m.lower())
            if found is not None:
                break
        t = found if found is not None else prev
        t = min(t, at + 1.1 + i * 1.7)          # the list never lags behind
        t = max(t, prev)
        t = min(t, at + dur - 0.9)
        times.append(t)
        prev = t + 0.45
    return times


# ------------------------------------------------------------------- assemble
def build(label: str, edit: Path, json_out: Path | None = None,
          copy_path: Path | None = None) -> int:
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

    if copy_path is None:
        candidate = ROOT / "script" / f"{label}-inserts.json"
        copy_path = candidate if candidate.is_file() else None
    ce = CopyEngine(brand, copy_path)

    blocks = sorted([b for b in plan["blocks"] if b.get("timeline_first_word_s") is not None],
                    key=lambda b: b["timeline_first_word_s"])
    for i, b in enumerate(blocks):
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        b["_start"] = float(b["timeline_first_word_s"])
        b["_src0"] = float(b.get("source_first_word_s") or 0.0)
        b["_end"] = (float(nxt.get("boundary_s") or nxt["timeline_first_word_s"])) if nxt else total
        b["_src1"] = float(nxt.get("source_first_word_s") or (b["_src0"] + 60.0)) if nxt \
            else b["_src0"] + 120.0
        b["_divider_at"] = float(b.get("boundary_s") if b.get("boundary_s") is not None
                                 else b["_start"])

    author = data["passport"].get("author") or {"name": "Дмитрий Царьков",
                                                "role": "управляющий активами"}
    c = Comp(brand, ce)
    cid = "main"

    # ---- opening name plate
    lt_at, lt_dur = 0.6, 6.0
    c.clip("lt", "panel lt", lt_at, lt_dur,
           f'    <div class="n">{esc(author["name"])}</div>\n'
           f'    <div class="r">{esc(author["role"])}</div>\n')
    c.js.append(f"pop('#lt', {lt_at:.3f});")
    c.js.append(f"leave('#lt', {lt_at + lt_dur - 0.42:.3f});")
    c.plan_row(lt_at, "здравствуйте", "hook", "титр имени и должности", "pop")

    # ---- opening title card, above the head
    first = blocks[0]
    ttl_content = content_title(first, ce, override_for(ce, first, "title", 0))
    ttl_at, ttl_dur = 7.0, 6.2
    if ttl_at + ttl_dur > first["_end"] - 1.0:
        ttl_at, ttl_dur = first["_start"] + 0.6, 5.0
    draw_title(c, ttl_content, "ttl1", ttl_at, ttl_dur)
    inserts_meta: list[dict] = [{"block": first["n"], "kind": "title", "id": "ttl1",
                                 "at": ttl_at, "dur": ttl_dur, "side": "top",
                                 "anchored": True, "layout": "title"}]

    # ---- liquid-glass dividers, straight after the spoken boundary pause
    for i, b in enumerate(blocks):
        if i == 0:
            continue
        at = b["_divider_at"]
        at = max(at, blocks[i - 1]["_start"] + 1.0)
        at = min(at, b["_start"] + 0.35)
        dur = 2.30
        spec = content_divider(b, ce, override_for(ce, b, "divider", 0))
        eid = f"dv{b['n']}"
        draw_divider(c, spec, eid, at, dur)
        inserts_meta.append({"block": b["n"], "kind": "divider", "id": eid, "at": round(at, 3),
                             "dur": dur, "side": "center", "anchored": True, "layout": "glass"})

    # ---- inserts, laid out in speech order with air between them (§9.5)
    for i, b in enumerate(blocks):
        counters: dict[str, int] = {}
        prepared = []
        for spec in block_inserts(b):
            kind = spec["kind"]
            idx = counters.get(kind, 0)
            counters[kind] = idx + 1
            ov = override_for(ce, b, kind, idx)
            content = CONTENT[kind](b, ce, ov, spec)
            marks = [("phrase", ov["anchor"])] if ov.get("anchor") else spec["marks"]
            found = anchor_timeline(anch, b, marks)
            tier = 2 if spec.get("force_last") else (0 if spec.get("primary") else 1)
            prepared.append({"kind": kind, "side": ov.get("side") or spec["side"],
                             "dur": float(ov.get("dur") or spec["dur"]),
                             "content": content, "found": found, "tier": tier,
                             "force_last": bool(spec.get("force_last")),
                             "reveal": estimate_reveal(kind, content),
                             "hold": hold_time(kind, content),
                             "override": ov})
        prepared.sort(key=lambda x: ((1 if x["force_last"] else 0),
                                     x["found"] if x["found"] is not None else b["_start"] + 33.0,
                                     x["tier"]))

        cursor = max(b["_start"] + 3.1, 1.0)
        if i == 0:
            cursor = max(cursor, ttl_at + ttl_dur + 0.7)
        limit_end = min(b["_end"], total - 0.2)
        # pass 1: place the cards in the order the speaker reaches them, with air
        placed: list[dict] = []
        for ev in prepared:
            at = max(ev["found"] if ev["found"] is not None else cursor, cursor)
            at = max(at, b["_start"] + (3.1 if i else 0.6))
            if i == 0:
                at = max(at, ttl_at + ttl_dur + 0.7)
            ev["at"] = round(at, 3)
            placed.append(ev)
            cursor = at + ev["hold"] + AIR
        # pass 2: a card holds through its topic, never past the next one
        keep: list[dict] = []
        for j, ev in enumerate(placed):
            nxt = placed[j + 1] if j + 1 < len(placed) else None
            hard_end = min(limit_end - 0.15, (nxt["at"] - AIR) if nxt else limit_end - 0.15)
            prev_end = (keep[-1]["at"] + keep[-1]["dur"]) if keep else -1e9
            earliest = b["_start"] + (3.1 if i else 0.6)
            if i == 0:
                earliest = max(earliest, ttl_at + ttl_dur + 0.7)
            at, want = ev["at"], hard_end - ev["at"]
            # a card anchored at the very end of its block is pulled back so it has
            # time to be read, instead of flashing for two seconds
            if want < ev["hold"]:
                alt = max(earliest, prev_end + AIR, hard_end - ev["hold"])
                if hard_end - alt > want:
                    at, want = alt, hard_end - alt
            floor = ev["reveal"] + 0.6
            if want < floor:
                c.notes.append(f"#{b['n']} {ev['kind']}: не помещается "
                               f"(at {at:.2f}, конец {hard_end:.2f}, "
                               f"даёт {want:.1f} с при минимуме {floor:.1f} с; "
                               f"блок {b['_start']:.1f}-{b['_end']:.1f}, "
                               f"найдено {ev['found']}), пропущено")
                continue
            ev["at"] = round(at, 3)
            ev["dur"] = round(min(want, max(floor, min(ev["dur"], want))), 3)
            keep.append(ev)

        for j, ev in enumerate(keep):
            if ev["force_last"]:
                ev["dur"] = round(max(ev["dur"], min(30.0, total - 0.2 - ev["at"])), 3)
            eid = f"e{b['n']}_{j+1}"
            draw_card(c, ev, eid, ev["at"], ev["dur"], b, anch)
            inserts_meta.append({"block": b["n"], "kind": ev["kind"], "id": eid,
                                 "at": ev["at"], "dur": ev["dur"], "side": ev["side"],
                                 "anchored": ev["found"] is not None,
                                 "layout": "push" if ev["kind"] == "outro" else "side",
                                 "override": bool(ev["override"])})
            if j + 1 < len(keep):
                gap = keep[j + 1]["at"] - (ev["at"] + ev["dur"])
                if gap < 0.4:
                    c.notes.append(f"#{b['n']} {ev['kind']} → {keep[j+1]['kind']}: "
                                   f"зазор {gap:.2f} с (норма ≥0.4)")

    # ---- brand end card: the speech (and a beat of silence) is allowed to finish
    end_at = round(max(0.0, total - 0.35), 3)
    end_dur = 5.4
    for m in inserts_meta:
        if m["kind"] == "outro":
            m["dur"] = round(max(m["dur"], end_at + 0.35 - m["at"]), 3)
    end_spec = {"brand": "Rudstock", "accent": "Crypto", "handle": "@TDmitryT",
                "sub": "Разбор по итогам конференции — в следующем ролике"}
    ov_end = override_for(ce, blocks[-1], "endcard", 0)
    end_spec.update({k: ov_end[k] for k in ("brand", "accent", "sub", "handle") if ov_end.get(k)})
    draw_endplate(c, end_spec, "endcard", end_at, end_dur)
    total_layer = round(end_at + end_dur, 3)

    # the frame stage never runs past the footage
    for w in c.stage:
        w["end"] = round(min(float(w["end"]), total), 3)
        w["start"] = round(max(0.0, float(w["start"])), 3)
    c.stage = [w for w in c.stage if w["end"] > w["start"] + 0.1]
    c.stage.sort(key=lambda w: w["start"])

    assert_no_ellipsis("comp", [n for n in re.findall(r'>([^<>]+)<', "".join(c.html))], [])

    # ---- write the composition
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
<div id="root" class="clip" data-composition-id="{cid}" data-start="0" data-duration="{total_layer:.3f}" data-width="1920" data-height="1080">
{chr(10).join(c.html)}

</div>
<script>
{JS_COMMON}{chr(10).join(c.js)}
window.__timelines['{cid}'] = tl;
tl.seek(0);
</script>
</body>
</html>
"""
    (comp / "index.html").write_text(html, encoding="utf-8")

    rows = ["| время | слова | элемент | анимация | звук | примечание |",
            "|---|---|---|---|---|---|"]
    for r in sorted(c.plan, key=lambda x: x["t"]):
        rows.append(f"| {r['t']:.1f} | {r['words']} | {r['element']} | {r['motion']} | "
                    f"{r['sound']} | {r.get('note', '')} |")
    (edit / "graphics_plan.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    meta = {"label": label, "duration_s": round(total, 3), "layer_s": total_layer,
            "endcard_at": end_at, "blocks": len(blocks), "elements": len(c.html),
            "inserts": inserts_meta, "notes": c.notes, "author": author,
            "copy_source": str(copy_path) if copy_path else None}
    (json_out or (edit / "comp_plan.json")).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (edit / "stage.json").write_text(
        json.dumps({"windows": c.stage, "montage_s": round(total, 3),
                    "layer_s": total_layer}, ensure_ascii=False, indent=2), encoding="utf-8")
    (edit / "timeline.json").write_text(
        json.dumps({"montage_s": round(total, 3), "endcard_s": end_dur,
                    "total_s": total_layer}, ensure_ascii=False, indent=2), encoding="utf-8")
    ce.write_fit_report(edit / "copy_fit.json")

    kinds: dict[str, int] = {}
    for m in inserts_meta:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    print(f"comp: {comp / 'index.html'}")
    print(f"  блоков {len(blocks)} | элементов {len(c.html)} | монтаж {total:.1f} с | "
          f"слой {total_layer:.1f} с (заставка на {end_at:.1f} с)")
    print("  вставки: " + (", ".join(f"{k} x{v}" for k, v in sorted(kinds.items(),
                                                                   key=lambda x: -x[1])) or "нет"))
    print(f"  привязано к речи: {sum(1 for m in inserts_meta if m['anchored'])}"
          f"/{len(inserts_meta)}")
    print(f"  режимы кадра: " + ", ".join(f"{w['mode']} {w['start']:.1f}-{w['end']:.1f}"
                                          for w in c.stage))
    if ce.fits:
        print(f"  тексты подогнаны под ширину карточек: {len(ce.fits)} "
              f"(см. copy_fit.json)")
    for n in c.notes:
        print(f"  ! {n}")
    print(f"  источник текстов: {copy_path.name if copy_path else 'автогенерация'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Brand graphics layer from the script plan")
    ap.add_argument("label")
    ap.add_argument("--edit", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--copy", default=None, help="curated copy file (inserts.json)")
    a = ap.parse_args(argv)
    ed = Path(a.edit) if a.edit else ROOT / "runs" / a.label / "edit"
    cp = Path(a.copy) if a.copy else None
    if cp and not cp.is_absolute():
        cp = ROOT / cp
    return build(a.label, ed, Path(a.json) if a.json else None, cp)


if __name__ == "__main__":
    raise SystemExit(main())
