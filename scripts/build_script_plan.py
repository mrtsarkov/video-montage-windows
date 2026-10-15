#!/usr/bin/env python3
"""Turn the shooting script into a machine plan (blocks, B-roll marks, placements).

The script format (one block per scene):

    #1Хук: правила яснее, цена ниже~50 сек
    текст, который читается вслух
    🎞 B-roll: титр «...» + справа виджет котировок BingX: BTC 81 174 (-2.38%), ETH 2 373 (-4.76%)

Everything is drawn from this file: block boundaries drive the scene transitions,
the B-roll marks drive the graphics, and the numbers in a mark are taken from the text
(never invented).

Usage:
  build_script_plan.py <script.md> <edit_dir> [--words transcripts/xxx-words.json]
                       [--edl edl.json] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
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


def main() -> int:
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

    def src_to_timeline(src_t: float):
        for a, b, t0 in timeline:
            if a <= src_t <= b:
                return round(t0 + (src_t - a), 3)
        return None

    words_path = Path(args.words) if args.words else None
    if words_path is None:
        cands = sorted((edit / "transcripts").glob("*-words.json"))
        words_path = cands[0] if cands else None
    transcript = json.loads(words_path.read_text(encoding="utf-8-sig")) if words_path and words_path.is_file() else []

    def locate(block: dict, start_from: int = 0):
        """Match a block to the take: score every position by how many of the block's
        opening words appear nearby. Positional comparison fails as soon as the speaker
        drops or adds a word, which happens in every block."""
        if not transcript or not block["narration"]:
            return None, None, start_from
        needle = [w.lower() for w in re.findall(r"[А-Яа-яЁёA-Za-z0-9]{4,}",
                                                " ".join(block["narration"]))[:8]]
        if not needle:
            return None, None, start_from
        low = [w["word"].strip().lower().strip(",.!?") for w in transcript]
        span = max(12, len(needle) * 3)
        best, best_hits = None, 0
        for i in range(start_from, len(low)):
            window = low[i:i + span]
            hits = sum(1 for n in needle if any(w.startswith(n[:4]) for w in window))
            if hits > best_hits:
                best_hits, best = hits, i
        if best is None or best_hits < max(2, len(needle) // 2):
            return None, None, start_from
        src = float(transcript[best]["start"])
        return src, src_to_timeline(src), best

    out_blocks = []
    cursor = 0
    for b in blocks:
        src_t, tl_t, cursor = locate(b, cursor)
        out_blocks.append({
            "n": b["n"], "title": b["title"], "planned_s": b["planned_s"],
            "narration": " ".join(b["narration"]),
            "source_start_s": src_t, "timeline_start_s": tl_t,
            "broll_spec": b["broll"],
            "assets": [a for spec in b["broll"] for a in assets_of(spec)],
        })

    matched = sum(1 for b in out_blocks if b["timeline_start_s"] is not None)
    # a block the matcher could not find belongs right after its predecessor
    for i, b in enumerate(out_blocks):
        if b["timeline_start_s"] is not None:
            continue
        prev = next((out_blocks[j] for j in range(i - 1, -1, -1)
                     if out_blocks[j]["timeline_start_s"] is not None), None)
        nxt = next((out_blocks[j] for j in range(i + 1, len(out_blocks))
                    if out_blocks[j]["timeline_start_s"] is not None), None)
        lo = (prev["timeline_start_s"] + prev["planned_s"]) if prev else 0.0
        hi = nxt["timeline_start_s"] if nxt else lo + b["planned_s"]
        b["timeline_start_s"] = round(max(0.0, min(lo, hi - 1.0)) if hi > lo else max(0.0, lo), 3)
        b["placed_by"] = "interpolated"

    known = out_blocks
    for i, b in enumerate(known):
        end = known[i + 1]["timeline_start_s"] if i + 1 < len(known) else None
        b["timeline_end_s"] = end
        b["actual_s"] = round(end - b["timeline_start_s"], 2) if end else None

    plan = {
        "script": str(args.script),
        "blocks": out_blocks,
        "planned_total_s": planned,
        "words": words,
        "pace_wpm": round(words / max(1, planned) * 60),
        "located_blocks": matched,
        "transcript_words": len(transcript),
    }
    dest = Path(args.json) if args.json else edit / "script_plan.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Script plan: {dest}")
    print(f"  блоков {len(blocks)} | плановая сумма {planned} с | слов {words} | темп {plan['pace_wpm']} сл/мин")
    print(f"  привязано к записи: {matched}/{len(blocks)} (остальные по интерполяции) | слов {len(transcript)}")
    kinds: dict[str, int] = {}
    for b in out_blocks:
        for a in b["assets"]:
            kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    print(f"  что рисовать: " + ", ".join(f"{k}×{v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])))
    for b in out_blocks[:6]:
        where = f"{b['timeline_start_s']:.1f}s" if b["timeline_start_s"] is not None else "не найдено"
        print(f"    #{b['n']:02d} {b['title'][:34]:34s} план {b['planned_s']:>3}с  на таймлайне {where:>10}  вставок {len(b['assets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
