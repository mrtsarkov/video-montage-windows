#!/usr/bin/env python3
"""Viewer-facing copy for the graphic inserts, and a hard "nothing is truncated" gate.

Two problems this module solves.

**1. Garbage from the script reached the screen.** The shooting script carries
production markup - `#1Хук: правила яснее, цена ниже`, `🎞 B-roll: Монтаж: титр
«...»`, `CTA`, `Bull-сценарий:` - and the first version printed the block heading
verbatim as a card headline and, when a component had no content, as its only
chip. Here the heading is rewritten into a sentence a viewer can read, the markup
is stripped, and every component gets real content (numbers, names, bullets) taken
from the narration and the B-roll mark.

**2. Text was "finished" with an ellipsis.** `cut(text, n)` chopped at n characters
and appended `…`, so cards looked like someone forgot to finish typing. Here every
string is measured with the real Inter font (`PIL.ImageFont.getlength`) against the
width the card actually has, and a string that does not fit is *rewritten*: a shorter
authored variant is used, or a trailing clause is dropped at a comma. An ellipsis is
never produced; `assert_no_ellipsis` fails the build if one ever appears.

A run can override the generated copy with `script/<label>-inserts.json` (see
`docs/INSERT-COPY.md`), which is how a specific video gets hand-polished wording
without losing the automatic path for every other take.

Usage (library):
  from insert_copy import CopyEngine
  ce = CopyEngine(brand_json, overrides_path)
  ce.card("chips", block, defaults={"kicker": "...", "items": [...]})
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "refs" / "brandbook" / "fonts"
SUFFIX = {400: "regular", 500: "500", 600: "600", 700: "700", 800: "800", 900: "900"}

# ---- markup that must never reach the screen ---------------------------------
PRODUCTION_PREFIX = re.compile(
    r"^\s*(?:#\s*\d+\s*)?(?:Хук|Завязка|Блок|Интро|Аутро|CTA|Код|Финал|Дальше)\s*[:\-—]\s*",
    re.I)
BROLL_PREFIX = re.compile(r"^\s*(?:🎞\s*)?(?:B-roll|Би-рол|Биролл|Монтаж|Титр|Титр\s+и)\s*[:\-—]\s*", re.I)
MARKUP_TOKEN = re.compile(r"#\d+|[🎞📈🎬]|\bB-roll\b", re.I)
SCENARIO_LABEL = re.compile(r"^\s*(Bull|Bear|Бычий|Медвежий)\s*[-—:]?\s*(сценарий)?\s*[:\-—]\s*", re.I)
QUOTE_IN_TEXT = re.compile(r"[«»\"]")
TYPO = {"ВБРФ": "ВЭБ.РФ", "Анбординг": "Онбординг", "анбординг": "онбординг",
        "комплайенс": "комплаенс", "стэк": "стек", "Старкнет": "Starknet",
        "арбитром": "Arbitrum", "Арбитром": "Arbitrum", "SPA": "SPY", "спайс": "SPY",
        "Cerebros": "Cerebras", "PAMFUN": "Pump.fun", "ланги": "лонги",
        "Сарьков": "Царьков", "Ростов Крипто": "Rudstock Crypto"}


def fix_typos(t: str) -> str:
    for bad, good in TYPO.items():
        t = t.replace(bad, good)
    return t


def strip_markup(t: str) -> str:
    """Remove production markup, keep the human words."""
    t = t or ""
    t = BROLL_PREFIX.sub("", t)
    t = PRODUCTION_PREFIX.sub("", t)
    t = SCENARIO_LABEL.sub(lambda m: ("Бычий" if m.group(1).lower() in ("bull", "бычий")
                                      else "Медвежий") + " сценарий: ", t)
    t = MARKUP_TOKEN.sub(" ", t)
    t = re.sub(r"\s*~\s*\d+\s*сек\s*$", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" .,;:—-")
    return fix_typos(t)


def human_title(title: str, limit_words: int = 9) -> str:
    """`#1Хук: правила яснее, цена ниже` -> `Правила яснее — цена ниже`."""
    t = strip_markup(title)
    t = re.sub(r"^(Хук|CTA|Итог)\b[:\-—]?\s*", "", t, flags=re.I).strip()
    if not t:
        return "Обзор"
    # "правила яснее, цена ниже" -> "Правила яснее — цена ниже"
    if "," in t and ":" not in t:
        head, tail = [x.strip() for x in t.split(",", 1)]
        if head and tail and len(head.split()) <= 4 and len(tail.split()) <= 5:
            t = f"{head} — {tail}"
    t = t[0].upper() + t[1:] if t else t
    return t


def sentence_case(t: str) -> str:
    t = t.strip()
    return (t[0].upper() + t[1:]) if t else t


# ------------------------------------------------------------------ measuring
class TextMetrics:
    """Real Inter metrics: `getlength` is what the browser lays out with (Latin+Cyrillic)."""

    def __init__(self, font_dir: Path = FONT_DIR):
        self.dir = font_dir
        self._cache: dict[tuple[int, int], ImageFont.FreeTypeFont] = {}
        self._wcache: dict[tuple[str, int, int], float] = {}

    def font(self, weight: int, size: int) -> ImageFont.FreeTypeFont:
        key = (weight, size)
        if key not in self._cache:
            path = self._pick(weight)
            self._cache[key] = ImageFont.truetype(str(path), size)
        return self._cache[key]

    def _pick(self, weight: int) -> Path:
        for w in (weight, 500, 600, 700, 800, 900, 400):
            p = self.dir / f"inter-v20-cyrillic_latin_latin-ext-{SUFFIX.get(w, 'regular')}.ttf"
            if p.is_file():
                return p
        raise FileNotFoundError(f"no Inter font in {self.dir}")

    def width(self, text: str, weight: int, size: int) -> float:
        key = (text, weight, size)
        if key not in self._wcache:
            self._wcache[key] = float(self.font(weight, size).getlength(text))
        return self._wcache[key]

    def wrap(self, text: str, weight: int, size: int, max_px: float) -> list[str]:
        lines, cur = [], ""
        for word in text.split():
            probe = f"{cur} {word}".strip()
            if cur and self.width(probe, weight, size) > max_px:
                lines.append(cur)
                cur = word
            else:
                cur = probe
        if cur:
            lines.append(cur)
        return lines

    def line_count(self, text: str, weight: int, size: int, max_px: float) -> int:
        return len(self.wrap(text, weight, size, max_px))

    def widest(self, text: str, weight: int, size: int, max_px: float) -> float:
        return max((self.width(l, weight, size) for l in self.wrap(text, weight, size, max_px)),
                   default=0.0)


def drop_tail_clause(text: str) -> str:
    """Drop a trailing subordinate clause at a comma - never mid-word, never with '…'."""
    parts = [p.strip() for p in re.split(r",\s+", text) if p.strip()]
    return ", ".join(parts[:-1]) if len(parts) > 1 else text


def shorten(text: str, metrics: TextMetrics, weight: int, size: int, max_px: float,
            max_lines: int, alts: list[str] | None = None) -> tuple[str, int]:
    """Return text that fits; the second value is how the fit was reached (0 = as is)."""
    for alt in (alts or []):
        if alt and metrics.line_count(alt, weight, size, max_px) <= max_lines:
            return alt, 2
    if metrics.line_count(text, weight, size, max_px) <= max_lines:
        return text, 0
    cur = text
    for _ in range(6):
        nxt = drop_tail_clause(cur)
        if nxt == cur:
            break
        cur = nxt
        if metrics.line_count(cur, weight, size, max_px) <= max_lines:
            return cur, 1
    # last resort: shed words from the end, keeping a whole-word string
    words = cur.split()
    while len(words) > 3:
        words = words[:-1]
        cand = " ".join(words).rstrip(" ,.;:—-")
        if metrics.line_count(cand, weight, size, max_px) <= max_lines:
            return cand, 3
    return " ".join(words).rstrip(" ,.;:—-"), 3


ELLIPSIS = "…"


def assert_no_ellipsis(label: str, texts: list[str], report: list[dict]) -> None:
    for t in texts:
        if ELLIPSIS in t or t.strip().endswith("..."):
            report.append({"where": label, "text": t})
    if report:
        bad = "; ".join(f"{r['where']}: {r['text'][:60]}" for r in report[:5])
        raise ValueError(f"ellipsis in card copy - write a shorter line instead: {bad}")


# ------------------------------------------------------------- literary copy
KICKER = {
    "quotes": "КОТИРОВКИ", "chart": "ДИНАМИКА", "table": "ЦИФРЫ", "timeline": "ХРОНОЛОГИЯ",
    "funnel": "СТРУКТУРА", "checklist": "ЧТО ДЕЛАТЬ", "diagram": "КАК ЭТО РАБОТАЕТ",
    "quote": "МЫСЛЬ", "logo": "КОНТЕКСТ", "outro": "ДАЛЬШЕ", "title": "СЕГОДНЯ",
    "stat": "ЦИФРА", "scenario": "СЦЕНАРИЙ", "premium": "ИНДИКАТОР", "miners": "РЕЕСТР",
    "chips": "КОРОТКО", "compare": "БЫЛО И СТАЛО", "steps": "ЦЕПОЧКА", "counter": "ЦИФРА",
}


class CopyEngine:
    """Card copy: generated from the script, optionally overridden per run."""

    def __init__(self, brand: dict | None = None, overrides: Path | None = None):
        self.metrics = TextMetrics()
        self.brand = brand or {}
        self.overrides: dict = {}
        if overrides and Path(overrides).is_file():
            self.overrides = json.loads(Path(overrides).read_text(encoding="utf-8-sig"))
        self.fits: list[dict] = []

    # ---------------------------------------------------------------- helpers
    def block_override(self, block: dict) -> dict:
        blocks = (self.overrides or {}).get("blocks", {})
        return blocks.get(str(block.get("n"))) or blocks.get(block.get("n")) or {}

    def insert_override(self, block: dict, kind: str, index: int) -> dict:
        ov = self.block_override(block)
        items = ov.get("inserts") or []
        for item in items:
            if item.get("kind") == kind:
                return item
        if 0 <= index < len(items):
            return items[index]
        return {}

    def title(self, block: dict) -> str:
        ov = self.block_override(block)
        return ov.get("title") or human_title(block.get("title", ""))

    def kicker(self, kind: str, block: dict | None = None, default: str | None = None) -> str:
        """Authored insert kicker wins; otherwise the kind's own label.

        A block-level kicker belongs to the block's divider, not to every card in
        the block - reusing it made every insert read "БЛОК 07".
        """
        if default:
            return str(default).upper()
        return KICKER.get(kind, "КОНТЕКСТ").upper()

    def fit(self, text: str, weight: int, size: int, max_px: float, max_lines: int,
            where: str, alts: list[str] | None = None) -> str:
        out, how = shorten(text, self.metrics, weight, size, max_px, max_lines, alts)
        if how:
            self.fits.append({"where": where, "how": how, "before": text, "after": out})
        return out

    def fit_lines(self, text: str, weight: int, size: int, max_px: float, max_lines: int,
                  where: str, alts: list[str] | None = None) -> list[str]:
        out = self.fit(text, weight, size, max_px, max_lines, where, alts)
        return self.metrics.wrap(out, weight, size, max_px)

    def write_fit_report(self, path: Path) -> None:
        path.write_text(json.dumps({"fitted": self.fits}, ensure_ascii=False, indent=2),
                        encoding="utf-8")


# ------------------------------------------------------------------ defaults
AUTHOR_FALLBACK = {"name": "Дмитрий Царьков", "role": "управляющий активами"}

#: fallbacks used only when neither the script nor the override gives content
def template_items(kind: str) -> list[str]:
    return {
        "chips": [], "diagram": [], "timeline": [], "checklist": [],
    }.get(kind, [])
