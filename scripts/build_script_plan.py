#!/usr/bin/env python3
"""Turn the shooting script into a machine plan (blocks, B-roll marks, placements).

The script format (one block per scene):

    #1Хук: правила яснее, цена ниже~50 сек
    текст, который читается вслух
    🎞 B-roll: титр «...» + справа виджет котировок BingX: BTC 81 174 (-2.38%), ETH 2 373 (-4.76%)

Everything is drawn from this file: block boundaries drive the scene transitions,
the B-roll marks drive the graphics, and the numbers in a mark are taken from the text
(never invented).

Block placement
---------------
The first version scored "how many of the block's opening words appear inside a
24-word window", which is a bag of words: on this take it put block 5 five seconds
early, so the "next block" plate appeared while the previous block was still being
spoken. Placement is now a *sequential* match - the opening words must be found in
order, tightly - and every block also gets

  * `source_first_word_s` / `timeline_first_word_s` - where its narration starts,
  * `source_last_word_s`  / `timeline_last_word_s`  - where its narration ends,
  * `boundary_s` - the middle of the pause between the previous block's last word and
    this block's first word. The divider belongs *there*, not at a guessed block start.

Usage:
  build_script_plan.py <script.md> <edit_dir> [--words transcripts/xxx-words.json]
                       [--edl edl.json] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# keyword -> element kind we can draw (§9.1 catalogue)
KINDS = [
    ("виджет котиров", "quotes"),
    ("котиров", "quotes"),
    ("график", "chart"),
    ("таблиц", "table"),
    ("таймлайн", "timeline"),
    ("чек-лист", "checklist"),
    ("чеклист", "checklist"),
    ("воронк", "funnel"),
    ("схем", "diagram"),
    ("инфографик", "diagram"),
    ("цитат", "quote"),
    ("логотип", "logo"),
    ("плашка подписки", "outro"),
    ("титр", "title"),
]
NUM = re.compile(r"[A-Z]{2,6}\s?\d[\d\s.,]*%?|\d[\d\s.,]*\s?(?:%|процент|млн|M\b|тыс)|\$\s?\d[\d.,]*")

STOP = {
    "это", "этот", "эта", "эти", "как", "так", "что", "чтобы", "или", "для", "при",
    "над", "под", "про", "чем", "все", "всё", "уже", "если", "но", "а", "и", "в", "во",
    "на", "с", "со", "за", "из", "к", "по", "о", "об", "от", "до", "же", "бы", "мы",
    "вы", "он", "она", "они", "был", "была", "было", "быть", "есть", "где", "когда",
    "тоже", "ещё", "еще", "просто", "очень", "себя", "свой", "своих", "который",
    "которая", "которые", "потому", "поэтому",
}


def read_any(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        import zipfile
        z = zipfile.ZipFile(path)
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        out = []
        for block in re.split(r"</w:p>", xml):
            txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", block, re.S))
            txt = re.sub(r"<[^>]+>", "", txt).strip()
            if txt:
                out.append(txt)
        return "\n".join(out)
    return path.read_text(encoding="utf-8-sig")


def parse_blocks(text: str) -> list[dict]:
    blocks, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = re.match(r"^#(\d+)\s*(.*?)\s*~\s*(\d+)\s*сек", line)
        if head:
            cur = {"n": int(head.group(1)), "title": head.group(2).strip(),
                   "planned_s": int(head.group(3)), "narration": [], "broll": []}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("🎞") or re.match(r"^\W*B-roll", line, re.I):
            cur["broll"].append(re.sub(r"^🎞\s*", "", line).strip())
        else:
            cur["narration"].append(line)
    return blocks


def kind_of(spec: str) -> str:
    low = spec.lower()
    for needle, kind in KINDS:
        if needle in low:
            return kind
    return "title"


def assets_of(spec: str) -> list[dict]:
    """Split a B-roll line into drawable items, keeping the numbers from the text."""
    parts = [p.strip(" .;") for p in re.split(r"[+;]|(?<=[а-яa-z0-9)])\.\s", spec) if p.strip()]
    items = []
    for part in parts:
        items.append({
            "kind": kind_of(part),
            "text": part,
            "numbers": sorted(set(m.group(0).strip() for m in NUM.finditer(part)))[:12],
        })
    return items


# ------------------------------------------------------------------ locating
def norm_token(w: str) -> str:
    return re.sub(r"[^\w]", "", (w or "").lower().replace("ё", "е"))


def needle_of(text: str, take: int, tail: bool = False) -> list[str]:
    """Distinctive tokens, in reading order (no stopwords, 4+ letters)."""
    toks = [t for t in re.findall(r"[А-Яа-яЁёA-Za-z0-9]{4,}", text)]
    keep = [t for t in toks if t.lower().replace("ё", "е") not in STOP]
    use = keep or toks
    return [t.lower().replace("ё", "е") for t in (use[-take:] if tail else use[:take])]


def seq_match(low: list[str], needle: list[str], lo: int, hi: int) -> tuple[int, int, float] | None:
    """Find the tightest in-order occurrence of `needle` inside low[lo:hi].

    Returns (start_index, end_index, score). Each needle token may match a token
    that *starts with* its first four characters, which tolerates inflection
    ("правила"/"правил", "рынок"/"рынка") while still demanding the order.
    """
    if not needle:
        return None
    best = None
    span_limit = max(6, int(len(needle) * 2.6))
    for i in range(lo, min(hi, len(low))):
        if not low[i].startswith(needle[0][:4]):
            continue
        pos, matched, last = i, 0, i
        for n in needle:
            found = -1
            for j in range(pos, min(hi, last + span_limit, len(low))):
                if low[j].startswith(n[:4]):
                    found = j
                    break
            if found < 0:
                continue
            matched += 1
            last = found
            pos = found + 1
        if matched == 0:
            continue
        span = last - i + 1
        score = matched - 0.08 * max(0, span - len(needle))
        if best is None or score > best[2]:
            best = (i, last, score)
    if best is None:
        return None
    need_min = max(2, int(round(len(needle) * 0.6)))
    if best[2] < need_min:
        return None
    return best


def pause_before(low: list[dict], index: int, look_back: float = 3.5) -> tuple[float, float]:
    """Largest real pause that ends at word `index`: (gap_start_s, gap_end_s)."""
    if index <= 0:
        return (0.0, float(low[0]["start"]) if low else 0.0)
    best = (float(low[index - 1]["end"]), float(low[index]["start"]))
    t_end = float(low[index]["start"])
    for j in range(index - 1, 0, -1):
        if t_end - float(low[j]["end"]) > look_back:
            break
        gap = float(low[j]["start"]) - float(low[j - 1]["end"])
        if gap > best[1] - best[0]:
            best = (float(low[j - 1]["end"]), float(low[j]["start"]))
    return best


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("edit_dir")
    ap.add_argument("--words", default=None)
    ap.add_argument("--edl", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    edit = Path(args.edit_dir)
    blocks = parse_blocks(read_any(Path(args.script)))
    if not blocks:
        raise SystemExit("в сценарии не найдено ни одного блока вида '#NЗаголовок~50 сек'")

    planned = sum(b["planned_s"] for b in blocks)
    words = sum(len(" ".join(b["narration"]).split()) for b in blocks)

    # source -> timeline map, if an EDL exists already
    edl_path = Path(args.edl) if args.edl else edit / "edl.json"
    timeline = []
    if edl_path.is_file():
        edl = json.loads(edl_path.read_text(encoding="utf-8-sig"))
        t = 0.0
        for seg in edl:
            timeline.append((float(seg["in"]), float(seg["out"]), t))
            t += float(seg["out"]) - float(seg["in"])
    total = timeline[-1][2] + (timeline[-1][1] - timeline[-1][0]) if timeline else 0.0

    def src_to_timeline(src_t: float):
        for a, b, t0 in timeline:
            if a <= src_t <= b:
                return round(t0 + (src_t - a), 3)
        # the stamp sits inside a pause the edit removed: the montage resumes at the
        # next cut, and that is exactly where the block starts on screen
        for a, b, t0 in timeline:
            if a > src_t:
                return round(t0, 3)
        if timeline:
            a, b, t0 = timeline[-1]
            return round(t0 + (b - a), 3)
        return None

    words_path = Path(args.words) if args.words else None
    if words_path is None:
        cands = sorted((edit / "transcripts").glob("*-words.json"))
        words_path = cands[0] if cands else None
    transcript = json.loads(words_path.read_text(encoding="utf-8-sig")) if words_path and words_path.is_file() else []
    low = [norm_token(w.get("word", "")) for w in transcript]

    out_blocks = []
    cursor = 0
    for b in blocks:
        heads = needle_of(" ".join(b["narration"]), 10)
        tails = needle_of(" ".join(b["narration"]), 6, tail=True)
        src_from = src_to = None
        src_last = None
        matched = 0
        if transcript and heads:
            window_hi = min(len(low), cursor + max(60, len(heads) * 22))
            # the speaker paraphrases: drop the opening word or two before giving up
            variants = [heads, heads[1:], heads[2:]]
            best = None
            for scope in (window_hi, len(low)):
                for var in variants:
                    if len(var) < 4:
                        continue
                    m = seq_match(low, var, cursor, scope)
                    if m and (best is None or m[2] > best[2]):
                        best = m
                if best is not None:
                    break
            if best is not None:
                src_from, _, matched = best
        if src_from is not None:
            src_from = float(transcript[src_from]["start"])
            search_from = next(i for i, w in enumerate(transcript)
                               if float(w["start"]) >= src_from - 1e-6)
            tm = seq_match(low, tails, search_from, min(len(low), search_from + len(heads) * 24))
            if tm:
                src_last = float(transcript[tm[1]]["end"])
            src_to = src_last or src_from
        block = {
            "n": b["n"], "title": b["title"], "planned_s": b["planned_s"],
            "narration": " ".join(b["narration"]),
            "source_first_word_s": src_from,
            "source_last_word_s": src_last,
            "timeline_first_word_s": src_to_timeline(src_from) if src_from is not None else None,
            "timeline_last_word_s": src_to_timeline(src_last) if src_last is not None else None,
            "match_score": matched,
            "broll_spec": b["broll"],
            "assets": [a for spec in b["broll"] for a in assets_of(spec)],
        }
        # the boundary pause: from the previous block's last word to this block's first
        if src_from is not None:
            idx = next((i for i, w in enumerate(transcript)
                        if float(w["start"]) >= src_from - 1e-6), None)
            if idx is not None:
                g0, g1 = pause_before(transcript, idx)
                block["boundary_pause_s"] = round(g1 - g0, 3)
                block["boundary_src_s"] = round((g0 + g1) / 2.0, 3)
                # the pause itself is usually cut out of the montage, so the block
                # boundary on the timeline *is* its first word
                block["boundary_s"] = src_to_timeline((g0 + g1) / 2.0)
                if block["boundary_s"] is None:
                    # the pause was cut out: the divider belongs on the cut itself
                    block["boundary_s"] = block["timeline_first_word_s"]
        out_blocks.append(block)
        if src_from is not None:
            cursor = max(cursor, next((i for i, w in enumerate(transcript)
                                       if float(w["start"]) >= src_from - 1e-6), cursor) + 1)

    located = sum(1 for b in out_blocks if b["timeline_first_word_s"] is not None)
    # a block the matcher could not find belongs right after its predecessor
    for i, b in enumerate(out_blocks):
        if b["timeline_first_word_s"] is not None:
            continue
        prev = next((out_blocks[j] for j in range(i - 1, -1, -1)
                     if out_blocks[j]["timeline_first_word_s"] is not None), None)
        nxt = next((out_blocks[j] for j in range(i + 1, len(out_blocks))
                    if out_blocks[j]["timeline_first_word_s"] is not None), None)
        lo = (prev["timeline_last_word_s"] or prev["timeline_first_word_s"] or 0.0) if prev else 0.0
        hi = (nxt["timeline_first_word_s"] - nxt.get("boundary_pause_s", 0.0)) if nxt else lo + b["planned_s"]
        b["timeline_first_word_s"] = round(max(0.0, min(lo, hi - 1.0)) if hi > lo else max(0.0, lo), 3)
        b["boundary_s"] = b["timeline_first_word_s"]
        b["placed_by"] = "interpolated"

    for i, b in enumerate(out_blocks):
        nxt = out_blocks[i + 1] if i + 1 < len(out_blocks) else None
        b["timeline_start_s"] = b["timeline_first_word_s"]
        b["timeline_end_s"] = nxt["timeline_first_word_s"] if nxt else round(total, 3)
        b["source_start_s"] = b["source_first_word_s"]
        b["source_end_s"] = b["source_last_word_s"]
        b["actual_s"] = (round(b["timeline_end_s"] - b["timeline_start_s"], 2)
                         if b["timeline_end_s"] is not None and b["timeline_start_s"] is not None
                         else None)
        # the block's tail words may sit inside a pause the edit removed: then the
        # block simply runs up to the next block's boundary
        if b["timeline_last_word_s"] is None and b["timeline_first_word_s"] is not None:
            stop = nxt.get("boundary_s") if nxt else round(total, 3)
            b["timeline_last_word_s"] = round(float(stop or b["timeline_end_s"]), 3)
            if b["source_last_word_s"] is None:
                b["source_last_word_s"] = b["source_first_word_s"]

    plan = {
        "script": str(args.script),
        "blocks": out_blocks,
        "planned_total_s": planned,
        "timeline_total_s": round(total, 3),
        "words": words,
        "pace_wpm": round(words / max(1, planned) * 60),
        "located_blocks": located,
        "transcript_words": len(transcript),
    }
    dest = Path(args.json) if args.json else edit / "script_plan.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Script plan: {dest}")
    print(f"  блоков {len(blocks)} | плановая сумма {planned} с | слов {words} | темп {plan['pace_wpm']} сл/мин")
    print(f"  привязано к записи: {located}/{len(blocks)} | слов в расшифровке {len(transcript)}")
    kinds: dict[str, int] = {}
    for b in out_blocks:
        for a in b["assets"]:
            kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    print("  что рисовать: " + ", ".join(f"{k}×{v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])))
    for b in out_blocks:
        first, last = b["timeline_first_word_s"], b["timeline_last_word_s"]
        if first is None:
            print(f"    #{b['n']:02d} {b['title'][:32]:32s} НЕ НАЙДЕН (по интерполяции)")
            continue
        pause = b.get("boundary_pause_s") or 0.0
        last_txt = f"{last:7.2f}" if last is not None else "   —   "
        print(f"    #{b['n']:02d} {b['title'][:32]:32s} речь {first:7.2f}-{last_txt}s "
              f"граница {b.get('boundary_s') if b.get('boundary_s') is not None else first:7.2f}s "
              f"(пауза {pause:.2f}s, совпадений {b['match_score']}) "
              f"вставок {len(b['assets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
