#!/usr/bin/env python3
"""Build an EDL from a word transcript (spec §4).

Draft pass: drop fillers and lone interjections, remove retakes (a phrase that the
speaker aborted and then said again), merge tiny fragments, trim the edges by a
small pad. Cut points are only *guessed* here from word times - `snap_cuts.py`
then moves every edge onto the speech envelope.

Retake removal has three rules, in this order:

  1. `stutter`  - a repeated token inside one phrase ("правила, правила яснее").
  2. `repeat`   - the same sentence said twice within `--retake-window` seconds;
                  the **later** attempt is kept (spec §4: on a tie take the later
                  take - the speaker is correcting himself).
  3. `abort`    - the earlier attempt is a token-prefix of the later one, i.e. he
                  started a sentence, stopped, and began it again. The earlier
                  attempt goes.

Rules 2 and 3 need trustworthy word times: run `build_words_dtw.py` first, because
the old per-segment timestamps made a whole phrase look like one word.

Every removed attempt is written to `edl_retakes.json` next to the EDL.

Usage:
  build_edl.py <words.json> <edl.json> [--source NAME] [--pause 0.35]
               [--min-words 3] [--pre 0.06] [--post 0.04]
               [--retake-window 30] [--retake-sim 0.62] [--no-retakes]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
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


def tokens_of(s: str) -> list[str]:
    return [t for t in normalize(s).split() if t]


def similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def is_aborted_prefix(a: str, b: str, min_tokens: int = 2) -> bool:
    """True when `a` is a truncated beginning of `b` ("Плюс внешний фон." -> "Плюс внешний фон. Оттоки...")."""
    ta, tb = tokens_of(a), tokens_of(b)
    if len(ta) < min_tokens or len(ta) >= len(tb):
        return False
    if ta == tb[: len(ta)]:
        return True
    # tolerate one wrong token inside the overlap (whisper spells a slip differently)
    if len(ta) >= 3:
        lead = tb[: len(ta)]
        same = sum(1 for x, y in zip(ta, lead) if x == y)
        return same >= len(ta) - 1
    return False


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


def collapse_stutter(p: list[dict], removed: list[dict]) -> list[dict]:
    """Drop a token that repeats the one before it ("правила, правила яснее")."""
    out: list[dict] = []
    for w in p:
        if out:
            prev = out[-1]["word"].strip().lower().strip(",.!?-—")
            cur = w["word"].strip().lower().strip(",.!?-—")
            if cur and cur == prev and len(cur) > 2:
                removed.append({"rule": "stutter", "text": w["word"].strip(),
                                "start": round(float(w["start"]), 3),
                                "end": round(float(w["end"]), 3)})
                out[-1]["end"] = w["end"]
                continue
        out.append(dict(w))
    return out


def find_retakes(phrases: list[list[dict]], window: float, thr: float) -> list[dict]:
    """Indices of the earlier attempts to drop, plus a record of why."""
    killed: dict[int, dict] = {}
    n = len(phrases)
    for i in range(n):
        if i in killed:
            continue
        ti = phrase_text(phrases[i])
        ni = normalize(ti)
        if len(ni) < 6:
            continue
        for j in range(i + 1, n):
            gap = phrases[j][0]["start"] - phrases[i][-1]["end"]
            if gap > window:
                break
            tj = phrase_text(phrases[j])
            nj = normalize(tj)
            if nj == ni and len(ni) >= 8:
                rule = "repeat"
            elif is_aborted_prefix(ti, tj) or is_aborted_prefix(ti, tj + " "):
                rule = "abort"
            elif similarity(ti, tj) >= thr and len(tokens_of(ti)) >= 3:
                rule = "repeat"
            else:
                continue
            killed[i] = {"rule": rule, "kept": j, "window_s": round(gap, 2),
                         "sim": round(similarity(ti, tj), 3),
                         "dropped_text": ti, "kept_text": phrase_text(phrases[j]),
                         "dropped_start_s": round(float(phrases[i][0]["start"]), 3),
                         "dropped_end_s": round(float(phrases[i][-1]["end"]), 3)}
            break
    return killed


def dedupe_phrases(phrases: list[list[dict]], window: float, thr: float,
                   notes: list[dict]) -> list[list[dict]]:
    killed = find_retakes(phrases, window, thr)
    for i in sorted(killed):
        notes.append(killed[i])
    return [p for i, p in enumerate(phrases) if i not in killed]


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
          pre: float, post: float, window: float, thr: float, retakes: bool,
          notes: list[dict]) -> list[dict]:
    phrases = [p for p in group_phrases(words, pause) if not is_drop_phrase(p)]
    if retakes:
        phrases = [collapse_stutter(p, notes) for p in phrases]
        phrases = [p for p in phrases if p]
        phrases = dedupe_phrases(phrases, window, thr, notes)
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
    ap.add_argument("--retake-window", type=float, default=30.0,
                    help="seconds to look back for a repeated or aborted phrase")
    ap.add_argument("--retake-sim", type=float, default=0.62,
                    help="similarity above which the earlier phrase is a retake")
    ap.add_argument("--no-retakes", action="store_true", help="keep every attempt (debug)")
    args = ap.parse_args()

    words_path = Path(args.words)
    words = json.loads(words_path.read_text(encoding="utf-8-sig"))
    if not words:
        print("empty transcript", file=sys.stderr)
        return 1
    source = args.source or words_path.name.split("-words")[0]
    notes: list[dict] = []
    edl = build(words, source, args.pause, args.min_words, args.pre, args.post,
                args.retake_window, args.retake_sim, not args.no_retakes, notes)
    Path(args.out).write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")

    report = Path(args.out).with_name("edl_retakes.json")
    report.write_text(json.dumps({"retakes": notes, "clips": len(edl)}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    dur = sum(c["out"] - c["in"] for c in edl)
    dropped = sum(1 for n in notes if n.get("rule") in ("abort", "repeat"))
    print(f"EDL: {len(edl)} clips from {len(words)} words, {dur:.1f}s (draft, edges not snapped yet)")
    print(f"     retakes: {dropped} attempt(s) removed, {len(notes) - dropped} stutter token(s); "
          f"see {report.name}")
    for n in notes[:8]:
        if n.get("rule") in ("abort", "repeat"):
            print(f"       - [{n['rule']} @{n['dropped_start_s']:.1f}s] "
                  f"«{n['dropped_text'][:60]}»")
        else:
            print(f"       - [stutter @{n.get('start', 0):.1f}s] «{n.get('text', '')}»")
    print(f"     written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
