#!/usr/bin/env python3
"""Build EDL from word transcript: trim pauses, drop fillers, pick best path."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FILLERS = {"э", "э-э", "ээ", "м", "мм", "ну", "как", "бы", "типа", "вот", "значит"}
DROP_PHRASES = [
    re.compile(r"^сразу покажу$", re.I),
    re.compile(r"^простоклашенной$", re.I),
]


def load_words(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def group_phrases(words: list[dict], pause: float = 0.35) -> list[list[dict]]:
    phrases: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > pause:
            phrases.append(cur)
            cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)
    return phrases


def phrase_text(p: list[dict]) -> str:
    return " ".join(w["word"].strip() for w in p).strip()


def normalize(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def is_drop_phrase(p: list[dict]) -> bool:
    t = phrase_text(p)
    if not t or t.lower() in FILLERS:
        return True
    for rx in DROP_PHRASES:
        if rx.search(t):
            return True
    # lone filler words
    toks = [w["word"].strip().lower().strip(",.!?") for w in p]
    if all(t in FILLERS or t == "" for t in toks):
        return True
    return False


def dedupe_phrases(phrases: list[list[dict]]) -> list[list[dict]]:
    """Drop earlier duplicate normalized phrases, keep later."""
    seen: dict[str, int] = {}
    out: list[list[dict]] = []
    for p in phrases:
        key = normalize(phrase_text(p))[:80]
        if len(key) < 8:
            out.append(p)
            continue
        if key in seen:
            # replace earlier with this later attempt
            out[seen[key]] = p
        else:
            seen[key] = len(out)
            out.append(p)
    return out


def trim_phrase_edges(p: list[dict], pre_pad: float = 0.06, post_pad: float = 0.04) -> dict:
    text = phrase_text(p)
    start = max(0.0, p[0]["start"] - pre_pad)
    end = p[-1]["end"] + post_pad
    return {
        "text": text,
        "source": "2026-05-28 13-20-36.mp4",
        "in": round(start, 3),
        "out": round(end, 3),
        "reason": "best single-take phrase after dedupe",
    }


def build(words: list[dict]) -> list[dict]:
    phrases = group_phrases(words)
    phrases = [p for p in phrases if not is_drop_phrase(p)]
    phrases = dedupe_phrases(phrases)
    # merge very short adjacent fragments (<3 words) with next if gap small
    merged: list[list[dict]] = []
    i = 0
    while i < len(phrases):
        p = phrases[i]
        if len(p) < 3 and i + 1 < len(phrases) and phrases[i + 1][0]["start"] - p[-1]["end"] < 0.25:
            phrases[i + 1] = p + phrases[i + 1]
            i += 1
            continue
        merged.append(p)
        i += 1
    return [trim_phrase_edges(p) for p in merged]


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: build_edl.py <words.json> <edl.json>", file=sys.stderr)
        return 1
    words = load_words(Path(sys.argv[1]))
    edl = build(words)
    out = Path(sys.argv[2])
    out.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
    dur = sum(c["out"] - c["in"] for c in edl)
    print(f"EDL: {len(edl)} clips, {dur:.1f}s edited duration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
