#!/usr/bin/env python3
"""Build subtitle cues from voice transcript with attack alignment."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# import attack logic
sys.path.insert(0, str(Path(__file__).parent))
from subtitle_attacks import read_wav_mono, rms_db, find_attacks  # noqa: E402


def group_cues(words: list[dict], lead: float = 0.1) -> list[dict]:
    cues: list[dict] = []
    i = 0
    while i < len(words):
        chunk = [words[i]]
        i += 1
        while i < len(words):
            gap = words[i]["start"] - chunk[-1]["end"]
            text_len = sum(len(w["word"]) for w in chunk)
            if gap > 0.35 or text_len > 14 or words[i]["word"].strip().endswith((".", "!", "?", "…")):
                if chunk[-1]["word"].strip().endswith((",", ";", ":")):
                    chunk.append(words[i])
                    i += 1
                    continue
                break
            if len(chunk) >= 2:
                break
            chunk.append(words[i])
            i += 1
        text = " ".join(w["word"].strip() for w in chunk)
        start = max(0.0, chunk[0]["start"] - lead)
        end = chunk[-1]["end"]
        cues.append({"text": text, "start": round(start, 3), "end": round(end, 3), "words": chunk})
    return cues


def align_words(words: list[dict], attacks: list[dict], shift: float = 0.12) -> list[dict]:
    """Simple global shift alignment."""
    aligned = []
    for w in words:
        aligned.append({**w, "start": round(max(0, w["start"] - shift), 3), "end": round(w["end"] - shift, 3)})
    return aligned


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: build_subtitles.py <voice-words.json> <subtitles.json>", file=sys.stderr)
        return 1
    words = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    words = align_words(words, [])
    cues = group_cues(words)
    out = Path(sys.argv[2])
    out.write_text(json.dumps(cues, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Subtitles: {len(cues)} cues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
