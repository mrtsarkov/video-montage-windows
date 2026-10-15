#!/usr/bin/env python3
"""Build an EDL from a word transcript (spec §4).

Draft pass: drop fillers and lone interjections, keep the best attempt of each
repeated phrase (the later one wins), merge tiny fragments, trim the edges by a
small pad. Cut points are only *guessed* here from word times - `snap_cuts.py`
then moves every edge onto the speech envelope, because whisper timestamps drift
by up to half a second on tails (spec §4).

Usage:
  build_edl.py <words.json> <edl.json> [--source NAME] [--pause 0.35]
               [--min-words 3] [--pre 0.06] [--post 0.04]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FILLERS = {"э", "э-э", "ээ", "м", "мм", "ну", "как", "бы", "типа", "вот", "значит", "эм"}
DROP_PHRASES = [
    re.compile(r"^сразу покажу$", re.I),
    re.compile(r"^простоклашенной$", re.I),
]


def phrase_text(p: list[dict]) -> str:
    return " ".join(w["word"].strip() for w in p).strip()


def normalize(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def group_phrases(words: list[dict], pause: float) -> list[list[dict]]:
    phrases, cur = [], []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > pause:
            phrases.append(cur)
            cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)
    return phrases


def is_drop_phrase(p: list[dict]) -> bool:
    t = phrase_text(p)
    if not t or t.lower() in FILLERS:
        return True
    if any(rx.search(t) for rx in DROP_PHRASES):
        return True
    toks = [w["word"].strip().lower().strip(",.!?") for w in p]
    return all(tok in FILLERS or tok == "" for tok in toks)


def dedupe_phrases(phrases: list[list[dict]]) -> list[list[dict]]:
    """Keep the later attempt of a repeated phrase (spec §4: on a tie take the later take)."""
    seen: dict[str, int] = {}
    out: list[list[dict]] = []
    for p in phrases:
        key = normalize(phrase_text(p))[:80]
        if len(key) < 8:
            out.append(p)
            continue
        if key in seen:
            out[seen[key]] = p
        else:
            seen[key] = len(out)
            out.append(p)
    return out


def merge_short(phrases: list[list[dict]], min_words: int, gap: float = 0.25) -> list[list[dict]]:
    merged: list[list[dict]] = []
    i = 0
    while i < len(phrases):
        p = phrases[i]
        if len(p) < min_words and i + 1 < len(phrases) and phrases[i + 1][0]["start"] - p[-1]["end"] < gap:
            phrases[i + 1] = p + phrases[i + 1]
            i += 1
            continue
        merged.append(p)
        i += 1
    return merged


def trim(p: list[dict], source: str, pre: float, post: float) -> dict:
    return {
        "text": phrase_text(p),
        "source": source,
        "in": round(max(0.0, p[0]["start"] - pre), 3),
        "out": round(p[-1]["end"] + post, 3),
        "reason": "draft from word timings; edges re-snapped to waveform",
    }


def build(words: list[dict], source: str, pause: float, min_words: int,
          pre: float, post: float) -> list[dict]:
    phrases = [p for p in group_phrases(words, pause) if not is_drop_phrase(p)]
    phrases = dedupe_phrases(phrases)
    phrases = merge_short(phrases, min_words)
    return [trim(p, source, pre, post) for p in phrases]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("words")
    ap.add_argument("out")
    ap.add_argument("--source", default=None, help="source file name stored in the EDL")
    ap.add_argument("--pause", type=float, default=0.35)
    ap.add_argument("--min-words", type=int, default=3)
    ap.add_argument("--pre", type=float, default=0.06)
    ap.add_argument("--post", type=float, default=0.04)
    args = ap.parse_args()

    words_path = Path(args.words)
    words = json.loads(words_path.read_text(encoding="utf-8-sig"))
    if not words:
        print("empty transcript", file=sys.stderr)
        return 1
    source = args.source or words_path.name.split("-words")[0]
    edl = build(words, source, args.pause, args.min_words, args.pre, args.post)
    Path(args.out).write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
    dur = sum(c["out"] - c["in"] for c in edl)
    print(f"EDL: {len(edl)} clips from {len(words)} words, {dur:.1f}s (draft, edges not snapped yet)")
    print(f"     written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
